"""Data models for the electrical-engineering MVP toolkit."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import json

from pydantic import BaseModel, Field, ValidationError


class EEValidationError(ValueError):
    """Raised when incoming project data cannot be validated."""


@dataclass
class OCPD:
    type: str
    rating_A: float
    interrupting_rating_kA: Optional[float] = None


@dataclass
class Cable:
    conductor: str
    size_awg: str
    qty_per_phase: int
    installation: str = "EMT"
    insulation: str = "THHN"
    temp_rating_C: int = 75
    conduit_trade_size_in: Optional[float] = None
    egc_awg: Optional[str] = None
    length_ft: Optional[float] = None
    neutral_counts_as_ccc: bool = False
    rooftop_height_in: Optional[float] = None
    ambient_C: Optional[float] = 30.0
    is_branch: bool = False
    is_feeder: bool = True
    is_tap: bool = False
    tap_rule: Optional[str] = None
    tap_termination_has_ocpd: Optional[bool] = None


@dataclass
class Edge:
    from_id: str
    to_id: str
    ocpd: Optional[OCPD] = None
    cable: Optional[Cable] = None


@dataclass
class Node:
    id: str
    type: str
    voltage_ll_V: Optional[float] = None
    phases: Optional[str] = None
    rating_A: Optional[float] = None
    mlo: Optional[bool] = None
    kVA: Optional[float] = None
    pri_V: Optional[float] = None
    sec_V: Optional[float] = None
    Z_pct: Optional[float] = None
    XR_ratio: Optional[float] = None
    available_fault_kA: Optional[float] = None
    sccr_kA: Optional[float] = None


@dataclass
class PanelEntry:
    ckt: str
    desc: str
    kVA: float
    cont: bool = False
    phases: str = "ABC"
    pf: Optional[float] = None
    category: Optional[str] = None
    location: Optional[str] = None


@dataclass
class PanelSchedule:
    panel_id: str
    entries: List[PanelEntry] = field(default_factory=list)


@dataclass
class Project:
    name: str
    code: Dict[str, Any]
    analysis_flags: Dict[str, bool]
    settings: Dict[str, Any]
    assumptions: List[Dict[str, Any]]
    sources: List[Dict[str, Any]]
    nodes: List[Node]
    edges: List[Edge]
    panel_schedules: List[PanelSchedule]
    schema_version: str = "0.1.0"


class _BaseModel(BaseModel):
    model_config = {
        "populate_by_name": True,
        "extra": "forbid",
    }


class OCPDModel(_BaseModel):
    type: str
    rating_A: float
    interrupting_rating_kA: Optional[float] = None

    def to_dataclass(self) -> OCPD:
        return OCPD(**self.model_dump())


class CableModel(_BaseModel):
    conductor: str
    size_awg: str
    qty_per_phase: int = Field(ge=1)
    installation: str = "EMT"
    insulation: str = "THHN"
    temp_rating_C: int = 75
    conduit_trade_size_in: Optional[float] = Field(default=None, ge=0)
    egc_awg: Optional[str] = None
    length_ft: Optional[float] = Field(default=None, ge=0)
    neutral_counts_as_ccc: bool = False
    rooftop_height_in: Optional[float] = Field(default=None, ge=0)
    ambient_C: Optional[float] = None
    is_branch: bool = False
    is_feeder: bool = True
    is_tap: bool = False
    tap_rule: Optional[str] = None
    tap_termination_has_ocpd: Optional[bool] = None

    def to_dataclass(self) -> Cable:
        return Cable(**self.model_dump())


class EdgeModel(_BaseModel):
    from_id: str
    to_id: str
    ocpd: Optional[OCPDModel] = None
    cable: Optional[CableModel] = None

    def to_dataclass(self) -> Edge:
        data = self.model_dump()
        ocpd = self.ocpd.to_dataclass() if self.ocpd else None
        cable = self.cable.to_dataclass() if self.cable else None
        return Edge(from_id=data["from_id"], to_id=data["to_id"], ocpd=ocpd, cable=cable)


class NodeModel(_BaseModel):
    id: str
    type: str
    voltage_ll_V: Optional[float] = None
    phases: Optional[str] = None
    rating_A: Optional[float] = None
    mlo: Optional[bool] = None
    kVA: Optional[float] = None
    pri_V: Optional[float] = None
    sec_V: Optional[float] = None
    Z_pct: Optional[float] = None
    XR_ratio: Optional[float] = None
    available_fault_kA: Optional[float] = None
    sccr_kA: Optional[float] = None

    def to_dataclass(self) -> Node:
        return Node(**self.model_dump())


class PanelEntryModel(_BaseModel):
    ckt: str
    desc: str
    kVA: float
    cont: bool = False
    phases: str = "ABC"
    pf: Optional[float] = None
    category: Optional[str] = None
    location: Optional[str] = None

    def to_dataclass(self) -> PanelEntry:
        return PanelEntry(**self.model_dump())


class PanelScheduleModel(_BaseModel):
    panel_id: str
    entries: List[PanelEntryModel] = Field(default_factory=list)

    def to_dataclass(self) -> PanelSchedule:
        return PanelSchedule(
            panel_id=self.panel_id,
            entries=[entry.to_dataclass() for entry in self.entries],
        )


class ProjectModel(_BaseModel):
    name: str
    code: Dict[str, Any]
    analysis_flags: Dict[str, bool]
    settings: Dict[str, Any]
    assumptions: List[Dict[str, Any]]
    sources: List[Dict[str, Any]]
    nodes: List[NodeModel]
    edges: List[EdgeModel]
    panel_schedules: List[PanelScheduleModel]
    schema_version: str = "0.1.0"

    def to_dataclass(self) -> Project:
        return Project(
            name=self.name,
            code=self.code,
            analysis_flags=self.analysis_flags,
            settings=self.settings,
            assumptions=self.assumptions,
            sources=self.sources,
            nodes=[node.to_dataclass() for node in self.nodes],
            edges=[edge.to_dataclass() for edge in self.edges],
            panel_schedules=[sched.to_dataclass() for sched in self.panel_schedules],
            schema_version=self.schema_version,
        )


def load_project(data: Dict[str, Any]) -> Project:
    """Validate a project dictionary and return a :class:`Project` instance."""
    try:
        model = ProjectModel.model_validate(data)
    except ValidationError as exc:  # pragma: no cover - exercised indirectly
        raise EEValidationError(str(exc)) from exc
    return model.to_dataclass()


def load_project_file(path: str | Path) -> Project:
    """Load and validate a project definition from a JSON file."""
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    return load_project(data)
