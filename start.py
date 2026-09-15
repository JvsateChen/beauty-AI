#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""采选美妆 AI · 本地一键启动

用法::

    python start.py                 # 构建(如缺) + 启动后端与前端 + 健康检查
    python start.py --dev           # 前端用 next dev（改代码热更新，便于迭代）
    python start.py --backend-only  # 只起后端
    python start.py --frontend-only # 只起前端
    python start.py --stop          # 停止本脚本启动的服务（按端口回收）
    python start.py --rebuild       # 强制重新构建前端

启动完成后打开 http://127.0.0.1:3000 即为产品界面；
后端交互式接口文档在 http://127.0.0.1:8000/docs 。

设计要点：
  · 后端用**当前解释器**（sys.executable）启动，保证依赖与 `pip install -r` 装的一致；
  · 端口被占用时先提示占用进程，`--stop` 可一键回收，避免起在旧代码上白测；
  · 前端优先用已有 `.next` 生产构建（更快、更接近线上），缺失或 `--rebuild` 时才构建；
  · 所有日志落到 `logs/`，便于出问题时回溯。
"""
from __future__ import annotations

import argparse
import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"
LOGS = ROOT / "logs"

BACKEND_PORT = int(os.environ.get("BACKEND_PORT", "8000"))
FRONTEND_PORT = int(os.environ.get("FRONTEND_PORT", "3000"))

IS_WIN = os.name == "nt"
CREATE_DETACHED = (
    subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
    if IS_WIN
    else 0
)


# --------------------------------------------------------------------------- 工具
def say(msg: str) -> None:
    print(msg, flush=True)


def port_in_use(port: int, host: str = "127.0.0.1") -> bool:
    with socket.socket() as s:
        s.settimeout(0.8)
        return s.connect_ex((host, port)) == 0


def pids_on_port(port: int) -> list[int]:
    """返回监听指定端口的 PID 列表（Windows 走 netstat，POSIX 走 lsof/ss）。"""
    pids: set[int] = set()
    try:
        if IS_WIN:
            out = subprocess.run(
                ["netstat", "-ano"], capture_output=True
            ).stdout.decode("gbk", errors="ignore")
            for line in out.splitlines():
                if "LISTENING" not in line:
                    continue
                parts = line.split()
                if len(parts) >= 5 and parts[1].endswith(f":{port}"):
                    pids.add(int(parts[-1]))
        else:
            out = subprocess.run(
                ["lsof", "-ti", f"tcp:{port}", "-sTCP:LISTEN"],
                capture_output=True,
            ).stdout.decode("utf-8", errors="ignore")
            pids = {int(x) for x in out.split() if x.strip().isdigit()}
    except Exception:
        pass
    return sorted(pids)


def kill_pid(pid: int) -> bool:
    try:
        if IS_WIN:
            r = subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                capture_output=True,
            )
            return r.returncode == 0
        os.kill(pid, 15)
        return True
    except Exception:
        return False


def free_port(port: int, label: str, force: bool = False) -> bool:
    """端口若被占用则回收。返回 True 表示现在端口空闲。

    force=True 时即使当下探测不到占用，也按 netstat 结果再清一遍
    （用于 --stop-first：清掉可能刚进入 TIME_WAIT / 亚健康状态的旧进程）。
    """
    if not force and not port_in_use(port):
        return True
    pids = pids_on_port(port)
    if not pids:
        if not port_in_use(port):
            return True
        say(f"  ! {label} 端口 {port} 被占用，但取不到 PID，请手动处理")
        return False
    say(f"  · {label} 端口 {port} 被占用，回收 PID {pids}")
    for pid in pids:
        kill_pid(pid)
    for _ in range(20):
        if not port_in_use(port):
            say(f"  ✓ 端口 {port} 已释放")
            return True
        time.sleep(0.3)
    say(f"  ! 端口 {port} 回收超时")
    return False


def wait_http(url: str, timeout: float, label: str) -> bool:
    """轮询直到 url 返回 2xx/3xx/4xx（4xx 也算服务已起，只是路由不存在）。"""
    import urllib.error
    import urllib.request

    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=3) as r:
                if r.status < 500:
                    return True
        except urllib.error.HTTPError as e:
            if e.code < 500:
                return True
        except Exception:
            pass
        time.sleep(0.5)
    say(f"  ! {label} 在 {timeout:.0f}s 内未就绪（{url}）")
    return False


def find_node() -> str | None:
    for cand in [
        shutil.which("node"),
        r"C:\Users\151661\.workbuddy\binaries\node\versions\22.22.2-3\node.exe",
    ]:
        if cand and Path(cand).exists():
            return cand
    return None


def spawn(cmd: list[str], cwd: Path, log_name: str) -> subprocess.Popen:
    LOGS.mkdir(exist_ok=True)
    log = open(LOGS / log_name, "ab", buffering=0)
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    proc = subprocess.Popen(
        cmd,
        cwd=str(cwd),
        stdout=log,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
        env=env,
        creationflags=CREATE_DETACHED,
    )
    say(f"  ✓ 已启动 PID {proc.pid} → logs/{log_name}")
    return proc


# --------------------------------------------------------------------------- 准备
def ensure_backend_env() -> bool:
    env_file = BACKEND / ".env"
    if env_file.exists():
        say("  ✓ backend/.env 已存在")
        return True
    example = BACKEND / ".env.example"
    if not example.exists():
        say("  ! 缺少 backend/.env.example，无法生成 .env")
        return False
    shutil.copyfile(example, env_file)
    say("  ✓ 已由 .env.example 生成 backend/.env（DATA_MODE=seed，用内置演示数据）")
    return True


def check_backend_deps() -> bool:
    try:
        import fastapi  # noqa: F401
        import uvicorn  # noqa: F401

        return True
    except ImportError as exc:
        say(f"  ! 缺少后端依赖（{exc.name}）。请先执行：")
        say(f"    {sys.executable} -m pip install -r backend/requirements.txt")
        return False


def ensure_frontend_build(rebuild: bool) -> bool:
    node = find_node()
    if not node:
        say("  ! 未找到 node，请安装 Node.js >= 18.17")
        return False
    if not (FRONTEND / "node_modules").is_dir():
        say("  · 安装前端依赖 npm install …（首次较慢）")
        r = subprocess.run([node, "npm", "install"], cwd=str(FRONTEND))
        if r.returncode != 0:
            say("  ! npm install 失败")
            return False
    build_id = FRONTEND / ".next" / "BUILD_ID"
    if build_id.exists() and not rebuild:
        say(f"  ✓ 复用已有生产构建 BUILD_ID={build_id.read_text().strip()}")
        return True
    say("  · 构建前端 next build …")
    next_bin = FRONTEND / "node_modules" / "next" / "dist" / "bin" / "next"
    r = subprocess.run([node, str(next_bin), "build"], cwd=str(FRONTEND))
    if r.returncode != 0:
        say("  ! 前端构建失败，见上方输出")
        return False
    say("  ✓ 前端构建完成")
    return True


# --------------------------------------------------------------------------- 主流程
def do_stop() -> int:
    say("停止服务：")
    free_port(BACKEND_PORT, "后端")
    free_port(FRONTEND_PORT, "前端")
    say("完成。")
    return 0


def do_start(args) -> int:
    say("=" * 62)
    say("采选美妆 AI · 本地启动")
    say("=" * 62)

    procs: list[tuple[str, subprocess.Popen]] = []

    if not args.frontend_only:
        say("\n[1/3] 准备后端")
        if not check_backend_deps():
            return 1
        ensure_backend_env()
        if not free_port(BACKEND_PORT, "后端", force=args.stop_first):
            return 1
        say("\n[2/3] 启动后端")
        procs.append(
            (
                "后端",
                spawn(
                    [
                        sys.executable,
                        "-m",
                        "uvicorn",
                        "main:app",
                        "--host",
                        "127.0.0.1",
                        "--port",
                        str(BACKEND_PORT),
                    ],
                    BACKEND,
                    "backend.log",
                ),
            )
        )
        if not wait_http(
            f"http://127.0.0.1:{BACKEND_PORT}/healthz", 60, "后端"
        ):
            return 1
        say(f"  ✓ 后端就绪 http://127.0.0.1:{BACKEND_PORT}")

    if not args.backend_only:
        say("\n[3/3] 准备并启动前端")
        if not ensure_frontend_build(args.rebuild):
            return 1
        if not free_port(FRONTEND_PORT, "前端", force=args.stop_first):
            return 1
        node = find_node()
        next_bin = FRONTEND / "node_modules" / "next" / "dist" / "bin" / "next"
        cmd = [
            node,
            str(next_bin),
            "dev" if args.dev else "start",
            "-p",
            str(FRONTEND_PORT),
            "-H",
            "127.0.0.1",
        ]
        procs.append(("前端", spawn(cmd, FRONTEND, "frontend.log")))
        if not wait_http(f"http://127.0.0.1:{FRONTEND_PORT}/", 120, "前端"):
            return 1
        say(f"  ✓ 前端就绪 http://127.0.0.1:{FRONTEND_PORT}")

    say("\n" + "=" * 62)
    say("已就绪，可直接验证：")
    if not args.backend_only:
        say(f"  产品界面      http://127.0.0.1:{FRONTEND_PORT}/")
        say(f"  比价看板      http://127.0.0.1:{FRONTEND_PORT}/compare?q=小棕瓶")
        say(f"  行情曲线      http://127.0.0.1:{FRONTEND_PORT}/trend?q=小棕瓶")
        say(f"  降价订阅      http://127.0.0.1:{FRONTEND_PORT}/alert")
        say(f"  我的          http://127.0.0.1:{FRONTEND_PORT}/my")
    if not args.frontend_only:
        say(f"  接口文档      http://127.0.0.1:{BACKEND_PORT}/docs")
        say(f"  数据源现状    http://127.0.0.1:{BACKEND_PORT}/api/compare/sources")
    say("")
    say(f"  日志          logs/backend.log  ·  logs/frontend.log")
    say(f"  停止服务      {sys.executable} start.py --stop")
    say("=" * 62)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description="采选美妆 AI 本地一键启动",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--stop", action="store_true", help="停止占用端口的服务")
    ap.add_argument("--stop-first", action="store_true", help="启动前强制回收端口")
    ap.add_argument("--dev", action="store_true", help="前端用 next dev（热更新）")
    ap.add_argument("--rebuild", action="store_true", help="强制重新构建前端")
    ap.add_argument("--backend-only", action="store_true", help="只启动后端")
    ap.add_argument("--frontend-only", action="store_true", help="只启动前端")
    args = ap.parse_args()

    if args.stop:
        return do_stop()
    return do_start(args)


if __name__ == "__main__":
    sys.exit(main())
