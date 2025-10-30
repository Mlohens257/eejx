# eejx
Deterministic EE toolchain with LLM extraction → typed project graph → validated calcs (load, VD, SCC stub).

## Features

* JSON schema + lightweight Pydantic-compatible models for the project graph.
* Deterministic validators covering topology, voltage/phase compatibility, basic ampacity checks, and analysis coverage.
* Analysis modules for load calculation, voltage drop, and a short-circuit stub.
* CLI for validation, analysis, and export flows (`python -m eejx.cli --help`).
* Panel schedule CSV and thin one-line JSON exporters.

## Development

Run the unit tests with:

```
pytest
```
