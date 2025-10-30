import json
from pathlib import Path

import pytest

from eejx import (
    ProjectGraph,
    export_panel_csv,
    run_load_calc,
    run_short_circuit_stub,
    run_voltage_drop,
    validate_project,
)


@pytest.fixture
def sample_graph_dict() -> dict:
    return {
        "schema_version": "0.1.0",
        "project": {
            "name": "4380 Mission Blvd – Subpanel Add",
            "code": {"nec_year": 2020, "jurisdiction": "CA", "amendments": []},
        },
        "analysis_flags": {"load": True, "voltage_drop": True, "short_circuit": False},
        "assumptions": [{"id": "A1", "text": "Assume 30 kA at service until utility confirms"}],
        "sources": [{"id": "S1", "file": "E1.0.pdf"}],
        "nodes": [
            {"id": "UTIL1", "type": "utility_service", "voltage_ll_V": 208, "phases": "ABC"},
            {"id": "P4L4D", "type": "panel", "voltage_ll_V": 208, "phases": "ABC", "rating_A": 400},
            {
                "id": "NEW-SP",
                "type": "panel",
                "voltage_ll_V": 208,
                "phases": "ABC",
                "rating_A": 100,
                "mlo": True,
            },
        ],
        "edges": [
            {"from": "UTIL1", "to": "P4L4D"},
            {
                "from": "P4L4D",
                "to": "NEW-SP",
                "ocpd": {"type": "breaker", "rating_A": 100},
                "cable": {
                    "conductor": "Cu",
                    "size_awg": "#1",
                    "qty_per_phase": 3,
                    "egc_awg": "#8",
                    "length_ft": 135,
                },
            },
        ],
        "panel_schedules": [
            {
                "panel_id": "P4L4D",
                "entries": [
                    {"ckt": "5-7", "desc": "NEW-SP feeder", "kVA": 36.0, "continuous": True}
                ],
            }
        ],
        "short_circuit": {"service_available_fault_kA": None},
    }


@pytest.fixture
def sample_graph(sample_graph_dict: dict) -> ProjectGraph:
    return ProjectGraph.parse_obj(sample_graph_dict)


def test_validate_sample_graph(sample_graph: ProjectGraph) -> None:
    issues = validate_project(sample_graph)
    severities = {issue.severity for issue in issues}
    assert "ERROR" not in severities


def test_load_calc(sample_graph: ProjectGraph) -> None:
    results = run_load_calc(sample_graph)
    new_sp = results["NEW-SP"]
    assert pytest.approx(new_sp["kVA_total"], rel=1e-3) == 45.0
    assert new_sp["I_A"] is not None
    assert new_sp["I_A"] > 90


def test_voltage_drop(sample_graph: ProjectGraph) -> None:
    load_results = run_load_calc(sample_graph)
    vd_results = run_voltage_drop(sample_graph, load_results)
    edge_results = vd_results["per_edge"]["edge_1"]
    assert edge_results["pct"] is not None
    assert edge_results["pct"] > 0


def test_export_panel(tmp_path: Path, sample_graph: ProjectGraph) -> None:
    output_file = tmp_path / "panel.csv"
    export_panel_csv(sample_graph, str(output_file))
    contents = output_file.read_text(encoding="utf-8")
    assert "panel_id" in contents
    assert "NEW-SP feeder" in contents


def test_short_circuit_stub(sample_graph_dict: dict) -> None:
    graph_dict = json.loads(json.dumps(sample_graph_dict))
    graph_dict["analysis_flags"]["short_circuit"] = True
    graph_dict["short_circuit"] = {"service_available_fault_kA": 30.0}
    graph = ProjectGraph.parse_obj(graph_dict)
    results = run_short_circuit_stub(graph)
    assert results["per_node"]["P4L4D"]["I_sc_kA"] == 30.0
