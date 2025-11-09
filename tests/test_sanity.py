from pathlib import Path

from ee_mvp import DEFAULT_CONFIG, analyze
from ee_mvp.models import load_project_file


def test_demo_project_runs(tmp_path):
    project = load_project_file(Path(__file__).resolve().parents[1] / "examples" / "demo_project.json")
    results = analyze(project, DEFAULT_CONFIG, write_csv=True, out_dir=tmp_path)
    assert all(not frame.empty for frame in results.values())
    # CSV outputs plus run_meta.json should exist
    expected_files = {
        "panel_summary.csv",
        "edge_checks.csv",
        "voltage_drop_totals.csv",
        "short_circuit.csv",
        "tap_checks.csv",
        "run_meta.json",
    }
    actual = {path.name for path in tmp_path.iterdir()}
    assert expected_files.issubset(actual)


def test_demo_project_runs_from_json_string():
    project_path = Path(__file__).resolve().parents[1] / "examples" / "demo_project.json"
    project_json = project_path.read_text()
    results = analyze(project_json, DEFAULT_CONFIG)
    assert all(not frame.empty for frame in results.values())


def test_results_expose_rows_attribute():
    project_path = Path(__file__).resolve().parents[1] / "examples" / "demo_project.json"
    project = project_path.read_text()
    results = analyze(project, DEFAULT_CONFIG)
    for frame in results.values():
        assert hasattr(frame, "_rows")
        assert frame._rows == frame.to_dict("records")


def test_rows_attribute_persists_on_copy():
    project_path = Path(__file__).resolve().parents[1] / "examples" / "demo_project.json"
    project = project_path.read_text()
    results = analyze(project, DEFAULT_CONFIG)
    for frame in results.values():
        clone = frame.copy()
        assert hasattr(clone, "_rows")
        assert clone._rows == clone.to_dict("records")
