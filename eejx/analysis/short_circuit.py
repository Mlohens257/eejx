"""Simplified short-circuit stub calculations."""
from __future__ import annotations

from typing import Dict, Optional

from eejx.schema.models import ProjectGraph


def run_short_circuit_stub(graph: ProjectGraph) -> Dict[str, Dict[str, Optional[float]]]:
    """Propagate the service available fault current downstream without impedance modeling."""

    if not graph.short_circuit or graph.short_circuit.service_available_fault_kA is None:
        return {"per_node": {}}

    base_fault = graph.short_circuit.service_available_fault_kA
    results: Dict[str, Dict[str, Optional[float]]] = {}
    for node in graph.nodes:
        # Placeholder: no impedance reduction yet
        results[node.id] = {"I_sc_kA": base_fault, "method": "stub"}
    return {"per_node": results}


__all__ = ["run_short_circuit_stub"]
