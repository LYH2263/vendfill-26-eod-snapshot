import hashlib
import json
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.models import EodExport, Lane, Location, RefillOrder
from app.services.fill_engine import build_eod_package, build_fill_lines, summarize

router = APIRouter(prefix="/refills", tags=["refills"])

# 两套失败必须用两套码，不得混：
#   LOCATION_NOT_FOUND            —— 无点位，导出动作本身失败
#   EXPORT_SNAPSHOT_REFRESHED     —— 导出曾成功，但冻结包在库里被回刷/篡改
ERR_NO_LOCATION = "LOCATION_NOT_FOUND"
ERR_PACKAGE_REFRESHED = "EXPORT_SNAPSHOT_REFRESHED"
ERR_NO_EXPORT = "EOD_EXPORT_NOT_FOUND"


def _fail(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status, detail={"code": code, "message": message})


def _get_location(db: Session, location_id: int) -> Location:
    loc = db.get(Location, location_id)
    if not loc:
        raise _fail(404, ERR_NO_LOCATION, f"点位 {location_id} 不存在，无法导出")
    return loc


def _lanes_snapshot(db: Session, location_id: int) -> list[dict]:
    """读取当前库存的一次性快照；调用方拿到后与之后的库存变化无关。"""
    rows = db.scalars(
        select(Lane).where(Lane.location_id == location_id).order_by(Lane.slot_no)
    ).all()
    return [{"id": l.id, "slot_no": l.slot_no, "sku_name": l.sku_name,
             "capacity": l.capacity, "stock": l.stock, "in_transit": l.in_transit}
            for l in rows]


def _checksum(payload: dict) -> str:
    # 规范化序列化，使校验只取决于内容而非空白/键序
    blob = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


@router.post("/run")
def run_refill(location_id: int = 1, db: Session = Depends(get_db)):
    """生成补货单：永远按当下库存计算，跟新库存。与日终冻结包互不相干。"""
    _get_location(db, location_id)
    snapshot = _lanes_snapshot(db, location_id)
    summary = summarize(build_fill_lines(snapshot))
    order = RefillOrder(location_id=location_id, created_at=datetime.utcnow(),
                        lines_json=json.dumps(summary, ensure_ascii=False))
    db.add(order)
    db.commit()
    db.refresh(order)
    return {"id": order.id, "location_id": location_id, **summary}


@router.get("/latest")
def latest(location_id: int = 1, db: Session = Depends(get_db)):
    _get_location(db, location_id)
    order = db.scalars(select(RefillOrder).where(RefillOrder.location_id == location_id)
                       .order_by(RefillOrder.id.desc())).first()
    if not order:
        return run_refill(location_id=location_id, db=db)
    data = json.loads(order.lines_json)
    return {"id": order.id, "location_id": location_id, **data}


@router.post("/eod-exports")
def create_eod_export(location_id: int = 1, db: Session = Depends(get_db)):
    """日终导出一份钉死的口径包（待补总件数 / 满仓货道 / 超占货道）。

    只把快照追加写入 eod_exports，绝不回写任何库存；导出之后库存再变，
    本包保持原样。无点位走 LOCATION_NOT_FOUND（404）。
    """
    _get_location(db, location_id)
    package = build_eod_package(_lanes_snapshot(db, location_id))
    record = EodExport(
        location_id=location_id,
        exported_at=datetime.utcnow(),
        payload_json=json.dumps(package, ensure_ascii=False),
        payload_checksum=_checksum(package),
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return {"id": record.id, "location_id": location_id,
            "exported_at": record.exported_at.isoformat(), **package}


def _load_frozen_export(db: Session, export_id: int) -> EodExport:
    record = db.get(EodExport, export_id)
    if not record:
        raise _fail(404, ERR_NO_EXPORT, f"日终导出 {export_id} 不存在")
    try:
        payload = json.loads(record.payload_json)
    except (ValueError, TypeError):
        raise _fail(409, ERR_PACKAGE_REFRESHED, "导出包内容损坏，已不是导出瞬间的口径")
    if not isinstance(payload, dict) or _checksum(payload) != record.payload_checksum:
        # 导出成功过，但落库的包被回刷/篡改 —— 与无点位的失败严格分开
        raise _fail(409, ERR_PACKAGE_REFRESHED,
                    "导出包已被回刷，与导出瞬间钉死的口径不一致")
    return record


@router.get("/eod-exports/latest")
def latest_eod_export(location_id: int = 1, db: Session = Depends(get_db)):
    _get_location(db, location_id)
    record = db.scalars(
        select(EodExport).where(EodExport.location_id == location_id)
        .order_by(EodExport.id.desc())
    ).first()
    if not record:
        raise _fail(404, ERR_NO_EXPORT, "该点位尚无日终导出")
    return _serialize_export(_load_frozen_export(db, record.id))


def _serialize_export(record: EodExport) -> dict:
    return {"id": record.id, "location_id": record.location_id,
            "exported_at": record.exported_at.isoformat(),
            **json.loads(record.payload_json)}


@router.get("/eod-exports/{export_id}")
def get_eod_export(export_id: int, db: Session = Depends(get_db)):
    record = _load_frozen_export(db, export_id)
    return _serialize_export(record)


@router.get("/full")
def full_lanes(location_id: int = 1, db: Session = Depends(get_db)):
    """实时视图：按当前库存计算满仓名单，超占道（gap<0）不在其中。"""
    _get_location(db, location_id)
    package = build_eod_package(_lanes_snapshot(db, location_id))
    return {"location_id": location_id, "lanes": package["full_lanes"]}


@router.get("/summary")
def refill_summary(location_id: int = 1, db: Session = Depends(get_db)):
    """实时视图：跟当前库存走，不读冻结包。"""
    _get_location(db, location_id)
    package = build_eod_package(_lanes_snapshot(db, location_id))
    return {
        "location_id": location_id,
        "total_fill": package["total_fill"],
        "need_fill_count": package["need_fill_count"],
        "full_count": package["full_count"],
        "overbooked_count": package["overbooked_count"],
    }
