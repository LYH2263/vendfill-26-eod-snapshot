"""容量>0、库存/在途>=0：应用层与数据库约束同时保住；合法超占道必须仍能存在。"""
import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.database import SessionLocal


def test_app_layer_rejects_bad_lane_values(client):
    base = {"location_id": 1, "slot_no": "T1", "sku_name": "测试", "stock": 0, "in_transit": 0}
    assert client.post("/api/lanes", json={**base, "capacity": 0}).status_code == 422
    assert client.post("/api/lanes", json={**base, "capacity": -3}).status_code == 422
    assert client.post("/api/lanes", json={**base, "capacity": 5, "stock": -1}).status_code == 422
    assert client.post("/api/lanes", json={**base, "capacity": 5, "in_transit": -1}).status_code == 422


def test_app_layer_patch_rejects_bad_values(client):
    lane_id = client.get("/api/lanes").json()[0]["id"]
    assert client.patch(f"/api/lanes/{lane_id}", json={"capacity": 0}).status_code == 422
    assert client.patch(f"/api/lanes/{lane_id}", json={"stock": -5}).status_code == 422
    assert client.patch(f"/api/lanes/{lane_id}", json={"in_transit": -2}).status_code == 422


def test_app_layer_allows_legal_overbooked(client):
    # 合法超占道（库存>容量）必须仍能存在，应用层不得误拦
    r = client.post("/api/lanes", json={
        "location_id": 1, "slot_no": "T9", "sku_name": "超占测试",
        "capacity": 5, "stock": 8, "in_transit": 0,
    })
    assert r.status_code == 201, r.text
    assert r.json()["gap"] == -3
    # 清理，保持现场干净
    session = SessionLocal()
    try:
        session.execute(text("DELETE FROM lanes WHERE slot_no = 'T9'"))
        session.commit()
    finally:
        session.close()


def _insert(db, slot_no, capacity, stock, in_transit):
    db.execute(text(
        "INSERT INTO lanes (location_id, slot_no, sku_name, capacity, stock, in_transit) "
        f"VALUES (1, '{slot_no}', '直插', {capacity}, {stock}, {in_transit})"
    ))
    db.flush()


def test_db_rejects_direct_insert_capacity_zero(db):
    with pytest.raises(IntegrityError):
        _insert(db, "X1", 0, 0, 0)
    db.rollback()


def test_db_rejects_direct_insert_negative_stock(db):
    with pytest.raises(IntegrityError):
        _insert(db, "X2", 5, -1, 0)
    db.rollback()


def test_db_rejects_direct_insert_negative_in_transit(db):
    with pytest.raises(IntegrityError):
        _insert(db, "X3", 5, 0, -2)
    db.rollback()


def test_db_allows_legal_overbooked_insert(db):
    # 禁止为了过库约束把超占道删掉或改口：直插合法超占必须成功
    _insert(db, "X4", 5, 9, 0)
    db.rollback()  # 验证可插即可，不留现场
