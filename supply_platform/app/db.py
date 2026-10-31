"""数据库引擎与会话管理。

MVP 阶段使用 SQLite 文件库（零外部依赖）。生产环境可在此处切换为
Postgres/MySQL 连接串，业务代码无需改动。
"""
from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

# SQLite 文件库路径：默认 supply_platform/app/supply.db
# 可通过环境变量 SUPPLY_DB_PATH 覆盖（测试时使用临时库）
BASE_DIR = Path(__file__).resolve().parent
DB_PATH = Path(os.environ.get("SUPPLY_DB_PATH", str(BASE_DIR / "supply.db")))
DATABASE_URL = f"sqlite:///{DB_PATH}"

# check_same_thread=False 便于 FastAPI 多线程访问；MVP 足够。
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
    future=True,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


class Base(DeclarativeBase):
    """所有 ORM 模型的基类。"""


def get_db() -> Session:
    """FastAPI 依赖：提供请求级数据库会话，自动关闭。"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """建表（幂等）。在应用启动时调用。"""
    # 导入模型以确保它们注册到 Base.metadata
    from app import models  # noqa: F401
    Base.metadata.create_all(bind=engine)
