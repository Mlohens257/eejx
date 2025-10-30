"""Export helpers for panel schedules."""
from __future__ import annotations

import csv
from pathlib import Path

from eejx.schema.models import ProjectGraph


def export_panel_csv(graph: ProjectGraph, path: str) -> None:
    """Write panel schedules to CSV."""

    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(["panel_id", "ckt", "desc", "kVA", "kW", "continuous"])
        for schedule in graph.panel_schedules:
            for entry in schedule.entries:
                writer.writerow(
                    [
                        schedule.panel_id,
                        entry.ckt,
                        entry.desc,
                        entry.kVA if entry.kVA is not None else "",
                        entry.kW if entry.kW is not None else "",
                        entry.continuous if entry.continuous is not None else "",
                    ]
                )


__all__ = ["export_panel_csv"]
