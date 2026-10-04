"""日终口径包导出：导出瞬间钉死，之后库存变动不得回写。

两套失败严格分开（HTTP 状态与业务码都不同）：
- 409 EOD_NO_LOCATIONS      无点位，导出失败（导出根本没发生）
- 500 EOD_SNAPSHOT_TAMPERED 导出成功过，但包被回刷（服务端完整性校验不过）
"""
import hashlib
import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.models import EodExport, Lane, Location
from app.services.fill_engine import build_fill_lines

router = APIRouter(prefix="/exports", tags=["exports"])

CODE_NO_LOCATIONS = "EOD_NO_LOCATIONS"
CODE_SNAPSHOT_TAMPERED = "EOD_SNAPSHOT_TAMPERED"
CODE_NOT_FOUND = "EOD_EXPORT_NOT_FOUND"


def _canonical(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _lane_entry(line, location_id: int) -> dict:
    return {
        "lane_id": line.lane_id,
        "location_id": location_id,
        "slot_no": line.slot_no,
        "sku_name": line.sku_name,
        "capacity": line.capacity,
        "stock": line.stock,
        "in_transit": line.in_transit,
        "gap": line.gap,
    }


@router.post("/eod", status_code=201)
def export_eod(db: Session = Depends(get_db)):
    locations = db.scalars(select(Location).order_by(Location.id)).all()
    if not locations:
        raise HTTPException(
            status_code=409,
            detail={"code": CODE_NO_LOCATIONS, "message": "无点位，无法导出日终口径包"},
        )
    lanes = db.scalars(select(Lane).order_by(Lane.location_id, Lane.slot_no)).all()
    loc_of = {l.id: l.location_id for l in lanes}
    payload = [
        {"id": l.id, "slot_no": l.slot_no, "sku_name": l.sku_name,
         "capacity": l.capacity, "stock": l.stock, "in_transit": l.in_transit}
        for l in lanes
    ]
    lines = build_fill_lines(payload)
    content = {
        "location_count": len(locations),
        "total_fill": sum(l.fill_qty for l in lines),
        "full_lanes": [_lane_entry(l, loc_of[l.lane_id]) for l in lines if l.status == "full"],
        "overbooked_lanes": [_lane_entry(l, loc_of[l.lane_id]) for l in lines if l.status == "overbooked"],
    }
    body = _canonical(content)
    row = EodExport(
        exported_at=datetime.utcnow(),
        location_count=content["location_count"],
        total_fill=content["total_fill"],
        payload_json=body,
        sha256=_sha256(body),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"id": row.id, "exported_at": row.exported_at.isoformat(), "sha256": row.sha256, **content}


def _read_pinned(row: EodExport) -> dict:
    """只读已钉死的包，绝不按现库存重算；哈希不符即包被回刷。"""
    if _sha256(row.payload_json) != row.sha256:
        raise HTTPException(
            status_code=500,
            detail={"code": CODE_SNAPSHOT_TAMPERED, "message": "口径包被回刷，与导出瞬间不一致"},
        )
    data = json.loads(row.payload_json)
    return {"id": row.id, "exported_at": row.exported_at.isoformat(), "sha256": row.sha256, **data}


@router.get("/eod")
def list_eod_exports(db: Session = Depends(get_db)):
    rows = db.scalars(select(EodExport).order_by(EodExport.id.desc())).all()
    return [
        {"id": r.id, "exported_at": r.exported_at.isoformat(),
         "location_count": r.location_count, "total_fill": r.total_fill, "sha256": r.sha256}
        for r in rows
    ]


@router.get("/eod/latest")
def latest_eod_export(db: Session = Depends(get_db)):
    row = db.scalars(select(EodExport).order_by(EodExport.id.desc())).first()
    if not row:
        raise HTTPException(
            status_code=404,
            detail={"code": CODE_NOT_FOUND, "message": "尚未导出过日终口径包"},
        )
    return _read_pinned(row)


@router.get("/eod/{export_id}")
def get_eod_export(export_id: int, db: Session = Depends(get_db)):
    row = db.get(EodExport, export_id)
    if not row:
        raise HTTPException(
            status_code=404,
            detail={"code": CODE_NOT_FOUND, "message": "口径包不存在"},
        )
    return _read_pinned(row)
