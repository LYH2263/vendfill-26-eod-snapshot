import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.database as db_mod
from app.config import settings
from app.database import Base, get_db
from app.main import app
from app.services.seed import seed_if_empty


@pytest.fixture()
def engine():
    """共享连接的内存 sqlite；CHECK 约束随 create_all 一并建出。"""
    test_engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=test_engine)
    TestSession = sessionmaker(bind=test_engine, autoflush=False, autocommit=False)
    db = TestSession()
    seed_if_empty(db)  # 迁库种子场景：先播种
    db.close()

    original_engine = db_mod.engine
    db_mod.engine = test_engine  # lifespan 里 ensure_schema 改用测试引擎
    original_seed_flag = settings.seed_on_empty
    settings.seed_on_empty = False  # seed 已手动完成，lifespan 不得再连原引擎
    try:
        yield test_engine
    finally:
        settings.seed_on_empty = original_seed_flag
        db_mod.engine = original_engine
        Base.metadata.drop_all(bind=test_engine)


@pytest.fixture()
def client(engine):
    TestSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    def override_get_db():
        s = TestSession()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:  # 触发 lifespan：ensure_schema 走测试 sqlite
        yield c
    app.dependency_overrides.clear()


@pytest.fixture()
def session(engine):
    TestSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    s = TestSession()
    try:
        yield s
    finally:
        s.close()
