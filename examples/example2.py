import sys, time, random
sys.path.insert(0, ".")

import klayout.db as db
from g_route import RoutingConfig, GDSRouter, Net, Port, RouteStrat

# --- 3-layer stack with two via types ---------------------------------
cfg = {
    "routing_layers": {
        "m1": {"vindex": 0, "gds_layer": [11, 0], "route_cost": 1.0,
               "min_width": 0.2, "min_spacing": 0.2},
        "m2": {"vindex": 1, "gds_layer": [13, 0], "route_cost": 1.0,
               "min_width": 0.2, "min_spacing": 0.2},
        "m3": {"vindex": 2, "gds_layer": [15, 0], "route_cost": 1.0,
               "min_width": 0.3, "min_spacing": 0.3},
    },
    "vias": {
        "v12": {"lower_metal": "m1", "upper_metal": "m2", "cost": 2.0,
                "size": 0.2, "enclosure_by_lower_metal": 0.05,
                "enclosure_by_upper_metal": 0.05, "gds_layer": [12, 0]},
        "v23": {"lower_metal": "m2", "upper_metal": "m3", "cost": 2.5,
                "size": 0.3, "enclosure_by_lower_metal": 0.06,
                "enclosure_by_upper_metal": 0.06, "gds_layer": [14, 0]},
    },
}
rcfg = RoutingConfig(cfg)

layout = db.Layout()
layout.dbu = 0.001
top = layout.create_cell("TOP")

# --- Build a handful of nets, mixing layers, point + polygon ports ----
random.seed(7)
nets = []

# A 4-pin bus that spans m1/m3
nets.append(Net("bus0", [
    Port.point("bus0_a", 0.0, 0.0, "m1"),
    Port.point("bus0_b", 30.0, 4.0, "m3"),
    Port.point("bus0_c", 15.0, 22.0, "m3"),
    Port.point("bus0_d", 40.0, 18.0, "m1"),
]))

# A bunch of small 2-pin nets scattered around, to add some congestion
for i in range(24):
    x1, y1 = round(random.uniform(0, 45)*2)/2, round(random.uniform(0, 45)*2)/2
    x2, y2 = round(random.uniform(0, 45)*2)/2, round(random.uniform(0, 45)*2)/2
    layer = random.choice(["m1", "m2"])
    nets.append(Net(f"net{i}", [
        Port.point(f"net{i}_a", x1, y1, layer),
        Port.point(f"net{i}_b", x2, y2, layer),
    ]))

# A bunch of small 3-pin nets scattered around, to add more congestion
for i in range(24):
    x1, y1 = round(random.uniform(0, 45)*2)/2, round(random.uniform(0, 45)*2)/2
    x2, y2 = round(random.uniform(0, 45)*2)/2, round(random.uniform(0, 45)*2)/2
    x3, y3 = round(random.uniform(0, 45)*2)/2, round(random.uniform(0, 45)*2)/2
    layer = random.choice(["m1", "m2"])
    nets.append(Net(f"net{i+24}", [
        Port.point(f"net{i+24}_a", x1, y1, layer),
        Port.point(f"net{i+24}_b", x2, y2, layer),
        Port.point(f"net{i+24}_c", x3, y3, layer),
    ]))

router = GDSRouter.from_nets(layout, top, nets, rcfg, pitch_um=0.5, padding_um=15.0)

for net in nets:
    for p in net.ports:
        router.draw_port(p, net.name)

print(f"Grid: {router.grid.cols} x {router.grid.rows} cells "
      f"({router.grid.cols * router.grid.rows} cells/layer, "
      f"{router.grid.lyrs} layers, pitch={router.grid.pitch}um)")

t0 = time.perf_counter()
results = router.route(RouteStrat.MultiStart)
elapsed = time.perf_counter() - t0

n_ok = sum(1 for v in results.values() if v)
print(f"Routed {n_ok}/{len(results)} nets in {elapsed*1000:.1f} ms")
for name, ok in results.items():
    if not ok:
        print(f"  FAILED: {name}")

out_path = "test_route.gds"
layout.write(out_path)
print(f"wrote {out_path}")

# reload sanity check
layout2 = db.Layout()
layout2.read(out_path)
c2 = layout2.top_cell()
total_shapes = sum(c2.shapes(li).size() for li in range(layout2.layers()))
print(f"total shapes in output GDS: {total_shapes}")