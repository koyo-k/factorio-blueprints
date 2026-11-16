"""A normalized, geometry-aware view of a blueprint dict, shared by validate and render."""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from . import gamedata as gd

# direction (0,4,8,12) -> unit vector. North is -y.
VECTORS = {0: (0, -1), 4: (1, 0), 8: (0, 1), 12: (-1, 0)}
NAMES = {0: "north", 4: "east", 8: "south", 12: "west"}


def rotate(vec: tuple[float, float], direction: int) -> tuple[float, float]:
    """Rotate a north-facing prototype vector to `direction` (multiples of 4)."""
    x, y = vec
    for _ in range((direction // 4) % 4):
        x, y = -y, x
    return x, y


@dataclass
class Ent:
    number: int
    name: str
    x: float  # centre, as stored in the blueprint string
    y: float
    direction: int
    raw: dict
    proto: dict | None
    tiles: list[tuple[int, int]] = field(default_factory=list)

    @property
    def type(self) -> str:
        return self.proto["type"] if self.proto else "unknown"

    @property
    def recipe(self) -> str | None:
        return self.raw.get("recipe")

    @property
    def tile(self) -> tuple[int, int]:
        """Top-left tile (what draftsman calls tile_position)."""
        return min(t[0] for t in self.tiles), min(t[1] for t in self.tiles)

    def where(self) -> str:
        tx, ty = self.tile
        return f"{self.name} @ tile ({tx}, {ty})"


@dataclass
class Layout:
    entities: list[Ent]
    wires: list[list[int]]
    grid: dict[tuple[int, int], list[Ent]]
    label: str | None = None

    def at(self, tile: tuple[int, int]) -> Ent | None:
        found = self.grid.get(tile)
        return found[0] if found else None

    def bounds(self) -> tuple[int, int, int, int]:
        xs = [t[0] for t in self.grid]
        ys = [t[1] for t in self.grid]
        return min(xs), min(ys), max(xs), max(ys)


def from_dict(data: dict) -> Layout:
    if "blueprint" not in data:
        kind = next(iter(data), "?")
        raise ValueError(f"expected a single blueprint, got '{kind}'")
    bp = data["blueprint"]
    ents: list[Ent] = []
    grid: dict[tuple[int, int], list[Ent]] = {}
    for raw in bp.get("entities") or []:
        name = raw["name"]
        proto = gd.ENTITIES.get(name)
        direction = int(raw.get("direction", 0))
        ent = Ent(raw["entity_number"], name, raw["position"]["x"], raw["position"]["y"], direction, raw, proto)
        w, h = gd.tile_size(name, direction) if proto else (1, 1)
        x0 = math.floor(ent.x - w / 2 + 1e-6)
        y0 = math.floor(ent.y - h / 2 + 1e-6)
        ent.tiles = [(x0 + dx, y0 + dy) for dy in range(h) for dx in range(w)]
        ents.append(ent)
        if proto and ent.type not in gd.RAIL_TYPES:
            for t in ent.tiles:
                grid.setdefault(t, []).append(ent)
    return Layout(ents, bp.get("wires") or [], grid, bp.get("label"))


def inserter_tiles(ent: Ent) -> tuple[tuple[int, int], tuple[int, int]]:
    """(pickup tile, drop tile) of an inserter, honouring custom vectors if present."""
    pick = ent.raw.get("pickup_position") or rotate(tuple(ent.proto["pickup_position"]), ent.direction)
    drop = ent.raw.get("drop_position") or rotate(tuple(ent.proto["insert_position"]), ent.direction)
    return (
        (math.floor(ent.x + pick[0]), math.floor(ent.y + pick[1])),
        (math.floor(ent.x + drop[0]), math.floor(ent.y + drop[1])),
    )


def fluid_ports(ent: Ent) -> list[dict]:
    """Fluid connection points: [{'kind': input|output|..., 'tile': outside tile it must touch}]."""
    proto = ent.proto or {}
    boxes = list(proto.get("fluid_boxes") or [])
    for key in ("fluid_box", "input_fluid_box", "output_fluid_box"):
        if isinstance(proto.get(key), dict):
            boxes.append(proto[key])
    ports = []
    for box in boxes:
        if not isinstance(box, dict):
            continue
        for conn in box.get("pipe_connections") or []:
            if "position" not in conn or conn.get("connection_type") == "underground":
                continue
            lx, ly = conn["position"]
            ldir = int(conn.get("direction", 0))
            if ent.raw.get("mirror"):  # horizontal flip in the entity's own frame, before rotation
                lx, ldir = -lx, (16 - ldir) % 16
            px, py = rotate((lx, ly), ent.direction)
            dx, dy = VECTORS.get((ldir + ent.direction) % 16, (0, 0))
            ports.append({
                "kind": box.get("production_type") or conn.get("flow_direction") or "input-output",
                "tile": (math.floor(ent.x + px + dx), math.floor(ent.y + py + dy)),
            })
    return ports
