"""pytest 全局装配。

关键点：``core.config.settings`` 是模块级单例，必须**先设好环境变量再导入应用**，
否则测试会连到开发库。因此环境准备写在本文件模块顶层（import 时即执行）。
"""
from __future__ import annotations

import os
import pathlib
import shutil
import sys
import tempfile

BACKEND_DIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))
os.chdir(BACKEND_DIR)

# ---- 测试环境隔离：临时库 + 关闭定时任务 + 收敛 CORS ----
_TMP = pathlib.Path(tempfile.mkdtemp(prefix="caixuan_test_"))
os.environ["SQLITE_PATH"] = str(_TMP / "test.db")
os.environ["DATABASE_URL"] = ""
os.environ["DATA_MODE"] = "seed"
os.environ["POLL_ENABLED"] = "false"
os.environ["PUSH_ENABLED"] = "false"
os.environ["CORS_ORIGINS"] = "http://testserver,http://localhost:3000"
os.environ["LOG_LEVEL"] = "WARNING"
os.environ["ENV"] = "dev"
os.environ["DEBUG"] = "false"
# 清掉可能从外部注入的联盟凭据，保证测试跑在「未接入」的诚实分支上
for _k in (
    "TMALL_UNION_APP_KEY", "TMALL_UNION_APP_SECRET", "TMALL_UNION_PID",
    "JD_UNION_APP_KEY", "JD_UNION_APP_SECRET", "JD_UNION_PID",
    "PDD_DUO_APP_KEY", "PDD_DUO_APP_SECRET", "PDD_DUO_PID",
    "VIP_UNION_APP_KEY", "VIP_UNION_APP_SECRET", "VIP_UNION_PID",
    "BONDED_API_BASE", "BONDED_API_KEY",
    "WECHAT_MP_APP_ID", "WECHAT_MP_APP_SECRET", "WECHAT_MP_TEMPLATE_ID",
    "WECHAT_MINI_APP_ID", "WECHAT_MINI_APP_SECRET", "WECHAT_MINI_TEMPLATE_ID",
):
    os.environ.pop(_k, None)

import pytest  # noqa: E402


@pytest.fixture(scope="session")
def app_module():
    import main

    return main


@pytest.fixture(scope="session")
def client(app_module):
    """带 lifespan 的 TestClient —— 会真实跑迁移与启动钩子。"""
    from fastapi.testclient import TestClient

    with TestClient(app_module.app) as c:
        yield c


@pytest.fixture(scope="session")
def session_id(client) -> str:
    """一个匿名设备会话，供订阅相关用例复用。"""
    r = client.post("/api/auth/session", json={"device_id": "pytest-device-0001"})
    assert r.status_code == 200, r.text
    return r.json()["session_id"]


@pytest.fixture(scope="session")
def headers(session_id) -> dict:
    return {"X-Session-Id": session_id}


def pytest_sessionfinish(session, exitstatus):
    shutil.rmtree(_TMP, ignore_errors=True)
