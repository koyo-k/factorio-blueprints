"""Small helpers for blueprints/<name>/build.py. They encode the easy-to-get-wrong parts.

Everything takes TILE coordinates: the top-left tile of the entity, x right, y down.
"""

from __future__ import annotations

from draftsman.blueprintable import Blueprint
from draftsman.constants import Direction

N, E, S, W = Direction.NORTH, Direction.EAST, Direction.SOUTH, Direction.WEST
_STEP = {N: (0, -1), E: (1, 0), S: (0, 1), W: (-1, 0)}
_OPPOSITE = {N: S, S: N, E: W, W: E}


def new(label: str, description: str = "") -> Blueprint:
    bp = Blueprint()
    bp.label = label
    if description:
        bp.description = description
    return bp


def belt(bp: Blueprint, start: tuple[int, int], direction: Direction, length: int,
         name: str = "transport-belt") -> tuple[int, int]:
    """Straight run of `length` belts from `start`, travelling in `direction`. Returns the last tile."""
    dx, dy = _STEP[direction]
    x, y = start
    for i in range(length):
        bp.entities.append(name, tile_position=(x + dx * i, y + dy * i), direction=direction)
    return x + dx * (length - 1), y + dy * (length - 1)


def underground(bp: Blueprint, entrance: tuple[int, int], direction: Direction, gap: int,
                name: str = "underground-belt") -> tuple[int, int]:
    """Entrance at `entrance`, exit `gap` empty tiles further along `direction`. Returns the exit tile."""
    dx, dy = _STEP[direction]
    x, y = entrance
    exit_tile = (x + dx * (gap + 1), y + dy * (gap + 1))
    bp.entities.append(name, tile_position=entrance, direction=direction, io_type="input")
    bp.entities.append(name, tile_position=exit_tile, direction=direction, io_type="output")
    return exit_tile


def inserter(bp: Blueprint, tile: tuple[int, int], moves: Direction, name: str = "inserter", **kwargs) -> None:
    """Inserter that MOVES items towards `moves` (takes from the opposite side).

    Factorio's own `direction` field is the side it picks up from, which is the opposite
    of what one usually thinks about; this helper hides that.
    """
    bp.entities.append(name, tile_position=tile, direction=_OPPOSITE[moves], **kwargs)


def machine(bp: Blueprint, name: str, tile: tuple[int, int], recipe: str | None = None,
            direction: Direction = N, modules: dict[str, int] | None = None, **kwargs):
    """Crafting machine with its top-left corner at `tile`. `modules` = {module name: count}."""
    if recipe is not None:
        kwargs["recipe"] = recipe
    bp.entities.append(name, tile_position=tile, direction=direction, **kwargs)
    entity = bp.entities[-1]
    slot = 0
    for module, count in (modules or {}).items():
        entity.request_modules(module, slots=tuple(range(slot, slot + count)))
        slot += count
    return entity


def finalize(bp: Blueprint) -> Blueprint:
    """Call last: stores the copper wires between poles (unwired poles stay disconnected in-game)."""
    bp.generate_power_connections()
    return bp
