"""blueprints/<name>/ handling: build.py -> blueprint.txt + previews, spec.toml -> simulation."""

from __future__ import annotations

import importlib.util
import json
import sys
import tomllib
import warnings
from dataclasses import dataclass
from pathlib import Path

from . import codec, layout, render, validate
from .sim import runner


def repo_root() -> Path:
    for parent in [Path.cwd(), *Path.cwd().parents]:
        if (parent / "blueprints").is_dir() and (parent / "pyproject.toml").is_file():
            return parent
    return Path(__file__).resolve().parents[2]


def project_dir(name: str) -> Path:
    path = Path(name)
    if not path.is_dir():
        path = repo_root() / "blueprints" / name
    if not (path / "build.py").is_file():
        raise FileNotFoundError(f"{path}/build.py not found (expected blueprints/<name>/build.py)")
    return path


def load_string(arg: str) -> str:
    """Blueprint string from: '-', a file, a project name/dir, or the literal string itself."""
    if arg == "-":
        return sys.stdin.read().strip()
    path = Path(arg)
    if path.is_file():
        text = path.read_text().strip()
        return codec.encode(json.loads(text)) if text.startswith("{") else text
    for candidate in (path / "blueprint.txt", repo_root() / "blueprints" / arg / "blueprint.txt"):
        if candidate.is_file():
            return candidate.read_text().strip()
    if arg.startswith("0") and len(arg) > 40:
        return arg
    raise FileNotFoundError(f"no blueprint found for '{arg}'")


@dataclass
class Built:
    directory: Path
    string: str
    layout: layout.Layout
    issues: list[validate.Issue]


def build(name: str, *, write: bool = True) -> Built:
    directory = project_dir(name)
    spec = importlib.util.spec_from_file_location(f"fbp_build_{directory.name.replace('-', '_')}", directory / "build.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if not hasattr(module, "build"):
        raise AttributeError(f"{directory}/build.py must define build() returning a draftsman Blueprint")
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        bp = module.build()
        string = bp.to_string()
    lay = layout.from_dict(codec.decode(string))
    issues = validate.validate(lay)
    for w in caught:  # draftsman's own complaints (bad recipe, overlap, unknown name...)
        text = " ".join(str(w.message).split())
        issues.append(validate.Issue("warning", "draftsman", text[:300] + ("..." if len(text) > 300 else "")))
    if write:
        (directory / "blueprint.txt").write_text(string + "\n")
        (directory / "preview.txt").write_text(render.ascii_art(lay))
        render.png(lay, directory / "preview.png")
    return Built(directory, string, lay, issues)


def load_spec(directory: Path) -> tuple[list[runner.Target], runner.SimSpec]:
    path = directory / "spec.toml"
    if not path.is_file():
        raise FileNotFoundError(f"{path} not found: it defines targets and the [sim] inputs/outputs")
    data = tomllib.loads(path.read_text())
    targets = [runner.Target(t["item"], float(t["per_minute"]), float(t.get("tolerance", 0.05)))
               for t in data.get("target", [])]
    return targets, runner.SimSpec.from_dict(data.get("sim", {}))
