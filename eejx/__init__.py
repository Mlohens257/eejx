"""Deterministic EE toolchain public interface with lazy imports."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover - import-time helpers for type checkers
    from .analysis.load_calc import run_load_calc
    from .analysis.short_circuit import run_short_circuit_stub
    from .analysis.voltage_drop import run_voltage_drop
    from .export.panel import export_panel_csv
    from .schema.models import ProjectGraph
    from .validate import (
        Issue,
        ValidationErrorWrapper,
        load_project_graph,
        validate_project,
    )

__all__ = [
    "ProjectGraph",
    "run_load_calc",
    "run_voltage_drop",
    "run_short_circuit_stub",
    "export_panel_csv",
    "validate_project",
    "load_project_graph",
    "ValidationErrorWrapper",
    "Issue",
]


def __getattr__(name: str) -> Any:  # pragma: no cover - thin compatibility shim
    if name == "ProjectGraph":
        from .schema.models import ProjectGraph as _ProjectGraph

        return _ProjectGraph
    if name == "run_load_calc":
        from .analysis.load_calc import run_load_calc as _run_load_calc

        return _run_load_calc
    if name == "run_voltage_drop":
        from .analysis.voltage_drop import run_voltage_drop as _run_voltage_drop

        return _run_voltage_drop
    if name == "run_short_circuit_stub":
        from .analysis.short_circuit import (
            run_short_circuit_stub as _run_short_circuit_stub,
        )

        return _run_short_circuit_stub
    if name == "export_panel_csv":
        from .export.panel import export_panel_csv as _export_panel_csv

        return _export_panel_csv
    if name == "validate_project":
        from .validate import validate_project as _validate_project

        return _validate_project
    if name == "load_project_graph":
        from .validate import load_project_graph as _load_project_graph

        return _load_project_graph
    if name == "ValidationErrorWrapper":
        from .validate import (
            ValidationErrorWrapper as _ValidationErrorWrapper,
        )

        return _ValidationErrorWrapper
    if name == "Issue":
        from .validate import Issue as _Issue

        return _Issue
    raise AttributeError(name)


def __dir__() -> list[str]:  # pragma: no cover - interactive helper
    return sorted(__all__)
