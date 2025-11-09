"""Voltage-drop utilities built on top of :mod:`ee_mvp.nec`."""

from __future__ import annotations

from typing import Tuple

from .nec import percent_voltage_drop, reactance_per_kft, resistance_per_kft


def conductor_impedance(
    material: str,
    size_awg: str,
    length_ft: float,
    installation: str,
    qty_per_phase: int = 1,
) -> Tuple[float, float]:
    """Return the total resistance and reactance for a run of conductor."""
    qty = max(1, int(qty_per_phase))
    factor = float(length_ft) / 1000.0
    r = resistance_per_kft(material, size_awg) * factor / qty
    x = reactance_per_kft(installation) * factor / qty
    return r, x


def voltage_drop_percent(
    current_A: float,
    voltage_ll_V: float,
    material: str,
    size_awg: str,
    length_ft: float,
    installation: str,
    qty_per_phase: int = 1,
    pf: float = 0.9,
) -> float:
    r, x = conductor_impedance(material, size_awg, length_ft, installation, qty_per_phase)
    return percent_voltage_drop(current_A, voltage_ll_V, r, x, pf)
