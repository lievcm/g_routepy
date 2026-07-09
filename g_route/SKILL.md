---
name: g-route-gds-router
description: Use this skill whenever working with the g_route Python package — a grid-based Manhattan/via-aware autorouter for IC/photonic-style layouts that reads a JSON layer-stack config and writes real GDSII output via KLayout. Trigger this any time the user mentions g_route, asks to route nets/ports on a GDS layout, wants to add keepouts/obstacles to a routing grid, asks about RoutingConfig/RoutingGrid/GDSRouter/NetRouter/AStarRouter classes, or wants to programmatically generate or auto-route a .gds file. Also use this to explain the package's API, debug routing failures ("no path found"), or extend it (new route strategies, new geometry).
---

# g_route: grid-based GDS autorouter

`g_route` is a Python port of a C++ autorouter. It takes a set of **nets**
(groups of **ports**, each pinned to a metal layer and an (x, y) location or
polygon), lays them out on a **Manhattan routing grid**, runs **A\*** search
per net (connected via a Prim's-MST edge order), and writes the resulting
wires/vias directly into a **KLayout** `Layout`/`Cell` as real GDSII shapes.

Use this doc to answer "how do I..." questions about the package, to write
scripts against it, or to debug routing failures.

## Install

```
pip install klayout shapely numpy
```

The package itself is a plain local module — copy the `g_route/` directory
into your project (no PyPI install step). Import as `import g_route` or
`from g_route import ...`.

## Mental model (read this first)

1. You describe your **layer stack** (metals + vias) as JSON → `RoutingConfig`.
2. You create a **KLayout** `Layout` + `Cell` (this is where GDS output goes).
3. You create a `GDSRouter`, bound to that layout/cell/config, sized to a grid
   (pitch + origin + cols/rows, or auto-sized from your nets).
4. You register **obstacles/keepouts** and **nets** (each net = list of `Port`).
5. You call `router.route(...)`. It Manhattan-routes each net with A\*,
   avoiding obstacles/other ports, and writes flex-paths + vias + polygon
   ports directly into the KLayout cell.
6. You `layout.write("out.gds")`.

Nothing here mutates a `.gds` file in place — you build up a KLayout `Layout`
in memory (from scratch or loaded from an existing file) and write it out.

## Quick start

```python
import klayout.db as db
from g_route import RoutingConfig, GDSRouter, Net, Port, RouteStrat

# 1. Layer stack config (see "RoutingConfig JSON schema" below)
cfg = {
    "routing_layers": {
        "m1": {"vindex": 0, "gds_layer": [11, 0], "route_cost": 1.0,
               "min_width": 0.2, "min_spacing": 0.2},
        "m2": {"vindex": 1, "gds_layer": [12, 0], "route_cost": 1.2,
               "min_width": 0.2, "min_spacing": 0.2},
    },
    "vias": {
        "v1": {"lower_metal": "m1", "upper_metal": "m2", "cost": 2.0,
               "size": 0.2, "enclosure_by_lower_metal": 0.05,
               "enclosure_by_upper_metal": 0.05, "gds_layer": [51, 0]},
    },
}
rcfg = RoutingConfig(cfg)                       # or RoutingConfig.from_file("layers.json")

# 2. KLayout layout + cell — this holds your GDS output
layout = db.Layout()
layout.dbu = 0.001                              # 1 database unit = 1 nm
top = layout.create_cell("TOP")

# 3. Define nets (ports)
net_a = Net("netA", [
    Port.point("p1", 0.0, 0.0, "m1"),
    Port.point("p2", 10.0, 6.0, "m1"),
])

# 4. Router, auto-sized grid from the nets' bounding box
router = GDSRouter.from_nets(layout, top, [net_a], rcfg, pitch_um=0.5, padding_um=5.0)

for p in net_a.ports:
    router.draw_port(p, net_a.name)             # optional: draw + label pin shapes

router.add_keepout("m1", 2.0, 2.0, 3.0, 3.0)     # optional obstacle

results = router.route(RouteStrat.MultiStart)    # {"netA": True, ...}
layout.write("out.gds")
```

## Core objects

### `Port` (`g_route.types.Port`)
A pin: a name, a layer, and either a point or a polygon.

```python
Port.point(name, x_um, y_um, layer)             # single point pin
Port.poly(name, layer, [(x1,y1), (x2,y2), ...]) # polygon pin (centroid auto-computed)
```

### `Net` (`g_route.types.Net`)
```python
Net(name="clk", ports=[port_a, port_b, port_c])  # 3+ ports -> routed as a Steiner-ish MST
```
A net with `< 2` ports is a no-op (returns success trivially).

### `RoutingConfig`
Parses your layer-stack JSON (see schema below). Construct from a dict
(`RoutingConfig(cfg)`) or a file (`RoutingConfig.from_file(path)`).

### `GDSRouter`
The main entry point. Owns a `RoutingGrid`, a KLayout `Layout`/`Cell`, and the
list of nets to route.

```python
GDSRouter(layout, cell, rcfg, grid_pitch_um=3.0, origin_x=0.0, origin_y=0.0, cols=200, rows=200)
GDSRouter.from_nets(layout, cell, nets, rcfg, pitch_um=3.0, padding_um=50.0)  # auto-sized grid

router.add_keepout(layer, x1, y1, x2, y2)                     # rectangular obstacle
router.add_keepout_polygon(layer, points, spacing=False)      # polygon obstacle
router.add_net(net) / router.add_nets([net, ...])              # register nets to route later
router.draw_port(port, net_name="")                            # draw pin shape (+label) into GDS
router.route(strat=RouteStrat.MultiStart, nets_override=None)  # -> {net_name: success_bool}
```

`route()` reserves all registered ports as no-go zones first (so nets don't
route through each other's pins), then hands off to `NetRouter`.

### `RouteStrat`
- **`MultiStart`** — after the first edge of a net's MST is routed, later
  edges may start from *any* node already on the net (not just the original
  port), producing more Steiner-tree-like, typically shorter nets.
- **`QuickMST`** — every MST edge routes strictly port-to-port. Faster,
  usually longer wire.

### `NetRouter`, `AStarRouter`, `RoutingGrid`
Lower-level pieces `GDSRouter` composes for you. Use them directly if you
want routing without any GDS output (e.g. to just get `Node` paths back), or
want to drive A\* on a hand-built grid:

```python
from g_route import RoutingGrid, AStarRouter

grid = RoutingGrid(rcfg, pitch=0.5, origin_x=0, origin_y=0, cols=200, rows=200)
astar = AStarRouter(grid, rcfg)
path = astar.route(start=(0, 0, 0), end=(20, 20, 1))  # Node = (col, row, layer_idx) or None
```

`NetRouter(layout, grid, rcfg).route_nets(nets, cell, strat)` is what
`GDSRouter.route()` calls internally — use it directly if you're managing
the `RoutingGrid`/obstacles yourself instead of going through `GDSRouter`.

### `GridObstacles`
A **standalone**, alternate obstacle/port-reservation tracker (NumPy-backed
boolean grids per layer). It is *not* wired into `GDSRouter`/`NetRouter` —
those use `RoutingGrid`'s own built-in occupancy grids. Only reach for
`GridObstacles` if you're building a custom routing pipeline that wants a
separate obstacle-tracking layer.

## RoutingConfig JSON schema

```json
{
  "routing_layers": {
    "<layer_name>": {
      "vindex": 0,              // stacking order, lowest = 0; also used for via up/down
      "gds_layer": [11, 0],     // [gds layer number, gds datatype]
      "route_cost": 1.0,        // A* cost per grid step on this layer
      "min_width": 0.2,         // um, wire width
      "min_spacing": 0.2,       // um, min spacing to other shapes
      "port_dtype": 1           // optional; defaults to gds_layer[1] if omitted
    }
  },
  "vias": {
    "<via_name>": {
      "lower_metal": "m1", "upper_metal": "m2",
      "cost": 2.0,                          // A* cost to change layers here
      "size": 0.2,                          // um, via cut size
      "enclosure_by_lower_metal": 0.05,     // um
      "enclosure_by_upper_metal": 0.05,     // um
      "gds_layer": [51, 0]
    }
  }
}
```
Layers are sorted internally by `vindex` to build the layer stack order (used
for "one via hop at a time" legality checks in A\*). A layer without a via
entry to its neighbor simply can't route a via there.

## Coordinates & units

- All routing-facing APIs (`Port`, `add_keepout`, config `min_width` etc.) use
  **microns (float)**.
- KLayout's `Layout.dbu` controls the GDS database-unit resolution
  (e.g. `0.001` = 1 nm/dbu). `g_route` always talks to KLayout in double-precision
  microns (`db.DBox`, `db.DPoint`, `db.DPath`), so you don't need to convert
  to integer database units yourself — KLayout does that at insert time.
- `Node = (col, row, layer_idx)` — grid-integer coordinates, not microns.
  Convert with `grid.to_grid(x_um, y_um)` / `grid.from_grid(col, row)`.

## Common tasks

**Route nets without drawing pin shapes.**
Skip `router.draw_port(...)` — routing doesn't require it, it's purely
cosmetic/for reference labels.

**Load an existing GDS and route into it.**
```python
layout = db.Layout()
layout.read("existing_design.gds")
top = layout.cell("TOP")   # or layout.top_cell()
router = GDSRouter(layout, top, rcfg, grid_pitch_um=0.5, origin_x=..., origin_y=..., cols=..., rows=...)
```
Existing shapes on your routing layers are **not** automatically registered
as obstacles — call `add_keepout`/`add_keepout_polygon` yourself for
anything the router should avoid, or query `layout` shapes and translate
them into keepouts.

**A net fails to route ("[WARN] No path found...")**
Causes, in likely order:
1. Grid too small / `origin`+`cols`+`rows` don't cover the ports — check
   `GDSRouter.from_nets(..., padding_um=...)` gave enough margin.
2. Ports are on a layer with no route/via path to each other (check
   `vindex` ordering and that a `via` entry bridges every adjacent layer you
   need).
3. Obstacles/other nets' reserved ports fully block the area — try routing
   in a different net order, increase grid resolution, or reduce `min_spacing`.
4. Two ports land on the exact same, already-blocked grid cell after
   inflation by `min_width`/`min_spacing` — increase `pitch_um` resolution
   or check the port polygon isn't degenerate.

`route_nets` sorts nets by HPWL (shortest first) so short/easy nets don't get
starved by long ones grabbing grid cells first — if you see failures, try
reducing congestion (bigger grid, coarser pitch) before assuming there's a bug.

**Speed.** The grid uses NumPy boolean arrays and polygon rasterization uses
Shapely/GEOS (`shapely.contains_xy`), both C-backed — the Python-level cost is
mostly the A\* search itself (`heapq`-based, one `NetRouter` object per
`route()` call, not currently parallelized across nets). For many/large nets,
consider batching `route()` calls per independent net group if you need
multiprocessing — `RoutingGrid`/A\* state isn't thread-safe to share across
processes without copying.

## Full worked example (polygon ports, keepouts, multi-layer)

```python
import klayout.db as db
from g_route import RoutingConfig, GDSRouter, Net, Port, RouteStrat

rcfg = RoutingConfig.from_file("layers.json")

layout = db.Layout()
layout.dbu = 0.001
top = layout.create_cell("TOP")

net = Net("data_bus", [
    Port.poly("padA", "m1", [(0,0), (2,0), (2,2), (0,2)]),
    Port.point("padB", 20.0, 15.0, "m2"),
])

router = GDSRouter.from_nets(layout, top, [net], rcfg, pitch_um=0.2, padding_um=10.0)
router.add_keepout_polygon("m1", [(8,8), (12,8), (12,12), (8,12)], spacing=True)

for p in net.ports:
    router.draw_port(p, net.name)

ok = router.route(RouteStrat.MultiStart)
if not ok["data_bus"]:
    raise RuntimeError("routing failed for data_bus")

layout.write("data_bus.gds")
```

## API reference (quick index)

| Class | Module | Purpose |
|---|---|---|
| `RoutingConfig` | `routing_config.py` | Layer stack + via costs/sizes from JSON |
| `RoutingGrid` | `routing_grid.py` | Manhattan grid: occupancy, port reservation, coord mapping |
| `GridObstacles` | `grid_obstacles.py` | Standalone (unused-by-default) obstacle tracker |
| `AStarRouter` | `astar_router.py` | Multi-source A\* over the grid |
| `NetRouter` | `net_router.py` | Per-net MST edge ordering + A\* + GDS write |
| `GDSRouter` | `gds_router.py` | Top-level: grid + obstacles + nets + `route()` |
| `gds_writer` | `gds_writer.py` | Low-level KLayout shape emission (paths/vias/rects) |
| `geometry` | `geometry.py` | Point-in-polygon, polygon offset, grid rasterization |
| `Node`, `NodeSet`, `Port`, `Net`, `RouteStrat` | `types.py` | Core data types |

Full API surface mirrors this doc's "Core objects" section — every public
method listed there is the complete signature (no hidden required args
beyond what's shown).
