"""Deterministic load calculation routines."""
from __future__ import annotations

import math
from collections import defaultdict, deque
from typing import Dict, List, Optional

from eejx.schema.models import Edge, Node, PanelSchedule, ProjectGraph

SQRT3 = math.sqrt(3)


def _node_base_load_kva(node: Node) -> float:
    if not node.load:
        return 0.0
    kVA = node.load.get("kVA")
    kW = node.load.get("kW")
    pf = node.load.get("pf") or 1.0
    continuous = bool(node.load.get("continuous"))
    base = 0.0
    if kVA is not None:
        base = float(kVA)
    elif kW is not None:
        base = float(kW) / max(pf, 1e-6)
    if continuous:
        base *= 1.25
    return base


def _entry_kva(entry) -> float:
    if entry.kVA is not None:
        value = float(entry.kVA)
    elif entry.kW is not None:
        value = float(entry.kW)
    else:
        return 0.0
    if entry.continuous:
        value *= 1.25
    return value


def _topological_order(nodes: List[Node], edges: List[Edge]) -> List[str]:
    node_ids = [node.id for node in nodes]
    indegree: Dict[str, int] = {node.id: 0 for node in nodes}
    adjacency: Dict[str, List[str]] = defaultdict(list)
    for edge in edges:
        if edge.from_ not in indegree or edge.to not in indegree:
            continue
        adjacency[edge.from_].append(edge.to)
        indegree[edge.to] += 1
    queue = deque([node_id for node_id, deg in indegree.items() if deg == 0])
    order: List[str] = []
    while queue:
        node_id = queue.popleft()
        order.append(node_id)
        for nbr in adjacency.get(node_id, []):
            indegree[nbr] -= 1
            if indegree[nbr] == 0:
                queue.append(nbr)
    return order


def _phase_count(node: Node) -> int:
    if not node.phases:
        return 3
    return len(node.phases)


def _voltage_for_current(node: Node) -> Optional[float]:
    if node.voltage_ll_V:
        if _phase_count(node) == 1:
            return node.voltage_ll_V / math.sqrt(3)
        return node.voltage_ll_V
    return None


def run_load_calc(graph: ProjectGraph) -> Dict[str, Dict[str, Optional[float]]]:
    """Compute connected load, currents, and capacity margin for each node."""

    adjacency: Dict[str, List[str]] = defaultdict(list)
    for edge in graph.edges:
        adjacency[edge.from_].append(edge.to)

    base_loads: Dict[str, float] = {node.id: _node_base_load_kva(node) for node in graph.nodes}
    panel_internal_loads: Dict[str, float] = defaultdict(float)

    for schedule in graph.panel_schedules:
        parent_id = schedule.panel_id
        children = adjacency.get(parent_id, [])
        for entry in schedule.entries:
            value = _entry_kva(entry)
            if value == 0.0:
                continue
            assigned = False
            normalized_desc = (entry.desc or "").upper()
            normalized_ckt = (entry.ckt or "").upper()
            for child_id in children:
                child_token = child_id.upper()
                if child_token and (child_token in normalized_desc or child_token in normalized_ckt):
                    base_loads[child_id] = base_loads.get(child_id, 0.0) + value
                    assigned = True
                    break
            if not assigned:
                panel_internal_loads[parent_id] += value

    for panel_id, value in panel_internal_loads.items():
        base_loads[panel_id] = base_loads.get(panel_id, 0.0) + value

    order = _topological_order(graph.nodes, graph.edges)
    if not order:
        order = [node.id for node in graph.nodes]

    aggregated: Dict[str, float] = {node_id: base_loads.get(node_id, 0.0) for node_id in base_loads}
    for node_id in reversed(order):
        for parent, children in adjacency.items():
            if node_id in children:
                aggregated[parent] = aggregated.get(parent, 0.0) + aggregated.get(node_id, 0.0)

    results: Dict[str, Dict[str, Optional[float]]] = {}
    node_lookup = {node.id: node for node in graph.nodes}
    for node_id, kva in aggregated.items():
        node = node_lookup.get(node_id)
        voltage = _voltage_for_current(node) if node else None
        if voltage and voltage > 0:
            if _phase_count(node) == 1:
                current = kva * 1000 / voltage
            else:
                current = kva * 1000 / (SQRT3 * voltage)
        else:
            current = None
        rating = node.rating_A if node else None
        margin = None
        if current is not None and rating is not None:
            margin = rating - current
        results[node_id] = {
            "kVA_total": kva,
            "kW_total": None,
            "I_A": current,
            "margin_A": margin,
        }
    return results


__all__ = ["run_load_calc"]
