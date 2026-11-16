"""Run a blueprint in a real headless Factorio and measure what it produces."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_INSTALL = Path.home() / ".cache" / "factorio-headless" / "factorio"
HARNESS = Path(__file__).with_name("control.lua")
# Statuses that mean "this machine is doing its job".
WORKING = {"working", "normal", "low_power", "fully_charged", "charging", "discharging"}


class FactorioNotFound(RuntimeError):
    pass


def find_factorio() -> Path:
    """Path to the factorio binary ($FACTORIO_BIN, or the scripts/setup-factorio.sh location)."""
    env = os.environ.get("FACTORIO_BIN")
    candidate = Path(env) if env else DEFAULT_INSTALL / "bin" / "x64" / "factorio"
    if not candidate.is_file():
        raise FactorioNotFound(
            f"Factorio headless binary not found at {candidate}. "
            "Run scripts/setup-factorio.sh or set FACTORIO_BIN."
        )
    return candidate


@dataclass
class SimSpec:
    """What the harness feeds, drains and how long it runs. Positions are blueprint tiles."""

    inputs: list[dict] = field(default_factory=list)
    outputs: list[dict] = field(default_factory=list)
    warmup_ticks: int = 3600
    measure_ticks: int = 7200
    fuel: str | None = None
    research_all: bool = False

    @classmethod
    def from_dict(cls, sim: dict) -> "SimSpec":
        known = {"input", "output", "warmup_ticks", "measure_ticks", "fuel", "research_all"}
        unknown = set(sim) - known
        if unknown:
            raise ValueError(f"unknown [sim] keys: {sorted(unknown)}")
        return cls(
            inputs=list(sim.get("input", [])),
            outputs=list(sim.get("output", [])),
            warmup_ticks=int(sim.get("warmup_ticks", 3600)),
            measure_ticks=int(sim.get("measure_ticks", 7200)),
            fuel=sim.get("fuel"),
            research_all=bool(sim.get("research_all", False)),
        )

    def to_json(self) -> str:
        return json.dumps(
            {
                "inputs": self.inputs,
                "outputs": self.outputs,
                "warmup_ticks": self.warmup_ticks,
                "measure_ticks": self.measure_ticks,
                "fuel": self.fuel,
                "research_all": self.research_all,
            }
        )


def _lua_long_string(text: str) -> str:
    level = 0
    while f"]{'=' * level}]" in text:
        level += 1
    eq = "=" * level
    return f"[{eq}[{text}]{eq}]"


def run(blueprint_string: str, spec: SimSpec, *, keep_dir: Path | None = None, timeout: int = 600) -> dict:
    """Simulate and return the harness result dict (see control.lua `report`).

    Always returns a dict with at least `ok`; on harness/engine failure `error` and
    `log_tail` explain why.
    """
    binary = find_factorio()
    workdir = Path(keep_dir) if keep_dir else Path(tempfile.mkdtemp(prefix="fbp-sim-"))
    try:
        if workdir.exists():
            shutil.rmtree(workdir)
        scenario = workdir / "write" / "scenarios" / "fbp"
        scenario.mkdir(parents=True)
        (workdir / "mods").mkdir()
        # Vanilla: only the base mod. The DLC mods ship with the headless build, so
        # they must be switched off explicitly.
        mods = [{"name": "base", "enabled": True}] + [
            {"name": n, "enabled": False} for n in ("elevated-rails", "quality", "recycler", "space-age")
        ]
        (workdir / "mods" / "mod-list.json").write_text(json.dumps({"mods": mods}))
        (workdir / "config.ini").write_text(
            f"[path]\nread-data={binary.parents[2] / 'data'}\nwrite-data={workdir / 'write'}\n"
        )
        shutil.copy(HARNESS, scenario / "control.lua")
        (scenario / "fbp_input.lua").write_text(
            "return {\n"
            f"  blueprint = {_lua_long_string(blueprint_string.strip())},\n"
            f"  spec_json = {_lua_long_string(spec.to_json())},\n"
            "}\n"
        )
        total = spec.warmup_ticks + spec.measure_ticks
        cmd = [
            str(binary), "-c", str(workdir / "config.ini"),
            "--mod-directory", str(workdir / "mods"),
            "--test-scenario", "fbp",
            "--test-ticks", str(total + 600),
        ]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
            log = proc.stdout + proc.stderr
        except subprocess.TimeoutExpired as exc:
            return {"ok": False, "error": f"factorio timed out after {timeout}s",
                    "log_tail": str(exc.stdout or "")[-2000:]}
        result_file = workdir / "write" / "script-output" / "fbp-result.json"
        if not result_file.is_file():
            return {"ok": False, "error": "factorio exited without writing a result",
                    "log_tail": "\n".join(log.splitlines()[-25:])}
        return json.loads(result_file.read_text())
    finally:
        if not keep_dir:
            shutil.rmtree(workdir, ignore_errors=True)


@dataclass
class Target:
    item: str
    per_minute: float
    tolerance: float = 0.05


def evaluate(result: dict, targets: list[Target]) -> dict:
    """Turn a raw harness result into a verdict: rates per minute, target checks, stalled machines."""
    if not result.get("ok"):
        return {"passed": False, "errors": [result.get("error", "unknown error")],
                "log_tail": result.get("log_tail"), "problems": result.get("problems") or []}
    minutes = result["measure_ticks"] / 3600
    collected: dict[str, float] = {}
    for out in result.get("outputs") or []:
        for name, count in (out.get("items") or {}).items():
            collected[name] = collected.get(name, 0) + count
    rates = {name: count / minutes for name, count in collected.items()}
    per_min = lambda d: {k: v / minutes for k, v in sorted((d or {}).items())}  # noqa: E731

    errors = list(result.get("problems") or [])
    checks = []
    for t in targets:
        got = rates.get(t.item, 0.0)
        ok = got >= t.per_minute * (1 - t.tolerance)
        checks.append({"item": t.item, "target": t.per_minute, "measured": round(got, 2), "ok": ok})
        if not ok:
            errors.append(f"{t.item}: measured {got:.1f}/min < target {t.per_minute}/min")

    # Utilisation. An entity that never worked is a dead part of the design: an error for
    # machines, a warning for inserters (a spare inserter is harmless but usually a mistake).
    samples = max(result.get("samples", 0), 1)
    groups: dict[tuple, dict] = {}
    dead, warnings = [], []
    for e in result.get("entities") or []:
        status = e.get("status") or {}
        working = sum(v for k, v in status.items() if k in WORKING) / samples
        idle = {k: v for k, v in status.items() if k not in WORKING}
        main = max(idle.items(), key=lambda kv: kv[1])[0] if idle else "working"
        if working == 0:
            x, y = e["position"]
            recipe = f" [{e['recipe']}]" if e.get("recipe") else ""
            text = f"{e['name']}{recipe} @ centre ({x:g}, {y:g}) never worked: {main}"
            dead.append(text)
            (warnings if e["type"] == "inserter" else errors).append(text)
        g = groups.setdefault((e["name"], e.get("recipe"), main), {"count": 0, "working": 0.0})
        g["count"] += 1
        g["working"] += working
    utilisation = [
        {"name": name, "recipe": recipe, "count": g["count"], "working": round(g["working"] / g["count"], 2),
         "idle_reason": main}
        for (name, recipe, main), g in sorted(groups.items(), key=lambda kv: (kv[0][0], str(kv[0][1])))
    ]
    if result.get("electric_networks", 1) > 1:
        errors.append(f"{result['electric_networks']} separate electric networks (poles not wired together)")
    return {
        "passed": not errors,
        "errors": errors,
        "checks": checks,
        "output_per_minute": {k: round(v, 2) for k, v in sorted(rates.items())},
        "input_per_minute": {
            k: round(v / minutes, 2)
            for inp in result.get("inputs") or [] for k, v in (inp.get("items") or {}).items()
        },
        "produced_per_minute": {k: round(v, 2) for k, v in per_min(result.get("produced")).items()},
        "consumed_per_minute": {k: round(v, 2) for k, v in per_min(result.get("consumed")).items()},
        "utilisation": utilisation,
        "warnings": warnings,
    }
