import os
import tempfile

# 必须在任何 app 模块导入之前钉死测试库，保证测试不碰真实 Postgres。
_TMP = tempfile.mkdtemp(prefix="vendfill_test_")
os.environ["DATABASE_URL"] = f"sqlite:///{_TMP}/test.db"
os.environ["SEED_ON_EMPTY"] = "true"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.main import app


@pytest.fixture(scope="session")
def client():
    """带 lifespan 的客户端：建表（含 CHECK 约束）+ 迁移 + 种子。"""
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def db(client):
    from app.database import SessionLocal
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def empty_client():
    """指向全新空库（无点位、无种子）的客户端，用于无点位失败场景。"""
    path = os.path.join(tempfile.mkdtemp(prefix="vendfill_empty_"), "empty.db")
    eng = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(eng)
    Session = sessionmaker(bind=eng)

    def override():
        s = Session()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = override
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()
