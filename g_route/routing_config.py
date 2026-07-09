"""Port of RoutingConfig.hpp / RoutingConfig.cpp."""
from __future__ import annotations

import json
from typing import Dict, List, Optional, Tuple


class RoutingConfig:
    def __init__(self, cfg: dict):
        self.config: dict = cfg
        layers = cfg["routing_layers"]
        vias = cfg["vias"]

        self.idx_to_layer: List[str] = self._sorted_layers(cfg)
        self.num_layers: int = len(self.idx_to_layer)

        self.layer_to_idx: Dict[str, int] = {}
        self.idx_to_gds: List[Tuple[int, int]] = []
        self.layer_costs: List[float] = []
        self.min_width: List[float] = []
        self.min_spacing: List[float] = []
        self.port_dtype: List[int] = []

        for i, name in enumerate(self.idx_to_layer):
            layer = layers[name]
            self.layer_to_idx[name] = i

            gds = layer["gds_layer"]
            self.idx_to_gds.append((int(gds[0]), int(gds[1])))
            self.layer_costs.append(float(layer["route_cost"]))
            self.min_width.append(float(layer["min_width"]))
            self.min_spacing.append(float(layer["min_spacing"]))
            self.port_dtype.append(int(layer.get("port_dtype", gds[1])))

        self.via_up_costs: Dict[int, float] = {}
        self.via_down_costs: Dict[int, float] = {}
        self.via_up_sizes: Dict[int, float] = {}
        self.via_down_sizes: Dict[int, float] = {}
        self.via_up_enclosures: Dict[int, float] = {}
        self.via_down_enclosures: Dict[int, float] = {}
        self.via_up_gds: Dict[int, Tuple[int, int]] = {}
        self.via_down_gds: Dict[int, Tuple[int, int]] = {}
        self.min_via_cost: float = float("inf")

        for _via_name, via in vias.items():
            lo = self.layer_to_idx[via["lower_metal"]]
            hi = self.layer_to_idx[via["upper_metal"]]
            cost = float(via["cost"])
            gds = via["gds_layer"]

            if cost < self.min_via_cost:
                self.min_via_cost = cost

            self.via_up_costs[lo] = cost
            self.via_up_sizes[lo] = float(via["size"])
            self.via_up_enclosures[lo] = float(via["enclosure_by_lower_metal"])
            self.via_up_gds[lo] = (int(gds[0]), int(gds[1]))

            self.via_down_costs[hi] = cost
            self.via_down_sizes[hi] = float(via["size"])
            self.via_down_enclosures[hi] = float(via["enclosure_by_upper_metal"])
            self.via_down_gds[hi] = (int(gds[0]), int(gds[1]))


    @classmethod
    def from_file(cls, path: str) -> "RoutingConfig":
        with open(path) as f:
            cfg = json.load(f)
        return cls(cfg)

    # -- getters --------------------------------------------------------
    def block_radius_um(self, layer_idx: int, poly: bool = False) -> float:
        if poly:
            return self.min_width[layer_idx] / 2.0 + self.min_spacing[layer_idx]
        return self.min_width[layer_idx] + self.min_spacing[layer_idx]

    def get_min_via_cost(self) -> float:
        return self.min_via_cost

    def get_min_route_cost(self) -> float:
        return min(self.layer_costs) if self.layer_costs else float("inf")

    def get_route_cost(self, layer_idx: int) -> float:
        return self.layer_costs[layer_idx]

    def get_via_up_cost(self, layer_idx: int) -> Optional[float]:
        return self.via_up_costs.get(layer_idx)

    def get_via_down_cost(self, layer_idx: int) -> Optional[float]:
        return self.via_down_costs.get(layer_idx)

    def get_via_up_size(self, layer_idx: int) -> float:
        return self.via_up_sizes[layer_idx]

    def get_via_down_size(self, layer_idx: int) -> float:
        return self.via_down_sizes[layer_idx]

    def get_via_up_enc(self, layer_idx: int) -> float:
        return self.via_up_enclosures[layer_idx]

    def get_via_down_enc(self, layer_idx: int) -> float:
        return self.via_down_enclosures[layer_idx]

    def get_via_up_gds(self, layer_idx: int) -> Tuple[int, int]:
        return self.via_up_gds[layer_idx]

    def get_via_down_gds(self, layer_idx: int) -> Tuple[int, int]:
        return self.via_down_gds[layer_idx]

    def get_gds(self, layer_idx: int) -> Tuple[int, int]:
        return self.idx_to_gds[layer_idx]

    def get_port_dt(self, layer_idx: int) -> int:
        return self.port_dtype[layer_idx]

    def get_num_layers(self) -> int:
        return self.num_layers

    def get_layer_idx(self, layer: str) -> int:
        return self.layer_to_idx[layer]

    def get_route_width(self, layer_idx: int) -> float:
        return self.min_width[layer_idx]

    # -- static -----------------------------------------------------------
    @staticmethod
    def _sorted_layers(cfg: dict) -> List[str]:
        layers = cfg["routing_layers"]
        indexed = sorted((props["vindex"], name) for name, props in layers.items())
        return [name for _, name in indexed]
