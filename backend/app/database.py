from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings

engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


# 已存在的库（迁库种子场景）create_all 不会补建 lanes 上的检查约束，
# 这里对 Postgres 幂等补加；约束名固定，存在即跳过。
# sqlite 的 create_all 直接按当前模型建表，天然带上约束，无需处理。


def ensure_schema() -> None:
    """create_all 建表后，对老库幂等补齐新增的检查约束。"""
    Base.metadata.create_all(bind=engine)
    if engine.dialect.name != "postgresql":
        return
    inspector = inspect(engine)
    if "lanes" not in inspector.get_table_names():
        return
    existing = {c["name"] for c in inspector.get_check_constraints("lanes")}
    wanted = {
        "ck_lanes_capacity_positive": "capacity > 0",
        "ck_lanes_stock_nonneg": "stock >= 0",
        "ck_lanes_in_transit_nonneg": "in_transit >= 0",
    }
    with engine.begin() as conn:
        for name, clause in wanted.items():
            if name in existing:
                continue
            # IF NOT EXISTS 仅约束名在 PG 中无对应子句，用 DO 块包住最稳妥
            conn.execute(text(
                "DO $$ BEGIN "
                f"ALTER TABLE lanes ADD CONSTRAINT {name} CHECK ({clause}); "
                "EXCEPTION WHEN duplicate_object THEN null; "
                "END $$;"
            ))


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
