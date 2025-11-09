"""Short-circuit calculations using a simple Thevenin back-bone."""

from __future__ import annotations

from collections import deque
from math import sqrt
from typing import Dict

import pandas as pd

from .models import Edge, Project
from .nec import reactance_per_kft, resistance_per_kft

SQRT3 = sqrt(3.0)


def _edge_impedance(edge: Edge) -> complex:
    if not edge.cable or not edge.cable.length_ft or not edge.cable.size_awg:
        return complex(0.0, 0.0)
    qty = max(1, edge.cable.qty_per_phase)
    factor = edge.cable.length_ft / 1000.0 / qty
    r = resistance_per_kft(edge.cable.conductor, edge.cable.size_awg) * factor
    x = reactance_per_kft(edge.cable.installation) * factor
    return complex(r, x)


def _initial_impedance(project: Project) -> Dict[str, complex]:
    values: Dict[str, complex] = {}
    for node in project.nodes:
        voltage = node.voltage_ll_V or node.pri_V or node.sec_V
        if not voltage:
            continue
        if node.available_fault_kA:
            i = node.available_fault_kA * 1000.0
            z = voltage / (SQRT3 * i)
            values[node.id] = complex(z, 0.0)
    return values


def available_fault(project: Project) -> pd.DataFrame:
    """Return a dataframe with the approximate available fault at each bus."""
    z_map = _initial_impedance(project)
    children: Dict[str, list[Edge]] = {}
    for edge in project.edges:
        children.setdefault(edge.from_id, []).append(edge)
    queue = deque(z_map.keys())
    seen = set()
    while queue:
        parent_id = queue.popleft()
        parent_z = z_map.get(parent_id)
        if parent_z is None:
            continue
        for edge in children.get(parent_id, []):
            key = (edge.from_id, edge.to_id)
            if key in seen:
                continue
            seen.add(key)
            z_map[edge.to_id] = parent_z + _edge_impedance(edge)
            queue.append(edge.to_id)
    rows = []
    for node in project.nodes:
        z = z_map.get(node.id)
        if not z:
            continue
        voltage = node.voltage_ll_V or node.sec_V or node.pri_V
        if not voltage:
            continue
        fault = voltage / (SQRT3 * abs(z)) / 1000.0
        rows.append({"bus": node.id, "available_fault_kA": fault, "Z_th_ohm": abs(z)})
    return pd.DataFrame(rows)
