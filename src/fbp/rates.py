"""Ratio calculator: how many machines and how much input a target rate needs.

All numbers come from the game's prototype data. Beacons are not modelled.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from . import gamedata as gd

DEFAULT_MACHINES = {
    "crafting": "assembling-machine-2",
    "advanced-crafting": "assembling-machine-2",
    "crafting-with-fluid": "assembling-machine-2",
    "smelting": "electric-furnace",
    "chemistry": "chemical-plant",
    "oil-processing": "oil-refinery",
    "centrifuging": "centrifuge",
    "rocket-building": "rocket-silo",
}


@dataclass
class Step:
    recipe: str
    machine: str
    crafts_per_minute: float
    machines: float
    speed: float          # effective crafting speed incl. modules
    productivity: float   # bonus, e.g. 0.2
    power_w: float        # for the exact (fractional) machine count
    inputs: dict[str, float]
    outputs: dict[str, float]


@dataclass
class Plan:
    target: str
    per_minute: float
    steps: list[Step] = field(default_factory=list)
    raw: dict[str, float] = field(default_factory=dict)        # per minute, to be supplied
    byproducts: dict[str, float] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)


def pick_machine(recipe: dict, overrides: dict[str, str]) -> str:
    for cat in gd.recipe_categories(recipe):
        name = overrides.get(cat) or DEFAULT_MACHINES.get(cat)
        if name:
            return name
    raise ValueError(f"no machine known for recipe categories {gd.recipe_categories(recipe)}")


def machine_effects(machine: str, recipe: dict, modules: dict[str, int]) -> tuple[float, float, float]:
    """(speed multiplier, productivity bonus, consumption multiplier) from modules in one machine."""
    proto = gd.ENTITIES[machine]
    slots = int(proto.get("module_slots") or 0)
    allowed = set(proto.get("allowed_effects") or [])
    speed = prod = cons = 0.0
    used = 0
    for name, count in modules.items():
        effect = gd.MODULES[name].get("effect") or {}
        if "productivity" in effect and effect["productivity"] > 0 and not recipe.get("allow_productivity"):
            continue
        if any(k not in allowed for k, v in effect.items() if k in ("productivity", "quality") and v > 0):
            continue
        n = min(count, slots - used)
        used += n
        speed += effect.get("speed", 0) * n
        prod += effect.get("productivity", 0) * n
        cons += effect.get("consumption", 0) * n
    return max(1 + speed, 0.2), max(prod, 0.0), max(1 + cons, 0.2)


def plan(target: str, per_minute: float, *, machines: dict[str, str] | None = None,
         modules: dict[str, int] | None = None, stop_at: set[str] | None = None,
         recipes: dict[str, str] | None = None) -> Plan:
    """Expand `target` down to raw inputs.

    machines: {recipe category: machine name} overrides. modules: {module: count} put in every
    machine that accepts them. stop_at: items to treat as supplied from outside.
    recipes: {item: recipe name} to choose between alternatives (oil products etc.).
    """
    machines, modules, stop_at, recipes = machines or {}, modules or {}, stop_at or set(), recipes or {}
    if target not in gd.ITEMS and target not in gd.FLUIDS and target not in gd.MODULES and not gd.recipes_producing(target):
        raise ValueError(f"unknown item or fluid: '{target}'")
    result = Plan(target, per_minute)
    demand: dict[str, float] = {target: per_minute}
    crafts: dict[str, float] = {}
    order: list[str] = []
    visiting: list[str] = []

    def choose(item: str) -> str | None:
        if item in recipes:
            return recipes[item]
        options = gd.recipes_producing(item)
        if item in options:
            return item
        if len(options) == 1:
            return options[0]
        if options:
            result.notes.append(f"{item}: several recipes {list(options)}; treated as an input "
                                f"(choose one with --recipe {item}=<recipe>)")
        return None

    def need(item: str, amount: float) -> None:
        if item in stop_at and item != target:
            result.raw[item] = result.raw.get(item, 0) + amount
            return
        name = choose(item)
        if name is None or item in visiting:
            result.raw[item] = result.raw.get(item, 0) + amount
            return
        recipe = gd.RECIPES[name]
        machine = pick_machine(recipe, machines)
        _, prod, _ = machine_effects(machine, recipe, modules)
        ins, outs = gd.recipe_io(recipe)
        n = amount / (outs[item] * (1 + prod))
        crafts[name] = crafts.get(name, 0) + n
        if name not in order:
            order.append(name)
        visiting.append(item)
        for ing, qty in ins.items():
            need(ing, qty * n)
        visiting.pop()

    need(target, per_minute)
    for name in order:
        recipe = gd.RECIPES[name]
        machine = pick_machine(recipe, machines)
        speed_mult, prod, cons = machine_effects(machine, recipe, modules)
        speed = gd.ENTITIES[machine]["crafting_speed"] * speed_mult
        n = crafts[name]
        count = n * gd.recipe_time(recipe) / speed / 60
        ins, outs = gd.recipe_io(recipe)
        step = Step(name, machine, n, count, speed, prod,
                    gd.parse_energy(gd.ENTITIES[machine].get("energy_usage")) * cons * count,
                    {k: v * n for k, v in ins.items()}, {k: v * n * (1 + prod) for k, v in outs.items()})
        result.steps.append(step)
        for product, qty in step.outputs.items():
            if gd.recipes_producing(product) and (recipes.get(product) or product) != name and \
                    not (product == target) and choose(product) != name:
                result.byproducts[product] = result.byproducts.get(product, 0) + qty
    return result


def format_plan(p: Plan, belt: str = "transport-belt") -> str:
    belt_cap = gd.belt_items_per_minute(belt)
    lines = [f"target: {p.per_minute:g} {p.target}/min   (game {gd.game_version()}, base mod only)", ""]
    lines.append(f"{'recipe':28} {'machine':22} {'count':>7} {'build':>5}  {'speed':>5} {'prod':>5}  per minute")
    for s in p.steps:
        flows = ", ".join(f"{v:g} {k}" for k, v in _round(s.inputs).items()) + "  ->  " + \
            ", ".join(f"{v:g} {k}" for k, v in _round(s.outputs).items())
        lines.append(f"{s.recipe:28} {s.machine:22} {s.machines:7.2f} {math.ceil(s.machines - 1e-9):5d}  "
                     f"{s.speed:5.2f} {s.productivity:5.0%}  {flows}")
    lines.append("")
    lines.append("inputs to supply (per minute):")
    for name, qty in sorted(p.raw.items()):
        if name in gd.FLUIDS:
            lines.append(f"  {qty:10.1f} {name}  (fluid)")
        else:
            lines.append(f"  {qty:10.1f} {name}  = {qty / belt_cap:.2f} {belt} ({qty / (belt_cap / 2):.2f} lanes)")
    if p.byproducts:
        lines.append("byproducts (per minute): " + ", ".join(f"{v:g} {k}" for k, v in _round(p.byproducts).items()))
    total_w = sum(s.power_w for s in p.steps)
    lines.append(f"electric power (machines only, exact count): {total_w / 1000:.0f} kW")
    lines.append(f"{belt}: {belt_cap:g} items/min full, {belt_cap / 2:g} per lane")
    for note in dict.fromkeys(p.notes):
        lines.append("note: " + note)
    return "\n".join(lines)


def _round(d: dict[str, float]) -> dict[str, float]:
    return {k: round(v, 2) for k, v in d.items()}
