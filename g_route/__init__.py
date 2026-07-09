"""
g_route: Python port of the C++ GDS auto-router.

Uses KLayout (klayout.db) for GDS I/O and Shapely/GEOS + NumPy (both C/C++
backed) for the geometry-heavy hot paths (polygon rasterisation onto the
routing grid, occupancy-grid bookkeeping).
"""

from .types import Node, NodeSet, Port, Net, RouteStrat
from .routing_config import RoutingConfig
from .routing_grid import RoutingGrid, OccupancyGrid
from .grid_obstacles import GridObstacles
from .astar_router import AStarRouter
from .net_router import NetRouter
from .gds_router import GDSRouter, GridBounds, compute_grid_bounds, compute_grid_bounds_from_nets
from . import gds_writer
from . import geometry

__all__ = [
    "Node", "NodeSet", "Port", "Net", "RouteStrat",
    "RoutingConfig",
    "RoutingGrid", "OccupancyGrid",
    "GridObstacles",
    "AStarRouter",
    "NetRouter",
    "GDSRouter", "GridBounds", "compute_grid_bounds", "compute_grid_bounds_from_nets",
    "gds_writer", "geometry",
]
