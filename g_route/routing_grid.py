"""
Port of RoutingGrid.hpp / RoutingGrid.cpp.

The occupancy grids (blocked_ / port_reserved_ in the C++, std::vector<bool>
under the hood) are replaced with NumPy boolean arrays. This turns the
rectangle set/get operations (block_rect, set_port_reservation, block_route,
...) into vectorised slice assignments executed in C rather than nested
Python loops.
"""
from __future__ import annotations

import math
from typing import List, Optional, Sequence, Tuple

import numpy as np

from .routing_config import RoutingConfig
from .types import Net, Node, NodeSet, Port
from .geometry import Point, offset_polygon, point_in_polygon, rasterise_polygon


class OccupancyGrid:
    """NumPy-backed replacement for the C++ OccupancyGrid (vector<bool>)."""

    def __init__(self, rows: int, cols: int, lyrs: int):
        self.rows = rows
        self.cols = cols
        self.lyrs = lyrs
        # [layer, row, col] -- vectorised rectangle ops are the hot path.
        self.data = np.zeros((lyrs, rows, cols), dtype=bool)

    def get(self, col: int, row: int, lyr: int) -> bool:
        return bool(self.data[lyr, row, col])

    def set(self, col: int, row: int, lyr: int, occ: bool) -> None:
        self.data[lyr, row, col] = occ

    def set_rect(self, c_lo: int, r_lo: int, c_hi: int, r_hi: int,
                 lyr: int, occ: bool) -> None:
        self.data[lyr, r_lo:r_hi + 1, c_lo:c_hi + 1] = occ


class RoutingGrid:
    def __init__(self, rcfg: RoutingConfig, pitch: float,
                 origin_x: float, origin_y: float, cols: int, rows: int):
        self.rcfg = rcfg
        self.pitch = pitch
        self.ox = origin_x
        self.oy = origin_y
        self.cols = cols
        self.rows = rows
        self.lyrs = rcfg.get_num_layers()

        self.blocked = OccupancyGrid(rows, cols, self.lyrs)
        self.port_reserved = OccupancyGrid(rows, cols, self.lyrs)

    # -- coordinate mapping ------------------------------------------------
    def to_grid(self, x: float, y: float) -> Tuple[int, int]:
        col = int(round((x - self.ox) / self.pitch))
        row = int(round((y - self.oy) / self.pitch))
        return col, row

    def from_grid(self, col: int, row: int) -> Tuple[float, float]:
        return self.ox + col * self.pitch, self.oy + row * self.pitch

    # Alias kept for compatibility with call sites written against the
    # `to_um` naming used elsewhere in the original codebase.
    to_um = from_grid

    def from_grid_arrays(self, cc: np.ndarray, rr: np.ndarray
                          ) -> Tuple[np.ndarray, np.ndarray]:
        """Vectorised counterpart of from_grid, used by geometry.rasterise_polygon."""
        return self.ox + cc * self.pitch, self.oy + rr * self.pitch

    def in_bounds(self, col: int, row: int, lyr: int = 0) -> bool:
        return 0 <= col < self.cols and 0 <= row < self.rows and 0 <= lyr < self.lyrs

    # -- obstacle blocking ---------------------------------------------------
    def block_rect(self, x1: float, y1: float, x2: float, y2: float,
                   lyr: int, inflate: float = 0.0) -> None:
        x_lo, x_hi = (x1, x2) if x1 <= x2 else (x2, x1)
        y_lo, y_hi = (y1, y2) if y1 <= y2 else (y2, y1)
        x_lo -= inflate; x_hi += inflate
        y_lo -= inflate; y_hi += inflate

        c_lo, r_lo = self.to_grid(x_lo, y_lo)
        c_hi, r_hi = self.to_grid(x_hi, y_hi)
        c_lo = max(0, c_lo); c_hi = min(self.cols - 1, c_hi)
        r_lo = max(0, r_lo); r_hi = min(self.rows - 1, r_hi)
        if c_hi < c_lo or r_hi < r_lo:
            return
        self.blocked.set_rect(c_lo, r_lo, c_hi, r_hi, lyr, True)

    def block_polygon(self, points: Sequence[Point], lyr: int,
                       inflate: float = 0.0) -> None:
        for col, row in self._rasterise_polygon(points, inflate):
            if self.in_bounds(col, row, lyr):
                self.blocked.set(col, row, lyr, True)

    def block_route(self, path: Sequence[Node]) -> None:
        for col, row, lyr in path:
            r = math.ceil(self.rcfg.block_radius_um(lyr) / self.pitch)
            c_lo = max(0, col - r); c_hi = min(self.cols - 1, col + r)
            r_lo = max(0, row - r); r_hi = min(self.rows - 1, row + r)
            if c_hi < c_lo or r_hi < r_lo:
                continue
            self.blocked.set_rect(c_lo, r_lo, c_hi, r_hi, lyr, True)

    # -- port reservation ------------------------------------------------
    def set_port_reservation(self, x: float, y: float, lyr: int, reserved: bool) -> None:
        r = self.rcfg.block_radius_um(lyr)
        c_lo, r_lo = self.to_grid(x - r, y - r)
        c_hi, r_hi = self.to_grid(x + r, y + r)
        c_lo = max(0, c_lo); c_hi = min(self.cols - 1, c_hi)
        r_lo = max(0, r_lo); r_hi = min(self.rows - 1, r_hi)
        if c_hi < c_lo or r_hi < r_lo:
            return
        self.port_reserved.set_rect(c_lo, r_lo, c_hi, r_hi, lyr, reserved)

    def set_port_reservation_polygon(self, points: Sequence[Point], lyr: int,
                                      reserved: bool) -> None:
        r = self.rcfg.block_radius_um(lyr, True)
        for col, row in self._rasterise_polygon(points, r):
            if self.in_bounds(col, row, lyr):
                self.port_reserved.set(col, row, lyr, reserved)

    def set_nodes_reservation(self, nodes: NodeSet, reserved: bool) -> None:
        for col, row, lyr in nodes:
            if self.in_bounds(col, row, lyr):
                self.port_reserved.set(col, row, lyr, reserved)

    # -- queries -----------------------------------------------------------
    def is_blocked(self, col: int, row: int, lyr: int) -> bool:
        if not self.in_bounds(col, row, lyr):
            return True
        return self.blocked.get(col, row, lyr)

    def is_reserved(self, col: int, row: int, lyr: int) -> bool:
        if not self.in_bounds(col, row, lyr):
            return True
        return self.port_reserved.get(col, row, lyr)

    def nodes_from_port(self, port: Port) -> NodeSet:
        lyr_idx = self.rcfg.get_layer_idx(port.layer)

        if port.polygon:
            width = self.rcfg.get_route_width(lyr_idx)
            cells = self._rasterise_polygon(port.polygon, -width / 2.0)
            if not cells:
                col, row = self.to_grid(port.x_um, port.y_um)
                return {(col, row, lyr_idx)}
            return {(c, r, lyr_idx) for c, r in cells}

        col, row = self.to_grid(port.x_um, port.y_um)
        return {(col, row, lyr_idx)}

    def best_start_node(self, start_nodes: NodeSet, target_nodes: NodeSet) -> Node:
        if not target_nodes:
            return next(iter(start_nodes))

        tc = sum(n[0] for n in target_nodes) / len(target_nodes)
        tr = sum(n[1] for n in target_nodes) / len(target_nodes)

        return min(start_nodes,
                   key=lambda n: abs(n[0] - tc) + abs(n[1] - tr))

    # -- private -------------------------------------------------------------
    def _rasterise_polygon(self, points: Sequence[Point], delta: float = 0.0
                            ) -> List[Tuple[int, int]]:
        return rasterise_polygon(points, self, shrink_um=-delta)
