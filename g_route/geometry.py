"""
Port of the free geometry functions shared by GridObstacles.cpp and
RoutingGrid.cpp (point_in_polygon / offset_polygon / rasterise_polygon).

Speed notes
-----------
- ``offset_polygon`` is a small, per-vertex computation (a handful of
  vertices for typical routing ports/keepouts), so it is kept as a direct,
  behaviour-preserving port of the original vertex-normal expansion in pure
  Python. It also auto-detects winding order (like the RoutingGrid.cpp
  variant) so a negative delta always means "shrink" regardless of polygon
  orientation.
- ``rasterise_polygon`` is the hot path (it can be evaluated over thousands
  of grid cells per obstacle/port), so it is vectorised with NumPy and
  handed to Shapely's GEOS-backed ``contains_xy``, which runs the
  point-in-polygon test in a single C loop instead of a Python loop.
"""
from __future__ import annotations

import math
from typing import List, Sequence, Tuple

import numpy as np
from shapely import contains_xy
from shapely.geometry import Polygon as _ShPolygon
from shapely.geometry import Point as _ShPoint

Point = Tuple[float, float]


def point_in_polygon(px: float, py: float, poly: Sequence[Point]) -> bool:
    """Point-in-polygon test (GEOS-backed). Matches the ray-casting semantics
    of the original C++ helper closely enough for grid-cell classification
    (boundary points are treated as inside)."""
    if len(poly) < 3:
        return False
    shp = _ShPolygon(poly)
    if not shp.is_valid:
        shp = shp.buffer(0)
    return bool(shp.covers(_ShPoint(px, py)))


def offset_polygon(pts: Sequence[Point], delta_um: float) -> List[Point]:
    """Offset a polygon outward (delta_um > 0) or inward (delta_um < 0) using
    vertex-normal expansion. Direct port of RoutingGrid::offset_polygon,
    which auto-detects CW/CCW winding via the shoelace formula so that a
    negative delta always shrinks the polygon."""
    n = len(pts)
    if n < 3 or delta_um == 0.0:
        return list(pts)

    signed_area = 0.0
    for i in range(n):
        j = (i + 1) % n
        signed_area += pts[i][0] * pts[j][1]
        signed_area -= pts[j][0] * pts[i][1]
    # signed_area > 0 -> CCW, < 0 -> CW. Flip delta for CW so negative always
    # means shrink.
    effective_delta = delta_um if signed_area < 0.0 else -delta_um

    result: List[Point] = []
    for i in range(n):
        prev = (i - 1) % n
        nxt = (i + 1) % n

        ax = pts[i][0] - pts[prev][0]
        ay = pts[i][1] - pts[prev][1]
        bx = pts[nxt][0] - pts[i][0]
        by = pts[nxt][1] - pts[i][1]

        la = math.hypot(ax, ay)
        lb = math.hypot(bx, by)
        if la < 1e-12 or lb < 1e-12:
            result.append(pts[i])
            continue

        nx1, ny1 = -ay / la, ax / la
        nx2, ny2 = -by / lb, bx / lb

        bsx = nx1 + nx2
        bsy = ny1 + ny2
        bsl = math.hypot(bsx, bsy)
        if bsl < 1e-12:
            result.append(pts[i])
            continue

        dot = nx1 * bsx / bsl + ny1 * bsy / bsl
        if abs(dot) < 1e-12:
            result.append(pts[i])
            continue

        scale = effective_delta / dot
        result.append((pts[i][0] + bsx / bsl * scale,
                        pts[i][1] + bsy / bsl * scale))
    return result


def rasterise_polygon(points_um: Sequence[Point], grid, shrink_um: float = 0.0
                       ) -> List[Tuple[int, int]]:
    """Rasterise a polygon onto ``grid`` (any object exposing ``to_grid``,
    ``from_grid_arrays``, ``cols`` and ``rows``). Returns all (col, row)
    cells whose centre lies inside the polygon.

    The point-in-polygon classification over the whole bounding-box of grid
    cells is done in one vectorised Shapely/GEOS call rather than a nested
    Python loop, which is the dominant cost for large obstacles/ports.
    """
    if not points_um:
        return []

    poly = points_um
    if shrink_um != 0.0:
        poly = offset_polygon(points_um, -shrink_um)
    if len(poly) < 3:
        return []

    xs_pts = [p[0] for p in poly]
    ys_pts = [p[1] for p in poly]
    xmin, xmax = min(xs_pts), max(xs_pts)
    ymin, ymax = min(ys_pts), max(ys_pts)

    c_lo, r_lo = grid.to_grid(xmin, ymin)
    c_hi, r_hi = grid.to_grid(xmax, ymax)
    c_lo = max(0, c_lo - 1)
    r_lo = max(0, r_lo - 1)
    c_hi = min(grid.cols - 1, c_hi + 1)
    r_hi = min(grid.rows - 1, r_hi + 1)
    if c_hi < c_lo or r_hi < r_lo:
        return []

    cols_idx = np.arange(c_lo, c_hi + 1)
    rows_idx = np.arange(r_lo, r_hi + 1)
    cc, rr = np.meshgrid(cols_idx, rows_idx, indexing="ij")
    xs, ys = grid.from_grid_arrays(cc, rr)

    shp = _ShPolygon(poly)
    if not shp.is_valid:
        shp = shp.buffer(0)

    mask = contains_xy(shp, xs, ys)

    sel_c = cc[mask]
    sel_r = rr[mask]
    return list(zip(sel_c.tolist(), sel_r.tolist()))
