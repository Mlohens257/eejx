"""Voltage drop calculations using placeholder conductor impedance tables."""
from __future__ import annotations

import math
from typing import Dict, List, Optional

from eejx.schema.models import Edge, ProjectGraph

SQRT3 = math.sqrt(3)

RESISTANCE_OHMS_PER_1000FT = {
    "Cu": {
        "#14": 3.14,
        "#12": 1.98,
        "#10": 1.24,
        "#8": 0.778,
        "#6": 0.491,
        "#4": 0.308,
        "#3": 0.245,
        "#2": 0.194,
        "#1": 0.154,
        "1/0": 0.122,
        "2/0": 0.097,
        "3/0": 0.077,
        "4/0": 0.061,
        "250": 0.052,
        "300": 0.043,
        "350": 0.037,
        "400": 0.033,
        "500": 0.028,
    },
    "Al": {
        "#12": 3.19,
        "#10": 1.99,
        "#8": 1.26,
        "#6": 0.791,
        "#4": 0.497,
        "#3": 0.395,
        "#2": 0.313,
        "#1": 0.249,
        "1/0": 0.197,
        "2/0": 0.156,
        "3/0": 0.124,
        "4/0": 0.098,
        "250": 0.082,
        "300": 0.069,
        "350": 0.059,
        "400": 0.051,
        "500": 0.041,
    },
}

REACTANCE_OHMS_PER_1000FT = 0.08  # placeholder average reactance


def _normalize_size(size: str) -> Optional[str]:
    size = size.strip().upper().replace("KCMIL", "").strip()
    if size.startswith("#") or "/" in size:
        return size
    if size.isdigit():
        return size
    return None


def _edge_current(edge: Edge, load_results: Dict[str, Dict[str, Optional[float]]]) -> Optional[float]:
    downstream = load_results.get(edge.to)
    if downstream:
        return downstream.get("I_A")
    return None


def _voltage_for_node(graph: ProjectGraph, node_id: str) -> Optional[float]:
    for node in graph.nodes:
        if node.id == node_id:
            return node.voltage_ll_V
    return None


def _phase_count(graph: ProjectGraph, node_id: str) -> int:
    for node in graph.nodes:
        if node.id == node_id:
            if node.phases:
                return len(node.phases)
            return 3
    return 3


def run_voltage_drop(
    graph: ProjectGraph,
    load_results: Dict[str, Dict[str, Optional[float]]],
) -> Dict[str, Dict[str, Dict[str, Optional[float]]]]:
    """Compute per-edge and per-path voltage drop results."""

    per_edge: Dict[str, Dict[str, Optional[float]]] = {}
    edge_lookup: Dict[str, Edge] = {}

    for idx, edge in enumerate(graph.edges):
        edge_id = f"edge_{idx}"
        edge_lookup[edge_id] = edge
        if not edge.cable or edge.cable.length_ft is None:
            per_edge[edge_id] = {"V_drop": None, "pct": None}
            continue
        normalized = _normalize_size(edge.cable.size_awg)
        if normalized is None:
            per_edge[edge_id] = {"V_drop": None, "pct": None}
            continue
        table = RESISTANCE_OHMS_PER_1000FT.get(edge.cable.conductor)
        if not table:
            per_edge[edge_id] = {"V_drop": None, "pct": None}
            continue
        resistance = table.get(normalized)
        if resistance is None:
            per_edge[edge_id] = {"V_drop": None, "pct": None}
            continue
        current = _edge_current(edge, load_results)
        if current is None:
            per_edge[edge_id] = {"V_drop": None, "pct": None}
            continue
        effective_resistance = resistance / max(edge.cable.qty_per_phase, 1)
        length_kft = edge.cable.length_ft / 1000.0
        r_total = effective_resistance * length_kft
        x_total = REACTANCE_OHMS_PER_1000FT * length_kft
        pf = 0.95
        cos_theta = pf
        sin_theta = math.sqrt(max(0.0, 1 - pf ** 2))
        impedance_drop = current * (r_total * cos_theta + x_total * sin_theta)
        phase_count = _phase_count(graph, edge.to)
        if phase_count == 1:
            voltage_drop = 2 * impedance_drop
            nominal_voltage = _voltage_for_node(graph, edge.to)
            if nominal_voltage:
                nominal_voltage /= math.sqrt(3)
        else:
            voltage_drop = SQRT3 * impedance_drop
            nominal_voltage = _voltage_for_node(graph, edge.to)
        pct = (voltage_drop / nominal_voltage * 100) if voltage_drop is not None and nominal_voltage else None
        per_edge[edge_id] = {"V_drop": voltage_drop, "pct": pct}

    per_path: Dict[str, Dict[str, Optional[float]]] = {}

    # Build incoming edge mapping for path accumulation
    incoming_edges: Dict[str, List[str]] = {}
    for edge_id, edge in edge_lookup.items():
        incoming_edges.setdefault(edge.to, []).append(edge_id)

    memo: Dict[str, Dict[str, Optional[float]]] = {}

    def accumulate(node_id: str) -> Dict[str, Optional[float]]:
        if node_id in memo:
            return memo[node_id]
        edges_in = incoming_edges.get(node_id, [])
        if not edges_in:
            memo[node_id] = {"V_drop": 0.0, "pct": 0.0}
            return memo[node_id]
        max_drop = 0.0
        max_pct = 0.0
        for edge_id in edges_in:
            edge = edge_lookup[edge_id]
            upstream = edge.from_
            upstream_drop = accumulate(upstream)
            edge_drop = per_edge[edge_id]["V_drop"] or 0.0
            edge_pct = per_edge[edge_id]["pct"] or 0.0
            total_drop = (upstream_drop["V_drop"] or 0.0) + edge_drop
            total_pct = (upstream_drop["pct"] or 0.0) + edge_pct
            if total_drop > max_drop:
                max_drop = total_drop
                max_pct = total_pct
        memo[node_id] = {"V_drop": max_drop, "pct": max_pct}
        return memo[node_id]

    for node in graph.nodes:
        if node.id not in memo:
            memo[node.id] = accumulate(node.id)
        per_path[node.id] = memo[node.id]

    return {"per_edge": per_edge, "per_path": per_path}


__all__ = ["run_voltage_drop"]
