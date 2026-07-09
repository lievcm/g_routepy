"""
Port of GDSWriter.hpp / GDSWriter.cpp, using KLayout (klayout.db) instead of
gdstk for all GDS shape creation.

KLayout's Python API is a thin, C++-backed binding (klayout.dbcore), so
shape creation here runs at native speed just like the original gdstk calls.

Unlike gdstk, KLayout addresses layers through a per-Layout ``layer(layer,
datatype) -> layer_index`` lookup, so every function here additionally takes
the ``klayout.db.Layout`` the cell belongs to.
"""
from __future__ import annotations

from typing import List, Sequence, Tuple

import klayout.db as db

from .routing_config import RoutingConfig
from .routing_grid import RoutingGrid
from .types import Node

Point = Tuple[float, float]


def _layer_index(layout: "db.Layout", layer: int, dtype: int) -> int:
    return layout.layer(layer, dtype)


def insert_rect(layout: "db.Layout", cell: "db.Cell",
                 lx: float, ly: float, hx: float, hy: float,
                 layer: int, dtype: int) -> None:
    li = _layer_index(layout, layer, dtype)
    cell.shapes(li).insert(db.DBox(lx, ly, hx, hy))


def insert_square(layout: "db.Layout", cell: "db.Cell",
                   cx: float, cy: float, half_side: float,
                   layer: int, dtype: int) -> None:
    insert_rect(layout, cell, cx - half_side, cy - half_side,
                cx + half_side, cy + half_side, layer, dtype)


def _remove_colin_points(pts: Sequence[Point]) -> List[Point]:
    if len(pts) < 3:
        return list(pts)

    out: List[Point] = [pts[0]]
    for i in range(1, len(pts) - 1):
        a, b, c = pts[i - 1], pts[i], pts[i + 1]
        # For rectilinear paths, collinear means the same axis is changing.
        # b is redundant if a->b and b->c are both horizontal or both vertical.
        ab_horiz = (a[1] == b[1])
        bc_horiz = (b[1] == c[1])
        if ab_horiz != bc_horiz:
            out.append(b)
    out.append(pts[-1])
    return out


def _place_run(layout: "db.Layout", cell: "db.Cell",
                points_pairs: Sequence[Point], lyr: int, rcfg: RoutingConfig) -> None:
    width = rcfg.get_route_width(lyr)
    layer, dtype = rcfg.get_gds(lyr)

    pts = _remove_colin_points(points_pairs)
    li = _layer_index(layout, layer, dtype)

    dpts = [db.DPoint(x, y) for x, y in pts]
    path = db.DPath(dpts, width, width / 2.0, width / 2.0)
    cell.shapes(li).insert(path)


def write_path_to_gds(layout: "db.Layout", cell: "db.Cell",
                       path: Sequence[Node], grid: RoutingGrid,
                       rcfg: RoutingConfig) -> None:
    if not path:
        return

    cur_lyr = path[0][2]
    c0, r0, _ = path[0]
    px0, py0 = grid.from_grid(c0, r0)
    latest_run: List[Point] = [(px0, py0)]

    for i in range(1, len(path)):
        c, r, l = path[i]
        px, py = grid.from_grid(c, r)

        if l != cur_lyr:
            if abs(l - cur_lyr) > 1:
                raise RuntimeError("Error: Tried to write invalid path to gds")

            if len(latest_run) > 1:
                _place_run(layout, cell, latest_run, cur_lyr, rcfg)

            lower, upper = (l, cur_lyr) if l < cur_lyr else (cur_lyr, l)

            size = rcfg.get_via_up_size(lower)
            l_width = max(rcfg.get_route_width(lower),
                          size + rcfg.get_via_up_enc(lower) * 2)
            u_width = max(rcfg.get_route_width(upper),
                          size + rcfg.get_via_down_enc(upper) * 2)
            l_lyr, l_dtyp = rcfg.get_gds(lower)
            u_lyr, u_dtyp = rcfg.get_gds(upper)
            v_lyr, v_dtyp = rcfg.get_via_up_gds(lower)

            insert_square(layout, cell, px, py, l_width / 2, l_lyr, l_dtyp)
            insert_square(layout, cell, px, py, size / 2, v_lyr, v_dtyp)
            insert_square(layout, cell, px, py, u_width / 2, u_lyr, u_dtyp)

            latest_run = []
            cur_lyr = l

        latest_run.append((px, py))

    if len(latest_run) > 1:
        _place_run(layout, cell, latest_run, cur_lyr, rcfg)