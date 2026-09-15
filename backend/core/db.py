"""数据库引擎、会话与轻量迁移。

开发默认 SQLite；生产把 DATABASE_URL 指向 Postgres 即可，代码无需改动。

迁移策略：不引入 Alembic，用「幂等 DDL 步骤 + schema_migrations 记录表」实现
可重放、可审计的迁移。对一期单服务上线足够，且零额外依赖；后续如需分支迁移
再叠加 Alembic（本模块的 Base 与连接可直接复用）。
"""
from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from core.config import settings

logger = logging.getLogger("caixuan.db")


class Base(DeclarativeBase):
    pass


def _ensure_sqlite_dir(url: str) -> None:
    if not url.startswith("sqlite:///"):
        return
    raw = url.replace("sqlite:///", "", 1)
    if raw in (":memory:", ""):
        return
    Path(raw).parent.mkdir(parents=True, exist_ok=True)
    if not os.path.isabs(raw):
        # 相对路径按当前工作目录（backend/）解析，保证可移植
        Path(raw).resolve().parent.mkdir(parents=True, exist_ok=True)


_engine = None
_SessionLocal: sessionmaker | None = None


def get_engine():
    global _engine, _SessionLocal
    if _engine is None:
        url = settings.sqlalchemy_url
        _ensure_sqlite_dir(url)
        kwargs: dict = {"echo": settings.db_echo, "future": True}
        if url.startswith("sqlite"):
            # SQLite 在 FastAPI 默认线程池下需要放开线程检查；并开启 WAL 提升并发读
            kwargs["connect_args"] = {"check_same_thread": False}
        else:
            kwargs.update({"pool_pre_ping": True, "pool_size": 10, "max_overflow": 20})
        _engine = create_engine(url, **kwargs)
        if url.startswith("sqlite"):
            with _engine.begin() as conn:
                conn.execute(text("PRAGMA journal_mode=WAL"))
                conn.execute(text("PRAGMA foreign_keys=ON"))
        _SessionLocal = sessionmaker(bind=_engine, autoflush=False, expire_on_commit=False)
        logger.info("数据库已连接：%s", url.split("@")[-1])
    return _engine


def get_session() -> Iterator[Session]:
    """FastAPI 依赖：请求级会话。"""
    if _SessionLocal is None:
        get_engine()
    assert _SessionLocal is not None
    db = _SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@contextmanager
def session_scope() -> Iterator[Session]:
    """脚本/任务里手动开事务作用域。"""
    if _SessionLocal is None:
        get_engine()
    assert _SessionLocal is not None
    db = _SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


# ---------------------------------------------------------------------------
# 迁移
# ---------------------------------------------------------------------------

_MIGRATIONS: list[tuple[str, str]] = [
    # (版本号, SQL) —— 只允许追加，不允许修改已发布条目
]


def run_migrations() -> None:
    """建表 + 应用增量迁移。可重复调用。"""
    from core import models  # noqa: F401  确保模型已注册到 Base.metadata

    engine = get_engine()
    Base.metadata.create_all(engine)

    with engine.begin() as conn:
        conn.execute(text(
            "CREATE TABLE IF NOT EXISTS schema_migrations ("
            " version VARCHAR(64) PRIMARY KEY,"
            " applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
        ))
        applied = {r[0] for r in conn.execute(text("SELECT version FROM schema_migrations"))}
        for version, sql in _MIGRATIONS:
            if version in applied:
                continue
            for stmt in [s.strip() for s in sql.split(";") if s.strip()]:
                conn.execute(text(stmt))
            conn.execute(
                text("INSERT INTO schema_migrations (version) VALUES (:v)"), {"v": version}
            )
            logger.info("已应用迁移 %s", version)

    tables = inspect(engine).get_table_names()
    logger.info("数据库就绪，表：%s", ", ".join(sorted(tables)))
