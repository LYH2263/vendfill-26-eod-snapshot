"""Vending refill: gap = capacity - stock - in_transit; fills capped by gap; no negative fills."""
from __future__ import annotations
from dataclasses import asdict, dataclass

@dataclass
class FillLine:
    lane_id: int
    slot_no: str
    sku_name: str
    capacity: int
    stock: int
    in_transit: int
    gap: int
    fill_qty: int
    status: str  # need_fill | full | overbooked

def compute_gap(capacity: int, stock: int, in_transit: int) -> int:
    return capacity - stock - in_transit

def build_fill_lines(lanes: list[dict], requested: dict[int, int] | None = None) -> list[FillLine]:
    """requested optional desired fill per lane_id; capped by gap; never negative."""
    lines: list[FillLine] = []
    for lane in lanes:
        gap = compute_gap(int(lane["capacity"]), int(lane["stock"]), int(lane["in_transit"]))
        if gap < 0:
            status = "overbooked"
            fill = 0
        elif gap == 0:
            status = "full"
            fill = 0
        else:
            status = "need_fill"
            desire = gap if requested is None else int(requested.get(lane["id"], gap))
            fill = max(0, min(desire, gap))
        lines.append(FillLine(
            lane_id=lane["id"], slot_no=lane["slot_no"], sku_name=lane["sku_name"],
            capacity=lane["capacity"], stock=lane["stock"], in_transit=lane["in_transit"],
            gap=gap, fill_qty=fill, status=status,
        ))
    return lines

def summarize(lines: list[FillLine]) -> dict:
    return {
        "total_fill": sum(l.fill_qty for l in lines),
        "need_fill_count": sum(1 for l in lines if l.status == "need_fill"),
        "full_count": sum(1 for l in lines if l.status == "full"),
        "overbooked_count": sum(1 for l in lines if l.status == "overbooked"),
        "lines": [asdict(l) for l in lines],
    }


def _lane_brief(l: FillLine) -> dict:
    return {
        "lane_id": l.lane_id,
        "slot_no": l.slot_no,
        "sku_name": l.sku_name,
        "capacity": l.capacity,
        "stock": l.stock,
        "in_transit": l.in_transit,
        "gap": l.gap,
    }


def build_eod_package(lanes: list[dict]) -> dict:
    """导出瞬间钉死的日终口径包：待补总件数 / 满仓货道 / 超占货道。

    满仓与超占互斥：gap == 0 才进满仓，gap < 0 进超占，
    超占道永远不会出现在满仓名单里。包内容只与传入快照有关，
    调用方之后再改库存，本包不会随之变化。
    """
    lines = build_fill_lines(lanes)
    s = summarize(lines)
    return {
        "total_fill": s["total_fill"],
        "need_fill_count": s["need_fill_count"],
        "full_count": s["full_count"],
        "overbooked_count": s["overbooked_count"],
        "full_lanes": [_lane_brief(l) for l in lines if l.status == "full"],
        "overbooked_lanes": [_lane_brief(l) for l in lines if l.status == "overbooked"],
    }
