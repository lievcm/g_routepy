"""Port of NetRouter.hpp / NetRouter.cpp."""
from __future__ import annotations

import math
import sys
from typing import Dict, List, Optional, Tuple

import klayout.db as db

from .astar_router import AStarRouter
from .gds_writer import write_path_to_gds
from .routing_config import RoutingConfig
from .routing_grid import RoutingGrid
from .types import Net, Node, NodeSet, Port, RouteStrat


class NetRouter:
    def __init__(self, layout: "db.Layout", grid: RoutingGrid, rcfg: RoutingConfig):
        self.layout = layout
        self.grid = grid
        self.rcfg = rcfg
        self.astar = AStarRouter(grid, rcfg)

    # -- public --------------------------------------------------------------
    def route_nets(self, nets: List[Net], cell: "db.Cell",
                    strat: RouteStrat) -> Dict[str, bool]:
        # Sort nets by HPWL (shortest first).
        sorted_nets = sorted(nets, key=self._net_hpwl)

        results: Dict[str, bool] = {}
        for net in sorted_nets:
            ok = self._route_net(net, cell, strat)
            results[net.name] = ok
            if not ok:
                print(f"[WARN] Could not complete routing for net '{net.name}'",
                      file=sys.stderr)
        return results

    # -- private helpers -----------------------------------------------------
    def _net_hpwl(self, net: Net) -> float:
        xs = [p.x_um for p in net.ports]
        ys = [p.y_um for p in net.ports]
        if not xs:
            return 0.0
        return (max(xs) - min(xs)) + (max(ys) - min(ys))

    def _clear_port_for_routing(self, port: Port) -> None:
        lyr = self.rcfg.get_layer_idx(port.layer)
        if port.polygon:
            self.grid.set_port_reservation_polygon(port.polygon, lyr, False)
        else:
            self.grid.set_port_reservation(port.x_um, port.y_um, lyr, False)

    def _restore_port_reservation(self, port: Port) -> None:
        lyr = self.rcfg.get_layer_idx(port.layer)
        if port.polygon:
            self.grid.set_port_reservation_polygon(port.polygon, lyr, True)
        else:
            self.grid.set_port_reservation(port.x_um, port.y_um, lyr, True)

    def _route_net(self, net: Net, cell: "db.Cell", strat: RouteStrat) -> bool:
        if strat == RouteStrat.MultiStart:
            return self._route_net_multistart(net, cell)
        elif strat == RouteStrat.QuickMST:
            return self._route_net_quickmst(net, cell)
        else:
            return False

    def _route_net_multistart(self, net: Net, cell: "db.Cell") -> bool:
        if len(net.ports) < 2:
            return True

        for port in net.ports:
            self._clear_port_for_routing(port)

        ports = net.ports
        edge_indices = self._mst_edges(ports)

        connected_nodes: Optional[NodeSet] = None
        all_paths: List[List[Node]] = []

        for ia, ib in edge_indices:
            p_a, p_b = ports[ia], ports[ib]

            start_nodes = connected_nodes if connected_nodes is not None \
                else self.grid.nodes_from_port(p_a)
            end_nodes = self.grid.nodes_from_port(p_b)
            end_node = self.grid.best_start_node(end_nodes, start_nodes)

            path = self.astar.route_multi_source(start_nodes, end_node)

            if path is None:
                print(f"[WARN] No path found for net '{net.name}' between "
                      f"'{p_a.name}' and '{p_b.name}'", file=sys.stderr)
                for port in net.ports:
                    self._restore_port_reservation(port)
                return False

            all_paths.append(path)

            if connected_nodes is None:
                connected_nodes = set(path)
            else:
                connected_nodes.update(path)
        
        for cp in all_paths:
            self.grid.block_route(cp)
            write_path_to_gds(self.layout, cell, cp, self.grid, self.rcfg)

        for port in net.ports:
            self._restore_port_reservation(port)

        return True

    def _route_net_quickmst(self, net: Net, cell: "db.Cell") -> bool:
        if len(net.ports) < 2:
            return True

        for port in net.ports:
            self._clear_port_for_routing(port)

        ports = net.ports
        edge_indices = self._mst_edges(ports)

        all_paths: List[List[Node]] = []

        for ia, ib in edge_indices:
            p_a, p_b = ports[ia], ports[ib]

            start_nodes = self.grid.nodes_from_port(p_a)
            end_nodes = self.grid.nodes_from_port(p_b)
            end_node = self.grid.best_start_node(end_nodes, start_nodes)

            path = self.astar.route_multi_source(start_nodes, end_node)

            if path is None:
                print(f"[WARN] No path found for net '{net.name}' between "
                      f"'{p_a.name}' and '{p_b.name}'", file=sys.stderr)
                for port in net.ports:
                    self._restore_port_reservation(port)
                return False

            all_paths.append(path)

        for cp in all_paths:
            self.grid.block_route(cp)
            write_path_to_gds(self.layout, cell, cp, self.grid, self.rcfg)

        for port in net.ports:
            self._restore_port_reservation(port)

        return True

    @staticmethod
    def _mst_edges(ports: List[Port]) -> List[Tuple[int, int]]:
        """Prim's MST on Manhattan distance. Returns edges ordered so that
        p_a is always the "already in tree" side."""
        n = len(ports)
        if n < 2:
            return []

        edges: List[Tuple[int, int]] = []
        in_tree = [False] * n
        in_tree[0] = True
        in_count = 1

        while in_count < n:
            best_cost = math.inf
            best_i = best_j = 0

            for i in range(n):
                if not in_tree[i]:
                    continue
                for j in range(n):
                    if in_tree[j]:
                        continue
                    d = (abs(ports[i].x_um - ports[j].x_um)
                         + abs(ports[i].y_um - ports[j].y_um))
                    if d < best_cost:
                        best_cost = d
                        best_i, best_j = i, j

            edges.append((best_i, best_j))
            in_tree[best_j] = True
            in_count += 1

        return edges
