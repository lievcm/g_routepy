"""Port of GDSRouter.hpp / GDSRouter.cpp, using KLayout (klayout.db) instead
of gdstk for all GDS shape creation."""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

import klayout.db as db

from .gds_writer import insert_square
from .net_router import NetRouter
from .routing_config import RoutingConfig
from .routing_grid import RoutingGrid
from .types import Net, Port, RouteStrat

Point = Tuple[float, float]


# ---------------------------------------------------------------------------
# Grid bounds helpers
# ---------------------------------------------------------------------------

def _collect_port_coords(ports: Sequence[Port]) -> Tuple[List[float], List[float]]:
    xs: List[float] = []
    ys: List[float] = []
    for p in ports:
        if p.polygon:
            for x, y in p.polygon:
                xs.append(x); ys.append(y)
        else:
            xs.append(p.x_um); ys.append(p.y_um)
    return xs, ys


@dataclass
class GridBounds:
    origin_um: Point
    cols: int
    rows: int


def compute_grid_bounds(ports: Sequence[Port], pitch_um: float,
                         padding_um: float = 50.0) -> GridBounds:
    xs, ys = _collect_port_coords(ports)

    xmin = math.floor((min(xs) - padding_um) / pitch_um) * pitch_um
    ymin = math.floor((min(ys) - padding_um) / pitch_um) * pitch_um
    xmax = math.ceil((max(xs) + padding_um) / pitch_um) * pitch_um
    ymax = math.ceil((max(ys) + padding_um) / pitch_um) * pitch_um

    cols = int(round((xmax - xmin) / pitch_um)) + 1
    rows = int(round((ymax - ymin) / pitch_um)) + 1

    return GridBounds((xmin, ymin), cols, rows)


def compute_grid_bounds_from_nets(nets: Sequence[Net], pitch_um: float,
                                   padding_um: float = 50.0) -> GridBounds:
    all_ports: List[Port] = []
    for net in nets:
        all_ports.extend(net.ports)
    return compute_grid_bounds(all_ports, pitch_um, padding_um)


# ---------------------------------------------------------------------------
# GDSRouter
# ---------------------------------------------------------------------------

class GDSRouter:
    def __init__(self, layout: "db.Layout", cell: "db.Cell",
                 routing_config: RoutingConfig,
                 grid_pitch_um: float = 3.0,
                 origin_x: float = 0.0, origin_y: float = 0.0,
                 cols: int = 200, rows: int = 200):
        self.layout = layout
        self.top_cell = cell
        self.rcfg = routing_config
        self.grid = RoutingGrid(routing_config, grid_pitch_um, origin_x, origin_y, cols, rows)
        self.nets: List[Net] = []

    @classmethod
    def from_nets(cls, layout: "db.Layout", cell: "db.Cell", nets: Sequence[Net],
                  routing_config: RoutingConfig, pitch_um: float = 3.0,
                  padding_um: float = 50.0) -> "GDSRouter":
        gb = compute_grid_bounds_from_nets(nets, pitch_um, padding_um)
        router = cls(layout, cell, routing_config, pitch_um,
                      gb.origin_um[0], gb.origin_um[1], gb.cols, gb.rows)
        router.add_nets(nets)
        return router

    # -- obstacle registration ------------------------------------------------
    def add_keepout(self, layer: str, x1_um: float, y1_um: float,
                     x2_um: float, y2_um: float) -> None:
        lyr = self.rcfg.get_layer_idx(layer)
        self.grid.block_rect(x1_um, y1_um, x2_um, y2_um,
                              lyr, self.rcfg.get_route_width(lyr) / 2.0)

    def add_keepout_polygon(self, layer: str, points_um: Sequence[Point],
                             spacing: bool = False) -> None:
        lyr = self.rcfg.get_layer_idx(layer)
        infl = (self.rcfg.block_radius_um(lyr) if spacing
                else self.rcfg.get_route_width(lyr) / 2.0)
        self.grid.block_polygon(points_um, lyr, infl)

    # -- net registration ----------------------------------------------------
    def add_net(self, net: Net) -> None:
        self.nets.append(net)

    def add_nets(self, nets: Sequence[Net]) -> None:
        self.nets.extend(nets)

    # -- port drawing --------------------------------------------------------
    def draw_port(self, port: Port, net_name: str = "") -> None:
        lyr_idx = self.rcfg.get_layer_idx(port.layer)
        gds_l, gds_d = self.rcfg.get_gds(lyr_idx)
        port_dt = self.rcfg.get_port_dt(lyr_idx)
        li = self.layout.layer(gds_l, port_dt)

        if port.polygon:
            pts = [db.DPoint(x, y) for x, y in port.polygon]
            self.top_cell.shapes(li).insert(db.DPolygon(pts))
        else:
            insert_square(self.layout, self.top_cell, port.x_um, port.y_um,
                          self.rcfg.get_route_width(lyr_idx) / 2.0, gds_l, port_dt)

        if net_name:
            text = db.DText(net_name, port.x_um, port.y_um)
            self.top_cell.shapes(li).insert(text)

    # -- routing ---------------------------------------------------------
    def route(self, strat: RouteStrat = RouteStrat.MultiStart,
              nets_override: Optional[List[Net]] = None) -> Dict[str, bool]:
        target_nets = nets_override if nets_override is not None else self.nets

        self._reserve_all_ports(target_nets)

        net_router = NetRouter(self.layout, self.grid, self.rcfg)
        return net_router.route_nets(target_nets, self.top_cell, strat)

    # -- private -----------------------------------------------------------
    def _reserve_all_ports(self, nets: Sequence[Net]) -> None:
        for net in nets:
            for port in net.ports:
                lyr = self.rcfg.get_layer_idx(port.layer)
                if port.polygon:
                    self.grid.set_port_reservation_polygon(port.polygon, lyr, True)
                else:
                    self.grid.set_port_reservation(port.x_um, port.y_um, lyr, True)
