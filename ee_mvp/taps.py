"""Helpers for common feeder tap rules (240.21(B))."""

from __future__ import annotations

from typing import Dict, List

import pandas as pd

from .models import Edge, Project
from .nec import ampacity_adjusted


def _current_at_bus(currents: Dict[str, float], bus: str) -> float:
    return float(currents.get(bus, 0.0))


def check_feeder_taps(project: Project, load_currents: Dict[str, float]) -> pd.DataFrame:
    rows: List[Dict[str, object]] = []
    for edge in project.edges:
        cable = edge.cable
        if not cable or not cable.is_tap:
            continue
        ampacity = ampacity_adjusted(
            cable.size_awg,
            cable.conductor,
            cable.insulation,
            cable.temp_rating_C,
            cable.ambient_C,
            cable.rooftop_height_in,
            cable.qty_per_phase * (4 if cable.neutral_counts_as_ccc else 3),
            cable.temp_rating_C,
            cable.qty_per_phase,
        )
        length = cable.length_ft or 0.0
        load = _current_at_bus(load_currents, edge.to_id)
        ten_ft_ok = length <= 10.0 and ampacity >= load and bool(cable.tap_termination_has_ocpd)
        source_ocpd = edge.ocpd.rating_A if edge.ocpd else None
        twentyfive_ok = False
        if length <= 25.0 and source_ocpd:
            twentyfive_ok = ampacity >= source_ocpd / 3.0
        rows.append(
            {
                "from": edge.from_id,
                "to": edge.to_id,
                "length_ft": length,
                "ampacity_A": ampacity,
                "load_A": load,
                "passes_10ft": ten_ft_ok,
                "passes_25ft": twentyfive_ok,
                "passes": ten_ft_ok or twentyfive_ok,
            }
        )
    return pd.DataFrame(rows)
