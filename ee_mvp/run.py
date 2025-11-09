"""Primary entry point for running the EE MVP analysis."""

from __future__ import annotations

from datetime import datetime, timezone
from math import sqrt
from numbers import Real
from pathlib import Path
from typing import Dict, List, Tuple

import json

import pandas as pd
from pandas.api.types import is_bool_dtype

from .models import PanelSchedule, Project, load_project, load_project_file
from .version import EE_MVP_VERSION
from .nec import ampacity_adjusted, minimum_raceway_size, upsized_equipment_ground
from .scc import available_fault
from .taps import check_feeder_taps
from .vd import voltage_drop_percent

SQRT3 = sqrt(3.0)

DEFAULT_CONFIG = {
    "pf": 0.9,
    "vd_branch_pct": 3.0,
    "vd_feeder_pct": 3.0,
    "vd_total_pct": 5.0,
}


def load_config(config: Dict[str, float] | None = None) -> Dict[str, float]:
    merged = dict(DEFAULT_CONFIG)
    if config:
        merged.update(config)
    return merged


def _ensure_project(project: Project | Dict | str | Path) -> Project:
    if isinstance(project, Project):
        return project
    if isinstance(project, str):
        stripped = project.strip()
        if stripped.startswith("{") or stripped.startswith("["):
            try:
                data = json.loads(project)
            except json.JSONDecodeError:
                pass
            else:
                return load_project(data)
        return load_project_file(project)
    if isinstance(project, Path):
        return load_project_file(project)
    if isinstance(project, dict):
        return load_project(project)
    raise TypeError("Unsupported project payload")


class _Calculator:
    def __init__(self, project: Project, config: Dict[str, float]):
        self.project = project
        self.config = config
        self.parents: Dict[str, List[str]] = {}
        self.children: Dict[str, List[str]] = {}
        for edge in project.edges:
            self.parents.setdefault(edge.to_id, []).append(edge.from_id)
            self.children.setdefault(edge.from_id, []).append(edge.to_id)
        self.schedule: Dict[str, PanelSchedule] = {sched.panel_id: sched for sched in project.panel_schedules}
        self.currents: Dict[str, float] = {}

    def _topological_order(self) -> List[str]:
        indegree: Dict[str, int] = {node.id: 0 for node in self.project.nodes}
        for to_id, parents in self.parents.items():
            indegree[to_id] = indegree.get(to_id, 0) + len(parents)
        queue = [node_id for node_id, deg in indegree.items() if deg == 0]
        order: List[str] = []
        while queue:
            node_id = queue.pop(0)
            order.append(node_id)
            for child in self.children.get(node_id, []):
                indegree[child] -= 1
                if indegree[child] == 0:
                    queue.append(child)
        return order

    @staticmethod
    def _schedule_totals(schedule: PanelSchedule) -> Tuple[float, float]:
        cont = 0.0
        noncont = 0.0
        for entry in schedule.entries:
            if entry.cont:
                cont += entry.kVA
            else:
                noncont += entry.kVA
        return cont, noncont

    @staticmethod
    def _node_voltage(node) -> float:
        return node.voltage_ll_V or node.sec_V or node.pri_V or 0.0

    def panel_summary(self) -> pd.DataFrame:
        roll_map: Dict[str, float] = {node.id: 0.0 for node in self.project.nodes}
        rows: List[Dict[str, object]] = []
        for node in self.project.nodes:
            schedule = self.schedule.get(node.id, PanelSchedule(panel_id=node.id, entries=[]))
            cont, noncont = self._schedule_totals(schedule)
            design = cont * 1.25 + noncont
            roll_map[node.id] = design
            rows.append(
                {
                    "bus": node.id,
                    "type": node.type,
                    "V_ll": self._node_voltage(node),
                    "rating_A": node.rating_A,
                    "kVA_cont": cont,
                    "kVA_noncont": noncont,
                    "kVA_design": design,
                }
            )
        for node_id in reversed(self._topological_order()):
            load = roll_map.get(node_id, 0.0)
            for parent in self.parents.get(node_id, []):
                roll_map[parent] = roll_map.get(parent, 0.0) + load
        summary_rows: List[Dict[str, object]] = []
        for row in rows:
            total = roll_map[row["bus"]]
            voltage = row["V_ll"] or 0.0
            current = total * 1000.0 / (SQRT3 * voltage) if voltage else 0.0
            self.currents[row["bus"]] = current
            rating = row["rating_A"] or 0.0
            utilization = (current / rating * 100.0) if rating else 0.0
            summary_rows.append({**row, "kVA_total": total, "I_design_A": current, "utilization_pct": utilization})
        return pd.DataFrame(summary_rows)

    def edge_checks(self) -> pd.DataFrame:
        pf = self.config.get("pf", 0.9)
        branch_limit = self.config.get("vd_branch_pct", 3.0)
        feeder_limit = self.config.get("vd_feeder_pct", 3.0)
        rows: List[Dict[str, object]] = []
        for edge in self.project.edges:
            cable = edge.cable
            if not cable or not cable.size_awg:
                continue
            load_current = self.currents.get(edge.to_id, 0.0)
            ccc = cable.qty_per_phase * (4 if cable.neutral_counts_as_ccc else 3)
            ampacity = ampacity_adjusted(
                cable.size_awg,
                cable.conductor,
                cable.insulation,
                cable.temp_rating_C,
                cable.ambient_C,
                cable.rooftop_height_in,
                ccc,
                cable.temp_rating_C,
                cable.qty_per_phase,
            )
            length = cable.length_ft or 0.0
            voltage = 0.0
            to_node = next((n for n in self.project.nodes if n.id == edge.to_id), None)
            if to_node:
                voltage = self._node_voltage(to_node)
            vd_pct = 0.0
            if length and voltage:
                vd_pct = voltage_drop_percent(
                    load_current,
                    voltage,
                    cable.conductor,
                    cable.size_awg,
                    length,
                    cable.installation,
                    cable.qty_per_phase,
                    pf,
                )
            limit = branch_limit if cable.is_branch else feeder_limit
            ampacity_margin = ampacity - load_current
            ocpd_rating = edge.ocpd.rating_A if edge.ocpd else load_current * 1.25
            base_ampacity = ampacity_adjusted(
                cable.size_awg,
                cable.conductor,
                cable.insulation,
                90,
                cable.ambient_C,
                cable.rooftop_height_in,
                ccc,
                90,
                cable.qty_per_phase,
            )
            upsizing_factor = base_ampacity / ampacity if ampacity else 1.0
            egc = upsized_equipment_ground(ocpd_rating, upsizing_factor, material=cable.conductor)
            conduit = minimum_raceway_size([(cable.size_awg, cable.qty_per_phase * 3), (egc, cable.qty_per_phase)])
            rows.append(
                {
                    "from": edge.from_id,
                    "to": edge.to_id,
                    "size_awg": cable.size_awg,
                    "qty_per_phase": cable.qty_per_phase,
                    "length_ft": length,
                    "ampacity_A": ampacity,
                    "load_A": load_current,
                    "ampacity_margin_A": ampacity_margin,
                    "vd_pct": vd_pct,
                    "vd_ok": vd_pct <= limit,
                    "egc_awg": egc,
                    "min_conduit_in": conduit,
                }
            )
        return pd.DataFrame(rows)

    def total_voltage_drop(self, edge_df: pd.DataFrame) -> pd.DataFrame:
        totals: Dict[str, float] = {node.id: 0.0 for node in self.project.nodes}
        vd_map: Dict[Tuple[str, str], float] = {}
        for _, row in edge_df.iterrows():
            vd_map[(row["from"], row["to"])] = row["vd_pct"]
        order = self._topological_order()
        for node_id in order:
            for child in self.children.get(node_id, []):
                totals[child] = totals[node_id] + vd_map.get((node_id, child), 0.0)
        records: List[Dict[str, object]] = []
        limit = self.config.get("vd_total_pct", 5.0)
        for node in self.project.nodes:
            voltage = self._node_voltage(node)
            if not voltage:
                continue
            total_vd = totals.get(node.id, 0.0)
            records.append({"bus": node.id, "total_vd_pct": total_vd, "vd_total_ok": total_vd <= limit})
        return pd.DataFrame(records)


class _AnalysisDataFrame(pd.DataFrame):
    """``DataFrame`` subclass that preserves a ``_rows`` attribute."""

    _metadata = ["_rows"]

    @property
    def _constructor(self):  # pragma: no cover - inherited behavior exercised indirectly
        return _AnalysisDataFrame


def _attach_rows_attr(df: pd.DataFrame) -> pd.DataFrame:
    """Attach a ``_rows`` attribute with the frame's record representation."""

    frame = _AnalysisDataFrame(df) if not isinstance(df, _AnalysisDataFrame) else df
    frame._rows = frame.to_dict("records")
    return frame


def _rounded(df: pd.DataFrame, digits: int = 3) -> pd.DataFrame:
    if df.empty:
        return _attach_rows_attr(df.copy())
    rounded = df.copy()
    for column in rounded.columns:
        series = rounded[column]
        if is_bool_dtype(series):
            continue
        mask = series.apply(lambda value: isinstance(value, Real) and not isinstance(value, bool))
        if mask.any():
            rounded.loc[mask, column] = series[mask].apply(lambda value: round(value, digits))
    return _attach_rows_attr(rounded)


def _write_csv(path: Path, df: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)


def _write_meta(path: Path, project: Project) -> None:
    meta = {
        "version": EE_MVP_VERSION,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "nec_year": project.code.get("nec_year"),
        "assumptions": project.assumptions,
    }
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(meta, fh, indent=2)


def analyze(
    project: Project | Dict | str | Path,
    config: Dict[str, float] | None = None,
    write_csv: bool = False,
    out_dir: str | Path | None = None,
) -> Dict[str, pd.DataFrame]:
    """Run the full analysis and optionally emit CSV outputs."""
    proj = _ensure_project(project)
    cfg = load_config(config)
    calc = _Calculator(proj, cfg)
    panel_df = calc.panel_summary()
    edge_df = calc.edge_checks()
    total_vd_df = calc.total_voltage_drop(edge_df)
    scc_df = available_fault(proj)
    tap_df = check_feeder_taps(proj, calc.currents)

    results = {
        "panel_summary": _rounded(panel_df),
        "edge_checks": _rounded(edge_df),
        "voltage_drop_totals": _rounded(total_vd_df),
        "short_circuit": _rounded(scc_df),
        "tap_checks": _rounded(tap_df),
    }

    if write_csv:
        directory = Path(out_dir or "analysis_outputs")
        _write_csv(directory / "panel_summary.csv", results["panel_summary"])
        _write_csv(directory / "edge_checks.csv", results["edge_checks"])
        _write_csv(directory / "voltage_drop_totals.csv", results["voltage_drop_totals"])
        _write_csv(directory / "short_circuit.csv", results["short_circuit"])
        _write_csv(directory / "tap_checks.csv", results["tap_checks"])
        _write_meta(directory / "run_meta.json", proj)

    return results
