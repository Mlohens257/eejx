# EE MVP

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/example/eejx/blob/main/examples/demo_notebook.ipynb)

Bootstrap package for lightweight NEC-inspired electrical-engineering analysis. The
project ships with a tiny data set so the utilities can be exercised without
shipping licensed NEC tables.

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
pytest
```

Then explore the [demo notebook](examples/demo_notebook.ipynb) locally or open it
in Colab using the badge above.

## Features

- Dataclasses with Pydantic validation for project inputs.
- Simplified ampacity, voltage-drop, short-circuit, and feeder-tap helpers.
- CSV emission with accompanying metadata for reproducibility.
