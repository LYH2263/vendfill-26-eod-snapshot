from datetime import datetime
from sqlalchemy import CheckConstraint, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base

class Location(Base):
    __tablename__ = "locations"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True)
    name: Mapped[str] = mapped_column(String(128))
    address: Mapped[str] = mapped_column(String(256), default="")

class Lane(Base):
    __tablename__ = "lanes"
    # 容量必须为正、库存与在途不得为负；但刻意不约束 stock/in_transit <= capacity，
    # 合法超占道（库存+在途超过容量）必须仍能存在。
    __table_args__ = (
        CheckConstraint("capacity > 0", name="ck_lanes_capacity_positive"),
        CheckConstraint("stock >= 0", name="ck_lanes_stock_nonnegative"),
        CheckConstraint("in_transit >= 0", name="ck_lanes_in_transit_nonnegative"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    location_id: Mapped[int] = mapped_column(ForeignKey("locations.id"))
    slot_no: Mapped[str] = mapped_column(String(16))
    sku_name: Mapped[str] = mapped_column(String(64))
    capacity: Mapped[int] = mapped_column(Integer)
    stock: Mapped[int] = mapped_column(Integer, default=0)
    in_transit: Mapped[int] = mapped_column(Integer, default=0)

class Sale(Base):
    __tablename__ = "sales"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    lane_id: Mapped[int] = mapped_column(ForeignKey("lanes.id"))
    qty: Mapped[int] = mapped_column(Integer)
    sold_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class RefillOrder(Base):
    __tablename__ = "refill_orders"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    location_id: Mapped[int] = mapped_column(ForeignKey("locations.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    lines_json: Mapped[str] = mapped_column(Text, default="[]")

class EodExport(Base):
    """日终口径包：导出瞬间钉死，之后库存变动不得回写本表。"""
    __tablename__ = "eod_exports"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    exported_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    location_count: Mapped[int] = mapped_column(Integer, default=0)
    total_fill: Mapped[int] = mapped_column(Integer, default=0)
    payload_json: Mapped[str] = mapped_column(Text, default="{}")
    sha256: Mapped[str] = mapped_column(String(64))
