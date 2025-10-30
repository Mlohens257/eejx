"""Validator implementations for ProjectGraph objects."""
from __future__ import annotations

import math
from collections import defaultdict, deque
from typing import Dict, Iterable, List, Optional, Set, Tuple

from pydantic import ValidationError

from eejx.schema.models import Edge, Node, ProjectGraph
from eejx.validate.issues import Issue


class ValidationErrorWrapper(Exception):
    """Raised when ProjectGraph instantiation fails."""

    def __init__(self, errors):  # type: ignore[no-untyped-def]
        super().__init__("Invalid ProjectGraph")
        self.errors = errors


def load_project_graph(data: dict) -> ProjectGraph:
    """Instantiate a ProjectGraph from a dict, raising ValidationErrorWrapper on error."""

    try:
        return ProjectGraph.parse_obj(data)
    except ValidationError as exc:  # pragma: no cover - trivial
        raise ValidationErrorWrapper(exc.errors()) from exc


class Validator:
    """Callable validator hook returning a list of issues."""

    def __call__(self, graph: ProjectGraph) -> List[Issue]:  # pragma: no cover - interface
        raise NotImplementedError


class TopologyValidator(Validator):
    """Checks node/edge references and acyclicity."""

    def __call__(self, graph: ProjectGraph) -> List[Issue]:
        issues: List[Issue] = []
        node_ids = {node.id for node in graph.nodes}

        for idx, edge in enumerate(graph.edges):
            if edge.from_ not in node_ids:
                issues.append(
                    Issue(
                        severity="ERROR",
                        code="TOPOLOGY_UNKNOWN_FROM",
                        path=f"edges[{idx}].from",
                        message=f"Edge references unknown node {edge.from_}",
                    )
                )
            if edge.to not in node_ids:
                issues.append(
                    Issue(
                        severity="ERROR",
                        code="TOPOLOGY_UNKNOWN_TO",
                        path=f"edges[{idx}].to",
                        message=f"Edge references unknown node {edge.to}",
                    )
                )

        adjacency: Dict[str, List[str]] = defaultdict(list)
        indegree: Dict[str, int] = {node.id: 0 for node in graph.nodes}
        for edge in graph.edges:
            if edge.from_ in node_ids and edge.to in node_ids:
                adjacency[edge.from_].append(edge.to)
                indegree[edge.to] = indegree.get(edge.to, 0) + 1

        queue: deque[str] = deque([node_id for node_id, deg in indegree.items() if deg == 0])
        visited = 0
        while queue:
            node_id = queue.popleft()
            visited += 1
            for nbr in adjacency.get(node_id, []):
                indegree[nbr] -= 1
                if indegree[nbr] == 0:
                    queue.append(nbr)

        if visited != len(node_ids):
            issues.append(
                Issue(
                    severity="ERROR",
                    code="TOPOLOGY_CYCLE",
                    path="edges",
                    message="Cycle detected in feeder topology",
                )
            )
        return issues


class VoltagePhaseValidator(Validator):
    """Ensures basic voltage/phasing compatibility between connected nodes."""

    def __call__(self, graph: ProjectGraph) -> List[Issue]:
        issues: List[Issue] = []
        node_map = {node.id: node for node in graph.nodes}

        for idx, edge in enumerate(graph.edges):
            upstream = node_map.get(edge.from_)
            downstream = node_map.get(edge.to)
            if not upstream or not downstream:
                continue
            if upstream.voltage_ll_V and downstream.voltage_ll_V:
                if not math.isclose(
                    upstream.voltage_ll_V,
                    downstream.voltage_ll_V,
                    rel_tol=0.05,
                    abs_tol=1e-3,
                ):
                    issues.append(
                        Issue(
                            severity="WARNING",
                            code="VOLTAGE_MISMATCH",
                            path=f"edges[{idx}]",
                            message=(
                                f"Voltage mismatch between {edge.from_} "
                                f"({upstream.voltage_ll_V} V) and {edge.to} "
                                f"({downstream.voltage_ll_V} V)"
                            ),
                        )
                    )
            if upstream.phases and downstream.phases:
                up_phases = set(upstream.phases)
                down_phases = set(downstream.phases)
                if not down_phases.issubset(up_phases):
                    issues.append(
                        Issue(
                            severity="ERROR",
                            code="PHASE_INCOMPATIBLE",
                            path=f"edges[{idx}]",
                            message=(
                                f"Downstream phases {downstream.phases} not available at upstream {upstream.phases}"
                            ),
                        )
                    )
        return issues


class PanelProtectionValidator(Validator):
    """Checks that feeders to panels without mains include an upstream OCPD."""

    def __call__(self, graph: ProjectGraph) -> List[Issue]:
        issues: List[Issue] = []
        node_map = {node.id: node for node in graph.nodes}

        incoming_edges: Dict[str, List[Tuple[int, Edge]]] = defaultdict(list)
        for idx, edge in enumerate(graph.edges):
            incoming_edges[edge.to].append((idx, edge))

        for node in graph.nodes:
            if node.type != "panel":
                continue
            if node.mlo is False or node.mlo is None:
                for idx, edge in incoming_edges.get(node.id, []):
                    if edge.ocpd is None:
                        issues.append(
                            Issue(
                                severity="WARNING",
                                code="MISSING_OCPD",
                                path=f"edges[{idx}].ocpd",
                                message=f"Panel {node.id} is not MLO; feeder should include OCPD",
                            )
                        )
            else:
                # MLO panels require upstream protection
                if not incoming_edges.get(node.id):
                    continue
                for idx, edge in incoming_edges[node.id]:
                    if edge.ocpd is None:
                        issues.append(
                            Issue(
                                severity="ERROR",
                                code="MLO_REQUIRES_OCPD",
                                path=f"edges[{idx}].ocpd",
                                message=f"Panel {node.id} is MLO but feeder lacks OCPD",
                            )
                        )
        return issues


AMPACITY_TABLE = {
    "Cu": {
        "#14": 20,
        "#12": 25,
        "#10": 35,
        "#8": 50,
        "#6": 65,
        "#4": 85,
        "#3": 100,
        "#2": 115,
        "#1": 130,
        "1/0": 150,
        "2/0": 175,
        "3/0": 200,
        "4/0": 230,
        "250": 255,
        "300": 285,
        "350": 310,
        "400": 335,
        "500": 380,
    },
    "Al": {
        "#12": 20,
        "#10": 30,
        "#8": 40,
        "#6": 50,
        "#4": 65,
        "#3": 75,
        "#2": 90,
        "#1": 100,
        "1/0": 120,
        "2/0": 135,
        "3/0": 155,
        "4/0": 180,
        "250": 205,
        "300": 230,
        "350": 250,
        "400": 270,
        "500": 310,
    },
}


def _normalize_conductor_size(size: str) -> Optional[str]:
    size = size.strip().upper().replace("KCMIL", "").strip()
    if size.startswith("#"):
        return size
    if "/" in size:
        return size
    if size.endswith("MM2"):
        return None
    return size


class AmpacityValidator(Validator):
    """Simple ampacity check using placeholder lookup table."""

    def __call__(self, graph: ProjectGraph) -> List[Issue]:
        issues: List[Issue] = []
        for idx, edge in enumerate(graph.edges):
            if not edge.ocpd or edge.ocpd.rating_A is None:
                continue
            if not edge.cable:
                continue
            size_key = edge.cable.size_awg
            normalized = _normalize_conductor_size(size_key)
            if normalized is None:
                continue
            table = AMPACITY_TABLE.get(edge.cable.conductor)
            if not table:
                continue
            ampacity = table.get(normalized)
            if ampacity is None:
                continue
            effective_ampacity = ampacity * max(edge.cable.qty_per_phase, 1)
            if edge.ocpd.rating_A > effective_ampacity:
                issues.append(
                    Issue(
                        severity="WARNING",
                        code="AMPACITY_LT_OCPD",
                        path=f"edges[{idx}].cable.size_awg",
                        message=(
                            f"Feeder ampacity {effective_ampacity}A < OCPD rating {edge.ocpd.rating_A}A"
                        ),
                    )
                )
        return issues


class CoverageValidator(Validator):
    """Ensures required data are present for enabled analyses."""

    def __call__(self, graph: ProjectGraph) -> List[Issue]:
        issues: List[Issue] = []
        if graph.analysis_flags.short_circuit:
            if not graph.short_circuit or graph.short_circuit.service_available_fault_kA is None:
                issues.append(
                    Issue(
                        severity="ERROR",
                        code="SHORT_CIRCUIT_INPUT_MISSING",
                        path="short_circuit.service_available_fault_kA",
                        message="Short-circuit analysis enabled but service fault current missing",
                    )
                )
        if graph.analysis_flags.load:
            panels_with_entries: Set[str] = {
                schedule.panel_id for schedule in graph.panel_schedules if schedule.entries
            }
            loads_present = any(
                (node.load and (node.load.get("kVA") or node.load.get("kW"))) for node in graph.nodes
            )
            if not panels_with_entries and not loads_present:
                issues.append(
                    Issue(
                        severity="WARNING",
                        code="LOAD_INPUT_INCOMPLETE",
                        path="panel_schedules",
                        message="Load analysis enabled but no panel schedules or node loads provided",
                    )
                )
        return issues


VALIDATORS: List[Validator] = [
    TopologyValidator(),
    VoltagePhaseValidator(),
    PanelProtectionValidator(),
    AmpacityValidator(),
    CoverageValidator(),
]


def validate_project(graph: ProjectGraph) -> List[Issue]:
    """Run all validators and return a flat list of issues."""

    issues: List[Issue] = []
    for validator in VALIDATORS:
        issues.extend(validator(graph))
    return issues


__all__ = [
    "Issue",
    "ValidationErrorWrapper",
    "validate_project",
    "load_project_graph",
]
