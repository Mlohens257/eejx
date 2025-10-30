"""Pydantic models describing the ProjectGraph schema."""
from __future__ import annotations

from typing import List, Optional, Literal, Dict, Any

from pydantic import BaseModel, Field


class Provenance(BaseModel):
    """Reference back to the source material for a field."""

    source_id: str
    page: Optional[int] = None
    bbox: Optional[List[float]] = None
    text: Optional[str] = None
    confidence: Optional[float] = None


class OCPD(BaseModel):
    type: Literal["breaker", "fuse", "switch"]
    rating_A: Optional[float] = None


class Cable(BaseModel):
    conductor: Literal["Cu", "Al"]
    size_awg: str
    qty_per_phase: int = 1
    egc_awg: Optional[str] = None
    length_ft: Optional[float] = None


class Node(BaseModel):
    id: str
    type: Literal[
        "utility_service",
        "xfmr_dry",
        "xfmr_oil",
        "switchboard",
        "mst",
        "panel",
        "disconnect",
        "mcc",
        "load",
    ]
    name: Optional[str] = None
    voltage_ll_V: Optional[float] = None
    phases: Optional[Literal["A", "B", "C", "AB", "BC", "CA", "ABC"]] = None
    rating_A: Optional[float] = None
    mlo: Optional[bool] = None
    xfmr: Optional[Dict[str, Any]] = None
    load: Optional[Dict[str, Any]] = None
    provenance: Optional[Provenance] = None


class Edge(BaseModel):
    from_: str = Field(..., alias="from")
    to: str
    ocpd: Optional[OCPD] = None
    cable: Optional[Cable] = None
    provenance: Optional[Provenance] = None

    class Config:
        allow_population_by_field_name = True


class PanelEntry(BaseModel):
    ckt: str
    desc: str
    kVA: Optional[float] = None
    kW: Optional[float] = None
    continuous: Optional[bool] = None
    provenance: Optional[Provenance] = None


class PanelSchedule(BaseModel):
    panel_id: str
    entries: List[PanelEntry] = []


class CodeCtx(BaseModel):
    nec_year: int
    jurisdiction: str
    amendments: List[str] = []


class ProjectCtx(BaseModel):
    name: str
    code: CodeCtx


class AnalysisFlags(BaseModel):
    load: bool = True
    voltage_drop: bool = True
    short_circuit: bool = False


class ShortCircuitCtx(BaseModel):
    service_available_fault_kA: Optional[float] = None


class ProjectGraph(BaseModel):
    schema_version: str = "0.1.0"
    project: ProjectCtx
    analysis_flags: AnalysisFlags
    assumptions: List[Dict[str, Any]] = []
    sources: List[Dict[str, Any]] = []
    nodes: List[Node]
    edges: List[Edge]
    panel_schedules: List[PanelSchedule] = []
    short_circuit: Optional[ShortCircuitCtx] = None

    class Config:
        allow_population_by_field_name = True
