import json

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from app.models.models import EodExport, Lane, Location


# ---------- 种子：口香糖在超占侧、不在满仓侧 ----------

def test_seed_gum_is_overbooked_not_full(session, client):
    resp = client.post("/api/refills/eod-exports?location_id=1")
    assert resp.status_code == 200
    pack = resp.json()
    full_ids = {l["lane_id"] for l in pack["full_lanes"]}
    over_ids = {l["lane_id"] for l in pack["overbooked_lanes"]}
    gum = session.scalars(select(Lane).where(Lane.sku_name == "口香糖")).first()
    assert gum is not None
    assert gum.id in over_ids          # 24 库存 + 2 在途 > 24 容量 → 超占
    assert gum.id not in full_ids      # 绝不能同时出现在满仓侧
    # 满仓侧只有真正 gap==0 的（可乐 18/18）
    assert full_ids == {
        l.id for l in session.scalars(select(Lane)).all()
        if l.stock + l.in_transit == l.capacity
    }
    assert pack["full_count"] == len(full_ids)
    assert pack["overbooked_count"] == 1


# ---------- 导出钉死：导出后改库存，包不被回写 ----------

def test_export_is_frozen_after_stock_change(session, client):
    pack1 = client.post("/api/refills/eod-exports?location_id=1").json()

    # 导出之后再改库存（待补总量随之变化）
    gum = session.scalars(select(Lane).where(Lane.sku_name == "口香糖")).first()
    gum.stock = 30
    water = session.scalars(select(Lane).where(Lane.sku_name == "矿泉水")).first()
    water.stock = 20  # 矿泉水从缺口 15 变成满仓
    session.commit()

    # 冻结包原样不变，不被回刷
    frozen = client.get(f"/api/refills/eod-exports/{pack1['id']}").json()
    assert frozen["total_fill"] == pack1["total_fill"]
    frozen_full = {l["lane_id"] for l in frozen["full_lanes"]}
    assert water.id not in frozen_full
    assert {l["lane_id"] for l in frozen["overbooked_lanes"]} == {gum.id}

    # 实时视图（货道页满仓名单 / 汇总 / 新单）跟新库存
    full_now = client.get("/api/refills/full?location_id=1").json()
    assert water.id in {l["lane_id"] for l in full_now["lanes"]}
    assert gum.id not in {l["lane_id"] for l in full_now["lanes"]}

    summary_now = client.get("/api/refills/summary?location_id=1").json()
    assert summary_now["total_fill"] != pack1["total_fill"]

    new_order = client.post("/api/refills/run?location_id=1").json()
    water_line = next(l for l in new_order["lines"] if l["lane_id"] == water.id)
    assert water_line["status"] == "full"
    # 新单与冻结包是两套东西：新单按新库存，冻结包保持导出瞬间口径
    assert new_order["total_fill"] == summary_now["total_fill"]
    assert new_order["total_fill"] != pack1["total_fill"]


def test_export_never_writes_back_stock(session, client):
    before = {l.id: (l.stock, l.in_transit) for l in session.scalars(select(Lane)).all()}
    client.post("/api/refills/eod-exports?location_id=1")
    session.expire_all()
    after = {l.id: (l.stock, l.in_transit) for l in session.scalars(select(Lane)).all()}
    assert before == after  # 导出动作绝不回写库存


# ---------- 两套失败码：无点位 vs 包被回刷 ----------

def test_export_without_location_is_not_found_code(client):
    resp = client.post("/api/refills/eod-exports?location_id=999")
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "LOCATION_NOT_FOUND"


def test_refreshed_package_is_distinct_code(session, client):
    pack = client.post("/api/refills/eod-exports?location_id=1").json()
    # 外部把落库的包回刷成另一套口径（导出成功后的篡改）
    row = session.get(EodExport, pack["id"])
    tampered = json.loads(row.payload_json)
    tampered["total_fill"] = tampered["total_fill"] + 999
    row.payload_json = json.dumps(tampered, ensure_ascii=False)
    session.commit()

    resp = client.get(f"/api/refills/eod-exports/{pack['id']}")
    assert resp.status_code == 409
    code = resp.json()["detail"]["code"]
    assert code == "EXPORT_SNAPSHOT_REFRESHED"
    assert code != "LOCATION_NOT_FOUND"  # 两套失败不得混成一个码


# ---------- 应用层 + 数据库约束 ----------

@pytest.mark.parametrize("field,bad", [("capacity", 0), ("stock", -1), ("in_transit", -1)])
def test_application_layer_rejects_bad_values(session, field, bad):
    loc = session.scalars(select(Location)).first()
    with pytest.raises(ValueError):
        Lane(location_id=loc.id, slot_no="Z9", sku_name="x",
             **{"capacity": 10, "stock": 0, "in_transit": 0, field: bad})


def test_db_check_constraints_enforced(session):
    loc = session.scalars(select(Location)).first()
    # 绕过 @validates：插一条合法行后再用裸 SQL 置非法值
    lane = Lane(location_id=loc.id, slot_no="Q1", sku_name="坚果",
                capacity=10, stock=5, in_transit=0)
    session.add(lane)
    session.commit()

    for sql, msg in [
        ("UPDATE lanes SET capacity = 0 WHERE id = :id", "capacity"),
        ("UPDATE lanes SET stock = -1 WHERE id = :id", "stock"),
        ("UPDATE lanes SET in_transit = -1 WHERE id = :id", "in_transit"),
    ]:
        with pytest.raises(IntegrityError):
            session.execute(text(sql), {"id": lane.id})
            session.commit()
        session.rollback()


def test_legal_overbooked_lane_must_exist(session, client):
    """合法超占道必须能存在：禁止为过库约束把它删掉或改口成满仓。"""
    loc = session.scalars(select(Location)).first()
    over = Lane(location_id=loc.id, slot_no="O1", sku_name="超占饼干",
                capacity=10, stock=9, in_transit=4)  # 合计 13 > 10
    session.add(over)
    session.commit()
    full = client.get("/api/refills/full?location_id=1").json()
    assert over.id not in {l["lane_id"] for l in full["lanes"]}
    pack = client.post("/api/refills/eod-exports?location_id=1").json()
    assert over.id in {l["lane_id"] for l in pack["overbooked_lanes"]}
    assert over.id not in {l["lane_id"] for l in pack["full_lanes"]}


# ---------- 迁完种子后仍能生成 ----------

def test_still_generates_after_seed_and_migration(client):
    # fixtures 里先 seed 再跑 lifespan 迁移；这里直接验证生成链路完好
    order = client.post("/api/refills/run?location_id=1")
    assert order.status_code == 200
    assert order.json()["id"] >= 1
    pack = client.post("/api/refills/eod-exports?location_id=1")
    assert pack.status_code == 200
    full = client.get("/api/refills/full?location_id=1").json()
    gum_over = any(l["slot_no"] == "C2" for l in full["lanes"])
    assert not gum_over  # 满仓名单仍不含超占道
