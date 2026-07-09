"""Port of AStarRouter.hpp / AStarRouter.cpp."""
from __future__ import annotations

import heapq
from typing import Dict, Iterable, List, Optional, Tuple

from .routing_config import RoutingConfig
from .routing_grid import RoutingGrid
from .types import Node, NodeSet


class AStarRouter:
    def __init__(self, grid: RoutingGrid, rcfg: RoutingConfig):
        self.grid = grid
        self.rcfg = rcfg

    # public -----------------------------------------------------------------
    def route(self, start: Node, end: Node) -> Optional[List[Node]]:
        return self.route_multi_source({start}, end)

    def route_multi_source(self, start_nodes: NodeSet, end: Node
                            ) -> Optional[List[Node]]:
        grid = self.grid

        def blocked(n: Node) -> bool:
            col, row, lyr = n
            return grid.is_blocked(col, row, lyr) or grid.is_reserved(col, row, lyr)

        if blocked(end):
            return None

        valid_starts = {s for s in start_nodes if not blocked(s)}
        if not valid_starts:
            return None
        if end in valid_starts:
            return [end]

        g_score: Dict[Node, float] = {}
        came_from: Dict[Node, Optional[Node]] = {}
        pq: List[Tuple[float, Node]] = []

        for s in valid_starts:
            g_score[s] = 0.0
            came_from[s] = None
            heapq.heappush(pq, (self._heuristic(s, end), s))

        INF = float("inf")

        while pq:
            f, current = heapq.heappop(pq)

            if current == end:
                return self._reconstruct(came_from, end)

            g_cur = g_score.get(current, INF)

            # Stale-entry check.
            if f > g_cur + self._heuristic(current, end) + 1e-9:
                continue

            for nb, step_cost in self._neighbours(current):
                if blocked(nb):
                    continue
                ng = g_cur + step_cost
                g_nb = g_score.get(nb, INF)
                if ng < g_nb:
                    g_score[nb] = ng
                    came_from[nb] = current
                    heapq.heappush(pq, (ng + self._heuristic(nb, end), nb))

        return None

    # private ------------------------------------------------------------
    def _heuristic(self, a: Node, b: Node) -> float:
        min_route = self.rcfg.get_min_route_cost()
        min_via = self.rcfg.get_min_via_cost()
        return ((abs(a[0] - b[0]) + abs(a[1] - b[1])) * min_route
                + abs(a[2] - b[2]) * min_via)

    def _neighbours(self, node: Node) -> Iterable[Tuple[Node, float]]:
        col, row, lyr = node
        step_cost = self.rcfg.get_route_cost(lyr)

        for dc, dr in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nc, nr = col + dc, row + dr
            if self.grid.in_bounds(nc, nr):
                yield (nc, nr, lyr), step_cost

        via_up_cost = self.rcfg.get_via_up_cost(lyr)
        if via_up_cost is not None:
            yield (col, row, lyr + 1), via_up_cost

        via_down_cost = self.rcfg.get_via_down_cost(lyr)
        if via_down_cost is not None:
            yield (col, row, lyr - 1), via_down_cost

    @staticmethod
    def _reconstruct(came_from: Dict[Node, Optional[Node]], end: Node) -> List[Node]:
        path: List[Node] = []
        node: Optional[Node] = end
        while node is not None:
            path.append(node)
            node = came_from.get(node)
        path.reverse()
        return path
