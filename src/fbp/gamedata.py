"""Thin, typed access to the game's prototype data (loaded by draftsman).

Never hard-code recipe times, sizes or speeds elsewhere: read them from here so the
numbers always match the installed game version.
"""

from __future__ import annotations

import math
from functools import lru_cache

from draftsman.data import entities as _entities
from draftsman.data import fluids as _fluids
from draftsman.data import items as _items
from draftsman.data import mods as _mods
from draftsman.data import modules as _modules
from draftsman.data import recipes as _recipes

ENTITIES: dict[str, dict] = _entities.raw
RECIPES: dict[str, dict] = _recipes.raw
ITEMS: dict[str, dict] = _items.raw
FLUIDS: dict[str, dict] = _fluids.raw
MODULES: dict[str, dict] = _modules.raw

BELT_TYPES = {"transport-belt", "underground-belt", "splitter", "loader", "loader-1x1", "linked-belt", "lane-splitter"}
CONTAINER_TYPES = {"container", "logistic-container", "infinity-container", "linked-container", "cargo-wagon"}
CRAFTING_TYPES = {"assembling-machine", "furnace", "rocket-silo"}
FLUID_CARRIER_TYPES = {"pipe", "pipe-to-ground", "storage-tank", "pump", "infinity-pipe", "offshore-pump", "valve"}
# Rails and friends sit on a 2x2 grid with odd collision rules; the layout checks skip them.
RAIL_TYPES = {"straight-rail", "curved-rail-a", "curved-rail-b", "half-diagonal-rail", "rail-signal",
              "rail-chain-signal", "train-stop", "legacy-straight-rail", "legacy-curved-rail",
              "locomotive", "cargo-wagon", "fluid-wagon", "artillery-wagon"}

_SI = {"k": 1e3, "M": 1e6, "G": 1e9, "T": 1e12}


def game_version() -> str:
    return ".".join(str(p) for p in _mods.versions["base"][:3])


def enabled_mods() -> list[str]:
    return sorted(_mods.versions)


def parse_energy(text: str | None) -> float:
    """'150kW' -> 150000.0 (W), '5kJ' -> 5000.0 (J)."""
    if not text:
        return 0.0
    number = text.rstrip("WJ")
    scale = 1.0
    if number and number[-1] in _SI:
        scale, number = _SI[number[-1]], number[:-1]
    return float(number) * scale


def tile_size(name: str, direction: int = 0) -> tuple[int, int]:
    """Footprint in tiles (width, height) for an entity facing `direction` (0-15)."""
    (x1, y1), (x2, y2) = ENTITIES[name]["collision_box"]
    w, h = math.ceil(x2 - x1), math.ceil(y2 - y1)
    return (h, w) if direction in (4, 12) else (w, h)


def recipe_categories(recipe: dict) -> list[str]:
    return recipe.get("categories") or ([recipe["category"]] if recipe.get("category") else ["crafting"])


def recipe_time(recipe: dict) -> float:
    return float(recipe.get("energy_required", 0.5))


def _avg_amount(entry: dict) -> float:
    if "amount" in entry:
        amount = float(entry["amount"])
    else:
        amount = (float(entry["amount_min"]) + float(entry["amount_max"])) / 2
    return amount * float(entry.get("probability", 1))


def recipe_io(recipe: dict) -> tuple[dict[str, float], dict[str, float]]:
    """(ingredients, results) as {name: average amount per craft}."""
    ins: dict[str, float] = {}
    outs: dict[str, float] = {}
    for entry in recipe.get("ingredients") or []:
        ins[entry["name"]] = ins.get(entry["name"], 0) + _avg_amount(entry)
    for entry in recipe.get("results") or []:
        outs[entry["name"]] = outs.get(entry["name"], 0) + _avg_amount(entry)
    return ins, outs


def recipe_fluids(recipe: dict) -> tuple[list[str], list[str]]:
    ins = [e["name"] for e in recipe.get("ingredients") or [] if e.get("type") == "fluid"]
    outs = [e["name"] for e in recipe.get("results") or [] if e.get("type") == "fluid"]
    return ins, outs


def can_craft(machine: str, recipe: str) -> bool:
    cats = set(ENTITIES[machine].get("crafting_categories") or [])
    return bool(cats & set(recipe_categories(RECIPES[recipe])))


@lru_cache(maxsize=None)
def recipes_producing(product: str) -> tuple[str, ...]:
    out = []
    for name, recipe in RECIPES.items():
        if recipe.get("hidden") or "parameters" in recipe_categories(recipe):
            continue
        if any(r["name"] == product for r in recipe.get("results") or []):
            out.append(name)
    return tuple(sorted(out))


def belt_items_per_minute(name: str) -> float:
    """Full belt (both lanes). 8 item slots per tile, speed is tiles/tick."""
    return ENTITIES[name]["speed"] * 8 * 60 * 60
