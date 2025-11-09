"""NEC-centric helpers: ampacity, adjustments, EGC sizing, and raceway fill."""

from __future__ import annotations

from functools import lru_cache
from math import pi, sqrt
from pathlib import Path
from typing import Dict, Iterable, Tuple

import csv


class TableLookupError(ValueError):
    """Raised when a lookup against the embedded placeholder tables fails."""


_TABLE_DIR = Path(__file__).with_suffix("").parent / "tables"


def _load_table(filename: str) -> Iterable[Dict[str, str]]:
    path = _TABLE_DIR / filename
    with open(path, "r", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            yield row


@lru_cache(maxsize=1)
def _ampacity_table() -> Dict[Tuple[str, str, int], Dict[str, float]]:
    table: Dict[Tuple[str, str, int], Dict[str, float]] = {}
    for row in _load_table("nec_310_16_stub.csv"):
        key = (row["material"].strip().upper(), row["insulation"].strip().upper(), int(row["temp_C"]))
        size_map = table.setdefault(key, {})
        size_map[row["size_awg"].strip()] = float(row["ampacity_A"])
    return table


@lru_cache(maxsize=None)
def _conductor_od_table() -> Dict[str, float]:
    return {row["size_awg"].strip(): float(row["od_in"]) for row in _load_table("conductor_od_stub.csv")}


@lru_cache(maxsize=None)
def _emt_area_table() -> Dict[float, float]:
    return {float(row["trade_size_in"]): float(row["area_sq_in"]) for row in _load_table("emt_area_stub.csv")}


@lru_cache(maxsize=1)
def _egc_table() -> Tuple[list[tuple[int, str]], list[tuple[int, str]]]:
    cu: list[tuple[int, str]] = []
    al: list[tuple[int, str]] = []
    for row in _load_table("egc_table_stub.csv"):
        limit = int(row["ocpd_max_A"])
        cu.append((limit, row["cu_size_awg"].strip()))
        al.append((limit, row["al_size_awg"].strip()))
    return cu, al


_OHMS_PER_KFT_R = {
    "CU": {
        "#3": 0.197,
        "#2": 0.1563,
        "#1": 0.1249,
        "1/0": 0.099,
        "2/0": 0.0785,
        "3/0": 0.0624,
        "4/0": 0.0495,
        "250": 0.041,
        "300": 0.0345,
        "350": 0.0298,
        "400": 0.026,
        "500": 0.0209,
        "600": 0.0174,
    },
    "AL": {
        "1/0": 0.158,
        "2/0": 0.125,
        "3/0": 0.099,
        "4/0": 0.078,
        "250": 0.067,
        "300": 0.056,
        "350": 0.048,
        "400": 0.043,
        "500": 0.034,
        "600": 0.029,
    },
}

_INSTALLATION_X_PER_KFT = {
    "EMT": 0.085,
    "PVC": 0.065,
    "RMC": 0.09,
}


def _normalize_material(material: str) -> str:
    mat = material.strip().upper()
    if mat.startswith("CU"):
        return "CU"
    if mat.startswith("AL"):
        return "AL"
    raise TableLookupError(f"Unknown conductor material '{material}'.")


def _normalize_insulation(insulation: str) -> str:
    text = insulation.strip().upper().replace(" ", "")
    aliases = {
        "THHN/THWN-2": "THHN",
        "THWN-2": "THHN",
        "XHHW2": "XHHW-2",
        "THHN2": "THHN",
    }
    return aliases.get(text, text)


def _temperature_column(temp_C: int | None) -> int:
    if temp_C is None:
        return 75
    return 90 if temp_C >= 90 else (75 if temp_C >= 75 else 60)


def ampacity_base(size_awg: str, material: str, insulation: str, temp_C: int | None = None) -> float:
    """Return the base ampacity from the stubbed 310.16 table."""
    key = (_normalize_material(material), _normalize_insulation(insulation), _temperature_column(temp_C))
    table = _ampacity_table().get(key)
    if not table and key[0] == "AL":
        alt_key = (key[0], "XHHW-2", key[2])
        table = _ampacity_table().get(alt_key)
        if table:
            key = alt_key
    if not table or size_awg not in table:
        raise TableLookupError(
            "No 310.16 table entry for material=%s insulation=%s temp=%s size=%s"
            % (key[0], key[1], key[2], size_awg)
        )
    return table[size_awg]


def ambient_correction_factor(temp_C: int, ambient_C: float | None, rooftop_height_in: float | None) -> float:
    """Return an ambient correction factor using a simplified curve."""
    ambient = 30.0 if ambient_C is None else float(ambient_C)
    if rooftop_height_in is not None and rooftop_height_in <= 12:
        ambient += 17.0
    if temp_C <= 60:
        ref = [(30, 1.0), (35, 0.88), (40, 0.82), (45, 0.71)]
    elif temp_C <= 75:
        ref = [(30, 1.0), (35, 0.94), (40, 0.88), (45, 0.82)]
    else:
        ref = [(30, 1.0), (35, 0.96), (40, 0.91), (45, 0.87)]
    factor = ref[-1][1]
    for limit, value in ref:
        if ambient <= limit:
            factor = value
            break
    return factor


def conductor_correction_factor(ccc: int) -> float:
    if ccc <= 3:
        return 1.0
    if ccc <= 6:
        return 0.8
    if ccc <= 9:
        return 0.7
    return 0.5


def terminal_temperature_limit(temp_C: int | None) -> int:
    if temp_C is None:
        return 75
    return _temperature_column(temp_C)


def ampacity_adjusted(
    size_awg: str,
    material: str,
    insulation: str,
    temp_C: int,
    ambient_C: float | None,
    rooftop_height_in: float | None,
    ccc: int,
    term_temp_C: int | None,
    parallel_sets: int = 1,
) -> float:
    base = ampacity_base(size_awg, material, insulation, temp_C)
    amb = ambient_correction_factor(temp_C, ambient_C, rooftop_height_in)
    bundling = conductor_correction_factor(ccc)
    terminal_limit = ampacity_base(size_awg, material, insulation, terminal_temperature_limit(term_temp_C))
    adjusted = min(base * amb * bundling, terminal_limit)
    return adjusted * max(1, int(parallel_sets))


def resistance_per_kft(material: str, size_awg: str) -> float:
    mat = _normalize_material(material)
    try:
        return _OHMS_PER_KFT_R[mat][size_awg]
    except KeyError as exc:  # pragma: no cover - friendly message exercised indirectly
        raise TableLookupError(f"No resistance data for {mat} conductor size {size_awg}.") from exc


def reactance_per_kft(installation: str) -> float:
    inst = installation.strip().upper()
    try:
        return _INSTALLATION_X_PER_KFT[inst]
    except KeyError as exc:  # pragma: no cover
        raise TableLookupError(f"No reactance data for installation '{installation}'.") from exc


def conductor_area_sq_in(size_awg: str) -> float:
    try:
        od = _conductor_od_table()[size_awg]
    except KeyError as exc:  # pragma: no cover
        raise TableLookupError(f"No conductor OD defined for size {size_awg}.") from exc
    radius = od / 2.0
    return pi * radius * radius


def emt_area_sq_in(trade_size_in: float) -> float:
    table = _emt_area_table()
    if trade_size_in not in table:  # pragma: no cover
        raise TableLookupError(f"No EMT area for trade size {trade_size_in} in.")
    return table[trade_size_in]


def minimum_raceway_size(conductors: Iterable[tuple[str, int]], fill_fraction: float = 0.4) -> float:
    required_area = 0.0
    for size_awg, qty in conductors:
        required_area += conductor_area_sq_in(size_awg) * qty
    for trade_size, area in sorted(_emt_area_table().items()):
        if required_area <= area * fill_fraction:
            return trade_size
    return max(_emt_area_table())


def equipment_ground_size(ocpd_rating_A: float, material: str = "Cu") -> str:
    cu_table, al_table = _egc_table()
    table = cu_table if _normalize_material(material) == "CU" else al_table
    rating = float(ocpd_rating_A)
    for limit, awg in table:
        if rating <= limit:
            return awg
    return table[-1][1]


def upsized_equipment_ground(ocpd_rating_A: float, conductor_upsizing_factor: float, material: str = "Cu") -> str:
    base = equipment_ground_size(ocpd_rating_A, material=material)
    if conductor_upsizing_factor <= 1.05:
        return base
    order = [
        "#14",
        "#12",
        "#10",
        "#8",
        "#6",
        "#4",
        "#3",
        "#2",
        "#1",
        "1/0",
        "2/0",
        "3/0",
        "4/0",
        "250",
        "300",
        "350",
        "400",
        "500",
        "600",
    ]
    try:
        idx = order.index(base)
    except ValueError:  # pragma: no cover - base table limited to order
        return base
    bump = 1 if conductor_upsizing_factor < 1.35 else 2
    return order[min(idx + bump, len(order) - 1)]


def percent_voltage_drop(current_A: float, voltage_ll_V: float, resistance_ohm: float, reactance_ohm: float, pf: float) -> float:
    if voltage_ll_V <= 0:
        return 0.0
    pf = max(0.0, min(1.0, pf))
    sinphi = sqrt(max(0.0, 1.0 - pf * pf))
    return (sqrt(3.0) * current_A * (resistance_ohm * pf + reactance_ohm * sinphi) / voltage_ll_V) * 100.0
