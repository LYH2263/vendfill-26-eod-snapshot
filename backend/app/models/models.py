from datetime import datetime
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, validates
from app.database import Base


class Location(Base):
    __tablename__ = "locations"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True)
    name: Mapped[str] = mapped_column(String(128))
    address: Mapped[str] = mapped_column(String(256), default="")


class Lane(Base):
    """货道。容量必须为正；库存与在途不得为负。

    注意：不约束 stock + in_transit <= capacity —— 合法超占货道
    （已到货尚未消化的在途把总量顶过容量）必须仍能存在。
    """

    __tablename__ = "lanes"
    __table_args__ = (
        CheckConstraint("capacity > 0", name="ck_lanes_capacity_positive"),
        CheckConstraint("stock >= 0", name="ck_lanes_stock_nonneg"),
        CheckConstraint("in_transit >= 0", name="ck_lanes_in_transit_nonneg"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    location_id: Mapped[int] = mapped_column(ForeignKey("locations.id"))
    slot_no: Mapped[str] = mapped_column(String(16))
    sku_name: Mapped[str] = mapped_column(String(64))
    capacity: Mapped[int] = mapped_column(Integer)
    stock: Mapped[int] = mapped_column(Integer, default=0)
    in_transit: Mapped[int] = mapped_column(Integer, default=0)

    @validates("capacity")
    def _check_capacity(self, key, value):
        if value is None or int(value) <= 0:
            raise ValueError("货道容量必须大于 0")
        return int(value)

    @validates("stock")
    def _check_stock(self, key, value):
        if value is None or int(value) < 0:
            raise ValueError("库存不得为负")
        return int(value)

    @validates("in_transit")
    def _check_in_transit(self, key, value):
        if value is None or int(value) < 0:
            raise ValueError("在途不得为负")
        return int(value)


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
    """日终导出：只追加（append-only）。

    每行是导出瞬间钉死的一份口径包（待补总件数 / 满仓货道 / 超占货道）。
    导出之后库存再怎么变，这份包都原样保留，绝不回写、也不被库存回刷；
    payload_checksum 用于读取时发现落库内容被外部篡改。
    """

    __tablename__ = "eod_exports"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    location_id: Mapped[int] = mapped_column(ForeignKey("locations.id"))
    exported_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    payload_json: Mapped[str] = mapped_column(Text)
    payload_checksum: Mapped[str] = mapped_column(String(64))
