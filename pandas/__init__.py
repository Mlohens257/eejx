"""A tiny subset of pandas sufficient for unit testing in this project."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, Iterable, Iterator, List, Sequence

import csv


Number = (int, float)


class DataFrame:
    def __init__(self, rows: Iterable[Dict[str, Any]] | None = None):
        self._rows: List[Dict[str, Any]] = [dict(row) for row in (rows or [])]
        self._columns: List[str] = list(self._rows[0].keys()) if self._rows else []

    @property
    def empty(self) -> bool:
        return not self._rows

    @property
    def columns(self) -> List[str]:
        return list(self._columns)

    def iterrows(self) -> Iterator[tuple[int, Dict[str, Any]]]:
        for idx, row in enumerate(self._rows):
            yield idx, dict(row)

    def to_csv(self, path, index: bool = False) -> None:
        if self.empty:
            with open(path, "w", encoding="utf-8", newline="") as fh:
                fh.write("")
            return
        with open(path, "w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=self._columns)
            writer.writeheader()
            for row in self._rows:
                writer.writerow({col: row.get(col, "") for col in self._columns})

    def copy(self) -> "DataFrame":
        return DataFrame(deepcopy(self._rows))

    def select_dtypes(self, include: Sequence[str] | str | None = None) -> "DataFrame":
        if include is None:
            return self.copy()
        if isinstance(include, str):
            include = [include]
        numeric_cols = []
        if "number" in include:
            for col in self._columns:
                if all(isinstance(row.get(col), Number) for row in self._rows if col in row):
                    numeric_cols.append(col)
        new_rows = [{col: row.get(col) for col in numeric_cols} for row in self._rows]
        df = DataFrame(new_rows)
        df._columns = numeric_cols
        return df

    def round(self, digits: int) -> "DataFrame":
        for row in self._rows:
            for key, value in list(row.items()):
                if isinstance(value, Number):
                    row[key] = round(value, digits)
        return self

    def __iter__(self):
        return iter(self._rows)

    def __len__(self) -> int:
        return len(self._rows)

    def __getitem__(self, item: str) -> List[Any]:
        return [row.get(item) for row in self._rows]

    def __repr__(self) -> str:  # pragma: no cover - debugging helper
        return f"DataFrame({self._rows!r})"


__all__ = ["DataFrame"]
