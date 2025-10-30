from pathlib import Path

import build_backend as backend


def test_project_metadata_matches_pyproject():
    meta = backend._read_project_metadata()
    assert meta.name == "eejx"
    assert meta.version == "0.1.0"
    assert meta.requires_python == ">=3.10"
    assert "typer[all]>=0.9" in meta.dependencies
    assert "rich>=13.0" in meta.dependencies
    assert meta.scripts == {"eejx": "eejx.cli:main"}


def test_build_artifacts(tmp_path: Path):
    metadata_dir = tmp_path / "meta"
    wheel_dir = tmp_path / "wheel"
    sdist_dir = tmp_path / "sdist"
    metadata_dir.mkdir()
    wheel_dir.mkdir()
    sdist_dir.mkdir()

    dist_info = backend.prepare_metadata_for_build_wheel(str(metadata_dir))
    assert dist_info.endswith(".dist-info")

    wheel_name = backend.build_wheel(str(wheel_dir), metadata_directory=str(metadata_dir))
    assert (wheel_dir / wheel_name).exists()

    sdist_name = backend.build_sdist(str(sdist_dir))
    assert (sdist_dir / sdist_name).exists()
