"""Typer-based CLI for eejx operations."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import typer

from eejx.analysis.load_calc import run_load_calc
from eejx.analysis.short_circuit import run_short_circuit_stub
from eejx.analysis.voltage_drop import run_voltage_drop
from eejx.export.panel import export_panel_csv
from eejx.schema.models import ProjectGraph
from eejx.validate import ValidationErrorWrapper, load_project_graph, validate_project

app = typer.Typer(help="Deterministic EE toolchain")


@app.command()
def ingest(src: Path = typer.Option(..., exists=True, help="Source documents directory"), out: Path = typer.Option(..., help="Output chunk path")) -> None:
    """Placeholder ingest command."""

    typer.echo("Ingest pipeline is not implemented in this MVP. Provide pre-processed chunks.")


@app.command()
def extract(chunks: Path = typer.Option(..., exists=True, help="Chunk directory"), out: Path = typer.Option(..., help="Output graph JSON path")) -> None:
    """Placeholder extraction command."""

    typer.echo("Extraction requires the LLM agent and is not implemented as a standalone CLI command.")


@app.command()
def validate(graph: Path = typer.Option(..., exists=True, help="Project graph JSON"), report: Optional[Path] = typer.Option(None, help="Validation report output path")) -> None:
    """Validate a project graph JSON file."""

    data = json.loads(graph.read_text(encoding="utf-8"))
    try:
        project_graph = load_project_graph(data)
    except ValidationErrorWrapper as exc:
        typer.echo("Schema validation failed:")
        typer.echo(json.dumps(exc.errors, indent=2))
        raise typer.Exit(code=1)

    issues = [issue.to_dict() for issue in validate_project(project_graph)]
    if report:
        report_path = report
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(issues, indent=2), encoding="utf-8")
    else:
        typer.echo(json.dumps(issues, indent=2))

    exit_code = 1 if any(issue["severity"] == "ERROR" for issue in issues) else 0
    raise typer.Exit(code=exit_code)


@app.command()
def analyze(graph: Path = typer.Option(..., exists=True, help="Project graph JSON"), out: Path = typer.Option(..., help="Analysis results output")) -> None:
    """Run deterministic analyses against a project graph."""

    data = json.loads(graph.read_text(encoding="utf-8"))
    project_graph = ProjectGraph.parse_obj(data)

    results = {}
    load_results = {}
    if project_graph.analysis_flags.load:
        load_results = run_load_calc(project_graph)
        results["load"] = load_results
    if project_graph.analysis_flags.voltage_drop:
        results["voltage_drop"] = run_voltage_drop(project_graph, load_results)
    if project_graph.analysis_flags.short_circuit:
        results["short_circuit"] = run_short_circuit_stub(project_graph)

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(results, indent=2), encoding="utf-8")
    typer.echo(f"Analysis results written to {out}")


@app.command()
def export(
    graph: Path = typer.Option(..., exists=True, help="Project graph JSON"),
    results: Optional[Path] = typer.Option(None, help="Analysis results JSON"),
    out: Path = typer.Option(..., help="Export directory"),
) -> None:
    """Export panel schedules and thin one-line data."""

    data = json.loads(graph.read_text(encoding="utf-8"))
    project_graph = ProjectGraph.parse_obj(data)

    out.mkdir(parents=True, exist_ok=True)
    export_panel_csv(project_graph, str(out / "panel_schedule.csv"))

    one_line_path = out / "one_line.json"
    one_line_payload = {"nodes": [node.dict(by_alias=True) for node in project_graph.nodes], "edges": [edge.dict(by_alias=True) for edge in project_graph.edges]}
    one_line_path.write_text(json.dumps(one_line_payload, indent=2), encoding="utf-8")

    if results:
        (out / "results.json").write_text(results.read_text(encoding="utf-8"), encoding="utf-8")

    typer.echo(f"Exports written to {out}")


def main() -> None:  # pragma: no cover - entry point
    app()


if __name__ == "__main__":  # pragma: no cover - module execution
    main()
