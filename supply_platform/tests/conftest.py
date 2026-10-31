"""Pytest 配置。

在导入 app 之前设置测试数据库路径（独立临时 SQLite 库），保证测试隔离。
"""
import os
import tempfile

# 必须在导入 app 之前确定测试数据库路径
_tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_tmp.close()
os.environ["SUPPLY_DB_PATH"] = _tmp.name

import pytest  # noqa: E402
from sqlalchemy import func, select  # noqa: E402

from app.db import Base, SessionLocal, engine  # noqa: E402
from app import models  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _init_db():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def session():
    """每个测试前清空业务表，保证隔离；返回绑定测试库的会话。"""
    with SessionLocal() as s:
        for tbl in reversed(Base.metadata.sorted_tables):
            s.execute(tbl.delete())
        s.commit()
    s2 = SessionLocal()
    try:
        yield s2
    finally:
        s2.close()
