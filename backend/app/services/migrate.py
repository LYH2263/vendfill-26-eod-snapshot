"""轻量迁移：为已存在的库补齐货道 CHECK 约束（幂等）。

新库由 Base.metadata.create_all 直接带出约束；本模块只负责老库补钉。
约束刻意不含 stock/in_transit <= capacity，合法超占道不受影响。
"""
from sqlalchemy import text
from sqlalchemy.engine import Engine

LANE_CHECKS = [
    ("ck_lanes_capacity_positive", "capacity > 0"),
    ("ck_lanes_stock_nonnegative", "stock >= 0"),
    ("ck_lanes_in_transit_nonnegative", "in_transit >= 0"),
]


def run_migrations(engine: Engine) -> None:
    if engine.dialect.name != "postgresql":
        # SQLite 等不支持 ALTER TABLE ADD CONSTRAINT；新库已由 create_all 带齐约束。
        return
    with engine.begin() as conn:
        for name, expr in LANE_CHECKS:
            conn.execute(text(
                "DO $$ BEGIN "
                f"IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = '{name}') THEN "
                f"ALTER TABLE lanes ADD CONSTRAINT {name} CHECK ({expr}); "
                "END IF; "
                "END $$"
            ))
