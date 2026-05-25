"""
后端测试公共 fixtures（PostgreSQL 业务侧：cases / confirmed_diagnosis）。

日志解析 / bundle 摄取相关测试已迁出至 ``backend/log_pipeline/tests/``，独立 conftest。
"""

import os
from datetime import datetime
from typing import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from main import app
from database import get_db
from models import Case
from models.base import Base


TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL", "sqlite:///:memory:")


@pytest.fixture(scope="function")
def test_db() -> Generator[Session, None, None]:
    connect_args = {}
    if TEST_DATABASE_URL.startswith("sqlite"):
        connect_args["check_same_thread"] = False

    engine = create_engine(
        TEST_DATABASE_URL,
        connect_args=connect_args,
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def client(test_db: Session, monkeypatch) -> TestClient:
    """提供绑定 SQLite 的 TestClient，并在 lifespan 中屏蔽真实 PG/Redis/embedding 依赖。"""
    def override_get_db():
        yield test_db

    # 屏蔽 lifespan 中对真实 PostgreSQL / Redis / embedding 索引的依赖
    import database as _database_module
    import main as _main_module

    monkeypatch.setattr(_database_module.db_manager, "initialize", lambda: None)
    monkeypatch.setattr(_database_module.db_manager, "create_tables", lambda: None)
    monkeypatch.setattr(_database_module.db_manager, "close", lambda: None)

    async def _noop_async() -> None:
        return None

    # tasks.client 是延迟导入，需 patch 模块属性
    import tasks.client as _tasks_client

    monkeypatch.setattr(_tasks_client, "get_task_client", _noop_async)
    monkeypatch.setattr(_tasks_client, "close_task_client", _noop_async)

    # log_pipeline 状态初始化使用真实磁盘路径（tmp 无关），保留；
    # 但 embedding 预热可能联网，禁用之
    monkeypatch.setattr(
        _main_module.vector_service, "load_embed_index", lambda _p: 0
    )

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def sample_case(test_db: Session) -> Case:
    case = Case(
        case_id="test_case_001",
        vin="TEST1234567890123",
        vehicle_model="Model X",
        issue_description="Test issue",
        status="active",
        created_at=datetime.utcnow(),
    )
    test_db.add(case)
    test_db.commit()
    test_db.refresh(case)
    return case
