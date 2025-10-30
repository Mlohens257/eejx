"""Definitions for validation issues returned by validators."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class Issue:
    """Structured validation issue."""

    severity: str
    code: str
    path: str
    message: str
    provenance: Optional[dict] = None

    def to_dict(self) -> dict:
        return {
            "severity": self.severity,
            "code": self.code,
            "path": self.path,
            "message": self.message,
            "provenance": self.provenance,
        }
