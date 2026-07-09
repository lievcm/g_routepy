"""
Port of GridObstacles.hpp / GridObstacles.cpp.

Note: in the original C++ project this class is a standalone
obstacle/port-reservation tracker; NetRouter/GDSRouter route against
RoutingGrid's own built-in occupancy grids instead, not this class. It is
ported here for completeness and API parity, using RoutingGrid's public
``to_grid``/``from_grid``/``cols``/``rows``/``pitch`` surface.
"""
from __future__ import annotations

import math
from typing import List, Optional, Sequence

import numpy as np

from .routing_config import RoutingConfig
from .routing_grid import RoutingGrid
from .types import Node, NodeSet
from .geometry import Point, offset_polygon, rasterise_polygon


class GridObstacles:
    def __init__(self, grid: RoutingGrid, rcfg: RoutingConfig):
        self.grid = grid
        self.rcfg = rcfg

        n = rcfg.get_num_layers()
        rows, cols = grid.rows, grid.cols
        # [layer][row, col] boolean occupancy, NumPy-backed for vectorised
        # rectangle set/clear (see RoutingGrid.OccupancyGrid for the same
        # pattern).
        self.occ: List[np.ndarray] = [np.zeros((rows, cols), dtype=bool) for _ in range(n)]
        self.port_occ: List[np.ndarray] = [np.zeros((rows, cols), dtype=bool) for _ in range(n)]

    # -- private helpers ---------------------------------------------------
    def _all_layer_indices(self) -> List[int]:
        return list(range(self.rcfg.get_num_layers()))

    @staticmethod
    def _set_rect(grids: List[np.ndarray], layer_idx: int,
                   c_lo: int, r_lo: int, c_hi: int, r_hi: int, value: bool) -> None:
        if c_hi < c_lo or r_hi < r_lo:
            return
        grids[layer_idx][r_lo:r_hi + 1, c_lo:c_hi + 1] = value

    def _rect_bounds(self, x_lo, y_lo, x_hi, y_hi):
        c_lo, r_lo = self.grid.to_grid(x_lo, y_lo)
        c_hi, r_hi = self.grid.to_grid(x_hi, y_hi)
        c_lo = max(0, c_lo); c_hi = min(self.grid.cols - 1, c_hi)
        r_lo = max(0, r_lo); r_hi = min(self.grid.rows - 1, r_hi)
        return c_lo, r_lo, c_hi, r_hi

    # -- obstacle blocking ---------------------------------------------------
    def block_rect_um(self, layer_idx: int, x1_um: float, y1_um: float,
                       x2_um: float, y2_um: float, inflate_um: float = 0.0) -> None:
        x_lo = min(x1_um, x2_um) - inflate_um
        x_hi = max(x1_um, x2_um) + inflate_um
        y_lo = min(y1_um, y2_um) - inflate_um
        y_hi = max(y1_um, y2_um) + inflate_um

        c_lo, r_lo, c_hi, r_hi = self._rect_bounds(x_lo, y_lo, x_hi, y_hi)
        self._set_rect(self.occ, layer_idx, c_lo, r_lo, c_hi, r_hi, True)

    def block_polygon_um(self, layer_idx: int, points_um: Sequence[Point],
                          inflate_um: float = 0.0) -> None:
        poly = points_um
        if inflate_um != 0.0:
            poly = offset_polygon(points_um, inflate_um)

        for col, row in rasterise_polygon(poly, self.grid):
            if self.grid.in_bounds(col, row):
                self.occ[layer_idx][row, col] = True

    def block_node(self, node: Node) -> None:
        col, row, lyr = node
        if self.grid.in_bounds(col, row):
            self.occ[lyr][row, col] = True

    # -- port reservation ------------------------------------------------
    def reserve_port(self, x_um: float, y_um: float,
                      layer_indices: Optional[List[int]] = None) -> None:
        layers = layer_indices if layer_indices is not None else self._all_layer_indices()
        for lyr in layers:
            r = self.rcfg.block_radius_um(lyr)
            c_lo, r_lo, c_hi, r_hi = self._rect_bounds(x_um - r, y_um - r, x_um + r, y_um + r)
            self._set_rect(self.port_occ, lyr, c_lo, r_lo, c_hi, r_hi, True)

    def reserve_port_polygon(self, points_um: Sequence[Point],
                              layer_indices: Optional[List[int]] = None) -> None:
        layers = layer_indices if layer_indices is not None else self._all_layer_indices()
        for lyr in layers:
            infl = self.rcfg.block_radius_um(lyr, True)
            grown = offset_polygon(points_um, infl)
            for col, row in rasterise_polygon(grown, self.grid):
                if self.grid.in_bounds(col, row):
                    self.port_occ[lyr][row, col] = True

    def clear_port_reservation(self, x_um: float, y_um: float,
                                layer_indices: Optional[List[int]] = None) -> None:
        layers = layer_indices if layer_indices is not None else self._all_layer_indices()
        for lyr in layers:
            r = self.rcfg.block_radius_um(lyr)
            c_lo, r_lo, c_hi, r_hi = self._rect_bounds(x_um - r, y_um - r, x_um + r, y_um + r)
            self._set_rect(self.port_occ, lyr, c_lo, r_lo, c_hi, r_hi, False)

    def clear_port_reservation_polygon(self, points_um: Sequence[Point],
                                        layer_indices: Optional[List[int]] = None) -> None:
        layers = layer_indices if layer_indices is not None else self._all_layer_indices()
        for lyr in layers:
            infl = self.rcfg.block_radius_um(lyr, True)
            grown = offset_polygon(points_um, infl)
            for col, row in rasterise_polygon(grown, self.grid):
                if self.grid.in_bounds(col, row):
                    self.port_occ[lyr][row, col] = False

    def clear_nodes_reservation(self, nodes: NodeSet) -> None:
        for col, row, lyr in nodes:
            if self.grid.in_bounds(col, row):
                self.port_occ[lyr][row, col] = False

    def reserve_nodes(self, nodes: NodeSet) -> None:
        for col, row, lyr in nodes:
            if self.grid.in_bounds(col, row):
                self.port_occ[lyr][row, col] = True

    # -- queries -----------------------------------------------------------
    def is_blocked(self, col: int, row: int, lyr: int) -> bool:
        if not self.grid.in_bounds(col, row):
            return True
        return bool(self.occ[lyr][row, col])

    def is_port_reserved(self, col: int, row: int, lyr: int) -> bool:
        if not self.grid.in_bounds(col, row):
            return False
        return bool(self.port_occ[lyr][row, col])

    # -- route commit ------------------------------------------------------
    def mark_route(self, path: Sequence[Node]) -> None:
        for col, row, lyr in path:
            sp = math.ceil(self.rcfg.inflate_um(lyr) / self.grid.pitch) \
                if hasattr(self.rcfg, "inflate_um") else \
                math.ceil(self.rcfg.block_radius_um(lyr) / self.grid.pitch)
            c_lo = max(0, col - sp)
            r_lo = max(0, row - sp)
            c_hi = min(self.grid.cols - 1, col + sp)
            r_hi = min(self.grid.rows - 1, row + sp)
            self.occ[lyr][r_lo:r_hi + 1, c_lo:c_hi + 1] = True
