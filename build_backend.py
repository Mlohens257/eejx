from __future__ import annotations

import base64
import dataclasses
import hashlib
import os
import re
import tarfile
import textwrap
import zipfile
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Sequence, Tuple

_ROOT = Path(__file__).resolve().parent
_PACKAGE_DIRS = ("eejx", "pydantic")
_EXTRA_ROOT_FILES = ("build_backend.py",)


@dataclasses.dataclass(frozen=True)
class ProjectMetadata:
    name: str
    version: str
    description: str
    requires_python: str
    dependencies: Sequence[str]
    scripts: Dict[str, str]

    @property
    def normalized_name(self) -> str:
        return self.name.replace("-", "_")

    @property
    def dist_info_dir(self) -> str:
        return f"{self.normalized_name}-{self.version}.dist-info"


def _read_project_metadata() -> ProjectMetadata:
    text = (_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    project_block = _extract_table(text, "project")
    scripts_block = _extract_table(text, "project.scripts", required=False)

    name = _extract_string(project_block, "name")
    version = _extract_string(project_block, "version")
    description = _extract_string(project_block, "description")
    requires_python = _extract_string(project_block, "requires-python")
    dependencies = _extract_list(project_block, "dependencies")
    scripts = _extract_kv_pairs(scripts_block)
    return ProjectMetadata(
        name=name,
        version=version,
        description=description,
        requires_python=requires_python,
        dependencies=tuple(dependencies),
        scripts=scripts,
    )


def _extract_table(text: str, table_path: str, required: bool = True) -> str:
    pattern = re.compile(rf"^\[{re.escape(table_path)}\]\s*$", re.MULTILINE)
    match = pattern.search(text)
    if not match:
        if required:
            raise RuntimeError(f"Unable to locate [{table_path}] in pyproject.toml")
        return ""
    start = match.end()
    any_table_pattern = re.compile(r"^\[[^\]]+\]\s*$", re.MULTILINE)
    following = any_table_pattern.search(text, start)
    end = following.start() if following else len(text)
    return text[start:end]


def _extract_string(block: str, key: str) -> str:
    pattern = re.compile(rf"^{re.escape(key)}\s*=\s*\"([^\"]*)\"\s*$", re.MULTILINE)
    match = pattern.search(block)
    if not match:
        raise RuntimeError(f"Missing {key} in pyproject.toml")
    return match.group(1)


def _extract_list(block: str, key: str) -> List[str]:
    values: List[str] = []
    start_pattern = re.compile(rf"^{re.escape(key)}\s*=\s*\[(.*)$", re.MULTILINE)
    match = start_pattern.search(block)
    if not match:
        return values

    remainder = match.group(1).strip()
    if remainder.endswith("]") and remainder.count("\"") >= 2:
        inline = remainder[:-1].strip()
        if inline:
            values.extend(_split_inline_list(inline))
        return values

    list_block = block[match.end() :]
    for line in list_block.splitlines():
        stripped = line.split("#", 1)[0].strip()
        if not stripped:
            continue
        if stripped.startswith("]"):
            break
        if stripped.endswith(","):
            stripped = stripped[:-1].strip()
        if stripped.startswith("\"") and stripped.endswith("\""):
            values.append(stripped[1:-1])
    return values


def _split_inline_list(text: str) -> List[str]:
    items: List[str] = []
    current: List[str] = []
    in_string = False
    escape = False
    for char in text:
        if escape:
            current.append(char)
            escape = False
            continue
        if char == "\\" and in_string:
            escape = True
            current.append(char)
            continue
        if char == '"':
            in_string = not in_string
            current.append(char)
            continue
        if char == "," and not in_string:
            item = "".join(current).strip()
            if item.startswith('"') and item.endswith('"'):
                items.append(item[1:-1])
            current = []
            continue
        current.append(char)
    item = "".join(current).strip()
    if item.startswith('"') and item.endswith('"'):
        items.append(item[1:-1])
    return items


def _extract_kv_pairs(block: str) -> Dict[str, str]:
    entries: Dict[str, str] = {}
    for line in block.splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        if "=" not in line:
            continue
        key, value = [part.strip() for part in line.split("=", 1)]
        if value.startswith('"') and value.endswith('"'):
            entries[key] = value[1:-1]
    return entries


def prepare_metadata_for_build_wheel(
    metadata_directory: str, config_settings: Optional[Dict[str, str]] = None
) -> str:
    project = _read_project_metadata()
    metadata_path = Path(metadata_directory) / project.dist_info_dir
    metadata_path.mkdir(parents=True, exist_ok=True)

    (metadata_path / "METADATA").write_text(_render_metadata(project), encoding="utf-8")
    (metadata_path / "WHEEL").write_text(_render_wheel_file(), encoding="utf-8")
    if project.scripts:
        (metadata_path / "entry_points.txt").write_text(
            _render_entry_points(project), encoding="utf-8"
        )
    return metadata_path.name


def get_requires_for_build_wheel(
    config_settings: Optional[Dict[str, str]] = None
) -> Sequence[str]:
    return ()


def build_wheel(
    wheel_directory: str,
    config_settings: Optional[Dict[str, str]] = None,
    metadata_directory: Optional[str] = None,
) -> str:
    project = _read_project_metadata()
    if metadata_directory:
        dist_info_dir = Path(metadata_directory) / project.dist_info_dir
        metadata_bytes = {
            "METADATA": (dist_info_dir / "METADATA").read_bytes(),
            "WHEEL": (dist_info_dir / "WHEEL").read_bytes(),
        }
        entry_points_path = dist_info_dir / "entry_points.txt"
        if entry_points_path.exists():
            metadata_bytes["entry_points.txt"] = entry_points_path.read_bytes()
    else:
        metadata_bytes = {
            "METADATA": _render_metadata(project).encode("utf-8"),
            "WHEEL": _render_wheel_file().encode("utf-8"),
        }
        entry_points_content = _render_entry_points(project)
        if entry_points_content:
            metadata_bytes["entry_points.txt"] = entry_points_content.encode("utf-8")

    wheel_name = f"{project.normalized_name}-{project.version}-py3-none-any.whl"
    wheel_path = Path(wheel_directory) / wheel_name

    records: List[Tuple[str, bytes]] = []

    with zipfile.ZipFile(wheel_path, "w") as zf:
        for path, arcname in _package_files():
            data = path.read_bytes()
            zf.writestr(arcname, data)
            records.append((arcname, data))

        for filename in _EXTRA_ROOT_FILES:
            root_file = _ROOT / filename
            if root_file.exists():
                data = root_file.read_bytes()
                zf.writestr(filename, data)
                records.append((filename, data))

        dist_info_prefix = f"{project.dist_info_dir}/"
        for filename, data in metadata_bytes.items():
            arcname = dist_info_prefix + filename
            zf.writestr(arcname, data)
            records.append((arcname, data))

        record_content = _render_record(records, dist_info_prefix + "RECORD")
        zf.writestr(dist_info_prefix + "RECORD", record_content)

    return wheel_name


def build_sdist(
    sdist_directory: str, config_settings: Optional[Dict[str, str]] = None
) -> str:
    project = _read_project_metadata()
    sdist_name = f"{project.name}-{project.version}.tar.gz"
    sdist_path = Path(sdist_directory) / sdist_name
    root_prefix = Path(f"{project.name}-{project.version}")

    with tarfile.open(sdist_path, "w:gz") as tf:
        def add_file(path: Path, arcname: Path) -> None:
            tf.add(path, arcname=str(arcname))

        add_file(_ROOT / "pyproject.toml", root_prefix / "pyproject.toml")
        readme = _ROOT / "README.md"
        if readme.exists():
            add_file(readme, root_prefix / "README.md")

        for filename in _EXTRA_ROOT_FILES:
            root_file = _ROOT / filename
            if root_file.exists():
                add_file(root_file, root_prefix / filename)

        for path, arcname in _package_files():
            add_file(path, root_prefix / arcname)

    return sdist_name


def _package_files() -> Iterator[Tuple[Path, str]]:
    for package in _PACKAGE_DIRS:
        package_root = _ROOT / package
        for path in package_root.rglob("*"):
            if not path.is_file():
                continue
            if path.name.endswith(".pyc") or path.name == "__pycache__":
                continue
            rel = path.relative_to(_ROOT)
            yield path, str(rel).replace(os.sep, "/")


def _render_metadata(project: ProjectMetadata) -> str:
    lines = [
        "Metadata-Version: 2.1",
        f"Name: {project.name}",
        f"Version: {project.version}",
        f"Summary: {project.description}",
        f"Requires-Python: {project.requires_python}",
    ]
    for dependency in project.dependencies:
        lines.append(f"Requires-Dist: {dependency}")
    return "\n".join(lines) + "\n"


def _render_wheel_file() -> str:
    return textwrap.dedent(
        """\
        Wheel-Version: 1.0
        Generator: eejx-build-backend 1.0
        Root-Is-Purelib: true
        Tag: py3-none-any
        """
    ).strip() + "\n"


def _render_entry_points(project: ProjectMetadata) -> str:
    if not project.scripts:
        return ""
    lines = ["[console_scripts]"]
    for name, target in sorted(project.scripts.items()):
        lines.append(f"{name} = {target}")
    return "\n".join(lines) + "\n"


def _render_record(records: Sequence[Tuple[str, bytes]], record_path: str) -> str:
    entries = []
    for arcname, data in records:
        digest = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=")
        entries.append(f"{arcname},sha256={digest.decode()},{len(data)}")
    entries.append(f"{record_path},,")
    return "\n".join(entries) + "\n"
