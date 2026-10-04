"""日终口径包：钉死导出、不被回写、两套失败分开、迁完种子仍能生成。"""
import json

from app.database import SessionLocal, engine
from app.main import app
from app.models.models import EodExport
from app.services.migrate import run_migrations

GUM = "口香糖"


def _gum(rows):
    return [r for r in rows if r["sku_name"] == GUM]


def test_seed_export_gum_overbooked_not_full(client):
    r = client.post("/api/exports/eod")
    assert r.status_code == 201, r.text
    data = r.json()
    # 种子导出时口香糖那道在超占侧、不在满仓侧
    assert len(_gum(data["overbooked_lanes"])) == 1
    assert _gum(data["full_lanes"]) == []
    assert _gum(data["overbooked_lanes"])[0]["gap"] < 0
    assert data["total_fill"] > 0
    assert data["location_count"] == 1


def test_export_pinned_after_stock_change(client):
    pinned = client.post("/api/exports/eod").json()
    lanes = client.get("/api/lanes").json()
    a1 = next(l for l in lanes if l["slot_no"] == "A1")
    a1_gap = a1["capacity"] - a1["stock"] - a1["in_transit"]

    # 导出之后再改库存：A1 补到满仓
    r = client.patch(f"/api/lanes/{a1['id']}", json={"stock": a1["capacity"]})
    assert r.status_code == 200, r.text

    # 这份包不得被回写成新库存
    again = client.get("/api/exports/eod/latest")
    assert again.status_code == 200
    assert again.json() == pinned

    # 货道页可以跟新
    lanes_after = client.get("/api/lanes").json()
    assert next(l for l in lanes_after if l["slot_no"] == "A1")["stock"] == a1["capacity"]

    # 之后新生成的单可以跟新
    run = client.post("/api/refills/run?location_id=1").json()
    a1_line = next(l for l in run["lines"] if l["slot_no"] == "A1")
    assert a1_line["status"] == "full"
    assert a1_line["fill_qty"] == 0
    assert run["total_fill"] == pinned["total_fill"] - a1_gap


def test_no_locations_and_tampered_are_distinct_failures(client, empty_client):
    # 失败一：无点位导出失败
    r = empty_client.post("/api/exports/eod")
    assert r.status_code == 409
    status_no_locations = r.status_code
    code_no_locations = r.json()["detail"]["code"]
    assert code_no_locations == "EOD_NO_LOCATIONS"

    # 空库场景结束，主客户端回到种子库（override 是 app 级全局）
    app.dependency_overrides.clear()

    # 失败二：导出成功但包被回刷
    r = client.post("/api/exports/eod")
    assert r.status_code == 201
    export_id = r.json()["id"]
    session = SessionLocal()
    try:
        row = session.get(EodExport, export_id)
        original = row.payload_json
        tampered = json.loads(original)
        tampered["total_fill"] = 999999
        row.payload_json = json.dumps(tampered, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        session.commit()

        r2 = client.get("/api/exports/eod/latest")
        assert r2.status_code == 500
        code_tampered = r2.json()["detail"]["code"]
        assert code_tampered == "EOD_SNAPSHOT_TAMPERED"

        # 两套失败，不得混成一个码（业务码与 HTTP 状态都不同）
        assert code_no_locations != code_tampered
        assert status_no_locations != r2.status_code

        # 恢复现场，别污染后续用例
        row = session.get(EodExport, export_id)
        row.payload_json = original
        session.commit()
    finally:
        session.close()
    assert client.get("/api/exports/eod/latest").status_code == 200


def test_latest_without_any_export_404(empty_client):
    r = empty_client.get("/api/exports/eod/latest")
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "EOD_EXPORT_NOT_FOUND"


def test_migrate_then_seed_then_generate_and_full_excludes_gum(client):
    # 迁移幂等可重入；迁完种子后仍能生成
    run_migrations(engine)
    run = client.post("/api/refills/run?location_id=1")
    assert run.status_code == 200, run.text

    # 满仓名单仍不含超占道
    full = client.get("/api/refills/full?location_id=1").json()["lanes"]
    assert all(l["sku_name"] != GUM for l in full)

    exp = client.post("/api/exports/eod")
    assert exp.status_code == 201
    assert len(_gum(exp.json()["overbooked_lanes"])) == 1
    assert _gum(exp.json()["full_lanes"]) == []
