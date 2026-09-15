"""定时任务：价格轮询（M3 真实行情积累 + M4 降价推送触发）。

为什么要它：
  · M3 的行情曲线要能从真实数据长出来，必须有人按固定节奏落价格快照；
  · M4 的降价提醒不能只在用户打开页面时才判断（那就不是提醒了）。

实现选择：APScheduler 的 BackgroundScheduler（单进程内），
一期单实例部署足够。多实例时任务会重复执行 —— 处理方式是把
``POLL_ENABLED`` 只在一个实例上置 true（部署文档已说明），
或后续换成独立的 worker 进程 + 分布式锁。
"""
from __future__ import annotations

import atexit
import logging

from core.config import settings

logger = logging.getLogger("caixuan.scheduler")

_scheduler = None


def _job_poll() -> None:
    """一轮价格轮询：刷新活跃订阅 → 命中则推送。"""
    from core.db import session_scope
    from services.alert import poll_active_subscriptions

    try:
        with session_scope() as db:
            result = poll_active_subscriptions(db)
        if result["checked"]:
            logger.info(
                "价格轮询完成：检查 %s 条订阅，命中 %s 条，推送 %s 条",
                result["checked"], result["triggered"], result["pushed"],
            )
    except Exception:      # pragma: no cover - 定时任务不允许把进程带崩
        logger.exception("价格轮询任务异常")


def start() -> bool:
    """启动调度器。返回是否成功启动（依赖缺失/被关闭时返回 False，不阻断服务启动）。"""
    global _scheduler
    if _scheduler is not None:
        return True
    if not settings.poll_enabled:
        logger.info("定时轮询已关闭（POLL_ENABLED=false）")
        return False
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        from apscheduler.triggers.interval import IntervalTrigger
    except ImportError:      # pragma: no cover - 依赖缺失时降级
        logger.warning("未安装 APScheduler，价格轮询不启动（不影响前台功能）")
        return False

    _scheduler = BackgroundScheduler(timezone="Asia/Shanghai", daemon=True)
    _scheduler.add_job(
        _job_poll,
        trigger=IntervalTrigger(minutes=max(1, settings.push_interval_minutes)),
        id="price_poll",
        name="价格轮询与降价推送",
        max_instances=1,
        coalesce=True,
        replace_existing=True,
    )
    _scheduler.start()
    logger.info("价格轮询已启动，间隔 %s 分钟", settings.push_interval_minutes)
    atexit.register(shutdown)
    return True


def shutdown() -> None:
    global _scheduler
    if _scheduler is not None:
        try:
            _scheduler.shutdown(wait=False)
        except Exception:      # pragma: no cover - 关闭期防御
            pass
        _scheduler = None
        logger.info("价格轮询已停止")


def status() -> dict:
    jobs = []
    if _scheduler is not None:
        for j in _scheduler.get_jobs():
            jobs.append({
                "id": j.id,
                "name": j.name,
                "next_run": j.next_run_time.isoformat() if j.next_run_time else None,
            })
    return {
        "running": _scheduler is not None,
        "enabled": settings.poll_enabled,
        "interval_minutes": settings.push_interval_minutes,
        "jobs": jobs,
    }


__all__ = ["shutdown", "start", "status"]
