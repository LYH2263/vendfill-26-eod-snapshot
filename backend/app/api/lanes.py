from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.models import Lane, Location
from app.services.fill_engine import compute_gap
router = APIRouter(prefix="/lanes", tags=["lanes"])

# 应用层约束与库约束同口径：容量>0、库存/在途>=0；
# 但 stock 可以大于 capacity（合法超占道），此处刻意不拦。
class LaneIn(BaseModel):
    location_id: int
    slot_no: str = Field(min_length=1, max_length=16)
    sku_name: str = Field(min_length=1, max_length=64)
    capacity: int = Field(gt=0)
    stock: int = Field(default=0, ge=0)
    in_transit: int = Field(default=0, ge=0)

class LanePatch(BaseModel):
    sku_name: str | None = Field(default=None, min_length=1, max_length=64)
    capacity: int | None = Field(default=None, gt=0)
    stock: int | None = Field(default=None, ge=0)
    in_transit: int | None = Field(default=None, ge=0)

def _lane_out(r: Lane) -> dict:
    gap = compute_gap(r.capacity, r.stock, r.in_transit)
    return {"id": r.id, "location_id": r.location_id, "slot_no": r.slot_no, "sku_name": r.sku_name,
            "capacity": r.capacity, "stock": r.stock, "in_transit": r.in_transit, "gap": gap,
            "fill_pct": round(r.stock / r.capacity * 100, 1) if r.capacity else 0}

@router.get("")
def list_lanes(location_id: int | None = None, db: Session = Depends(get_db)):
    q = select(Lane).order_by(Lane.slot_no)
    if location_id is not None: q = q.where(Lane.location_id == location_id)
    return [_lane_out(r) for r in db.scalars(q).all()]

@router.post("", status_code=201)
def create_lane(body: LaneIn, db: Session = Depends(get_db)):
    if not db.get(Location, body.location_id):
        raise HTTPException(404, "点位不存在")
    lane = Lane(**body.model_dump())
    db.add(lane); db.commit(); db.refresh(lane)
    return _lane_out(lane)

@router.patch("/{lane_id}")
def update_lane(lane_id: int, body: LanePatch, db: Session = Depends(get_db)):
    lane = db.get(Lane, lane_id)
    if not lane:
        raise HTTPException(404, "货道不存在")
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(lane, field, value)
    db.commit(); db.refresh(lane)
    return _lane_out(lane)
