"""
Port of Types.hpp.

Node is a plain (col, row, layer_idx) tuple, exactly like the C++
std::tuple<int,int,int> -- Python tuples are hashable and orderable out of
the box, so no custom comparator/hash is needed (unlike the C++ NodeCmp /
NodeHash helpers).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from typing import List, Optional, Sequence, Set, Tuple

# (col, row, layer_idx)
Node = Tuple[int, int, int]
NodeSet = Set[Node]


class RouteStrat(IntEnum):
    MultiStart = 0
    QuickMST = 1
    # MST = 2
    # I1S = 3


@dataclass
class Port:
    name: str
    x_um: float = 0.0
    y_um: float = 0.0
    layer: str = "m1"

    # Optional polygon port (vertices in um). When set, x_um/y_um are the
    # centroid, matching the C++ std::optional<vector<pair<double,double>>>.
    polygon: Optional[List[Tuple[float, float]]] = None

    @staticmethod
    def point(name: str, x_um: float, y_um: float, layer: str) -> "Port":
        return Port(name=name, x_um=x_um, y_um=y_um, layer=layer, polygon=None)

    @staticmethod
    def poly(name: str, layer: str, polygon: Sequence[Tuple[float, float]]) -> "Port":
        pts = list(polygon)
        cx = sum(p[0] for p in pts) / len(pts)
        cy = sum(p[1] for p in pts) / len(pts)
        return Port(name=name, x_um=cx, y_um=cy, layer=layer, polygon=pts)


@dataclass
class Net:
    name: str
    ports: List[Port] = field(default_factory=list)
