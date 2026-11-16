"""Static checks for production-line blueprints. Fast pre-flight before `fbp sim`.

Each check yields Issues. `error` = the blueprint will not work as built;
`warning` = suspicious, confirm it is intended.
"""

from __future__ import annotations

from dataclasses import dataclass

from . import gamedata as gd
from .layout import NAMES, VECTORS, Ent, Layout, fluid_ports, inserter_tiles

POLE_COPPER = 5  # wire connector id for copper (power) wires on electric poles


@dataclass
class Issue:
    severity: str  # "error" | "warning"
    code: str
    message: str
    tile: tuple[int, int] | None = None

    def __str__(self) -> str:
        return f"{self.severity.upper():7} [{self.code}] {self.message}"


def _err(code, msg, ent: Ent | None = None):
    return Issue("error", code, msg, ent.tile if ent else None)


def _warn(code, msg, ent: Ent | None = None):
    return Issue("warning", code, msg, ent.tile if ent else None)


def check_names(layout: Layout):
    for e in layout.entities:
        if e.proto is None:
            yield _err("unknown-entity", f"'{e.name}' is not an entity in this game version (base mod only)")
            continue
        if e.recipe is not None:
            if e.recipe not in gd.RECIPES:
                yield _err("unknown-recipe", f"{e.where()}: recipe '{e.recipe}' does not exist", e)
            elif e.type in gd.CRAFTING_TYPES and not gd.can_craft(e.name, e.recipe):
                cats = gd.recipe_categories(gd.RECIPES[e.recipe])
                yield _err("wrong-machine", f"{e.where()}: cannot craft '{e.recipe}' (needs category {cats})", e)
        elif e.type == "assembling-machine" and not e.proto.get("fixed_recipe"):
            yield _err("no-recipe", f"{e.where()}: no recipe set", e)
        for item in e.raw.get("items") or []:
            name = (item.get("id") or {}).get("name")
            if name and name not in gd.ITEMS and name not in gd.MODULES:
                yield _err("unknown-item", f"{e.where()}: requested item '{name}' does not exist", e)
        if e.direction % 4 and e.type not in gd.RAIL_TYPES:
            yield _err("bad-direction", f"{e.where()}: direction {e.direction} is diagonal; "
                       "use 0/4/8/12 (N/E/S/W) - Factorio 2.x has 16 directions", e)


def check_overlap(layout: Layout):
    reported = set()
    for tile, ents in layout.grid.items():
        if len(ents) > 1:
            key = tuple(sorted(e.number for e in ents))
            if key not in reported:
                reported.add(key)
                yield Issue("error", "overlap", "entities overlap at tile "
                            f"({tile[0]}, {tile[1]}): " + " / ".join(e.where() for e in ents), tile)


def check_power(layout: Layout):
    poles = [e for e in layout.entities if e.type == "electric-pole"]
    consumers = [e for e in layout.entities if e.proto and e.type != "electric-pole"
                 and (e.proto.get("energy_source") or {}).get("type") == "electric"]
    if not consumers:
        return
    if not poles:
        yield Issue("warning", "no-poles", f"{len(consumers)} electric entities but no electric poles in the blueprint")
        return
    for c in consumers:
        xs = [t[0] for t in c.tiles]
        ys = [t[1] for t in c.tiles]
        x1, y1, x2, y2 = min(xs), min(ys), max(xs) + 1, max(ys) + 1
        for p in poles:
            d = p.proto["supply_area_distance"]
            if x1 < p.x + d and x2 > p.x - d and y1 < p.y + d and y2 > p.y - d:
                break
        else:
            yield _err("unpowered", f"{c.where()}: outside every pole's supply area", c)
    # pole connectivity through copper wires stored in the blueprint
    parent = {p.number: p.number for p in poles}

    def find(n):
        while parent[n] != n:
            parent[n] = parent[parent[n]]
            n = parent[n]
        return n

    by_number = {p.number: p for p in poles}
    for a, ca, b, cb in layout.wires:
        if ca == POLE_COPPER and cb == POLE_COPPER and a in parent and b in parent:
            pa, pb = by_number[a], by_number[b]
            reach = min(pa.proto["maximum_wire_distance"], pb.proto["maximum_wire_distance"])
            if (pa.x - pb.x) ** 2 + (pa.y - pb.y) ** 2 > reach**2 + 1e-6:
                yield _err("wire-too-long", f"copper wire {pa.where()} <-> {pb.where()} exceeds reach {reach}", pa)
            parent[find(a)] = find(b)
    groups = {find(n) for n in parent}
    if len(groups) > 1:
        yield Issue("error", "poles-disconnected",
                    f"electric poles form {len(groups)} separate networks; blueprints only keep wires that are "
                    "stored in them - call bp.generate_power_connections() (fbp.kit.finalize does) "
                    "and keep poles within wire reach")


_GIVERS = gd.BELT_TYPES | gd.CONTAINER_TYPES | gd.CRAFTING_TYPES | {"lab", "mining-drill", "reactor", "boiler",
                                                                   "cargo-wagon", "roboport"}
_TAKERS = _GIVERS | {"ammo-turret", "artillery-turret", "beacon", "generator", "burner-generator", "locomotive"}


def check_inserters(layout: Layout):
    for e in layout.entities:
        if e.type != "inserter":
            continue
        pick_tile, drop_tile = inserter_tiles(e)
        src, dst = layout.at(pick_tile), layout.at(drop_tile)
        facing = NAMES.get(e.direction, e.direction)
        hint = (f"(direction={facing} means it PICKS UP from the {facing} side "
                "and drops on the opposite side)")
        if src is None:
            yield _warn("inserter-no-source", f"{e.where()}: picks up from empty tile {pick_tile} {hint}", e)
        elif src.type not in _GIVERS and not (src.proto.get("energy_source") or {}).get("type") == "burner":
            yield _err("inserter-bad-source", f"{e.where()}: cannot pick up from {src.where()} {hint}", e)
        if dst is None:
            yield _warn("inserter-no-target", f"{e.where()}: drops onto empty ground at tile {drop_tile} {hint}", e)
        elif dst.type not in _TAKERS and not (dst.proto.get("energy_source") or {}).get("type") == "burner":
            yield _err("inserter-bad-target", f"{e.where()}: cannot drop into {dst.where()} {hint}", e)
        if src is not None and dst is not None and src.type in gd.BELT_TYPES and dst.type in gd.BELT_TYPES:
            continue
        if src is not None and dst is not None and src.type in gd.CRAFTING_TYPES and dst.type in gd.CRAFTING_TYPES \
                and src.recipe and dst.recipe and src.recipe in gd.RECIPES and dst.recipe in gd.RECIPES:
            made = set(gd.recipe_io(gd.RECIPES[src.recipe])[1])
            needed = set(gd.recipe_io(gd.RECIPES[dst.recipe])[0])
            if not made & needed:
                yield _err("inserter-useless", f"{e.where()}: moves products of '{src.recipe}' into a machine "
                           f"crafting '{dst.recipe}', which uses none of them", e)


def _is_underground_output(e: Ent) -> bool:
    return e.type == "underground-belt" and e.raw.get("type") == "output"


def check_belts(layout: Layout):
    for e in layout.entities:
        if e.type not in gd.BELT_TYPES or e.direction not in VECTORS:
            continue
        dx, dy = VECTORS[e.direction]
        if e.type == "underground-belt":
            is_out = _is_underground_output(e)
            # walk towards the partner: forward for an input, backward for an output
            sx, sy = (-dx, -dy) if is_out else (dx, dy)
            tx, ty = e.tile
            partner = None
            for step in range(1, e.proto["max_distance"] + 1):
                other = layout.at((tx + sx * step, ty + sy * step))
                if other and other.name == e.name and other.direction == e.direction:
                    if _is_underground_output(other) != is_out:
                        partner = other
                    break  # the nearest same-kind underground in line decides the pairing
            if partner is None:
                kind = "output" if is_out else "input"
                yield _err("underground-unpaired", f"{e.where()}: underground {kind} facing {NAMES[e.direction]} has no "
                           f"matching {'input' if is_out else 'output'} within {e.proto['max_distance'] - 1} tiles gap "
                           "(same belt tier, same direction, io_type input -> output along the direction of travel)", e)
            if not is_out:
                continue  # an input's items leave through its partner
        for tile in e.tiles:
            ahead = layout.at((tile[0] + dx, tile[1] + dy))
            if ahead is None or ahead is e:
                continue
            if ahead.type in gd.BELT_TYPES and ahead.direction == (e.direction + 8) % 16:
                yield _err("belt-head-on", f"{e.where()} runs head-on into {ahead.where()}", e)
            elif ahead.type == "splitter" and ahead.direction != e.direction:
                yield _err("belt-into-splitter-side", f"{e.where()} feeds the side of {ahead.where()}", e)
            elif ahead.type == "underground-belt" and ahead.direction == e.direction and _is_underground_output(ahead):
                yield _err("belt-into-underground-output", f"{e.where()} feeds the back of underground OUTPUT "
                           f"{ahead.where()}; io_type is probably swapped", e)


def check_fluids(layout: Layout):
    for e in layout.entities:
        if e.type not in gd.CRAFTING_TYPES or not e.recipe or e.recipe not in gd.RECIPES:
            continue
        fl_in, fl_out = gd.recipe_fluids(gd.RECIPES[e.recipe])
        if not fl_in and not fl_out:
            continue
        connected = {"input": 0, "output": 0}
        for port in fluid_ports(e):
            other = layout.at(port["tile"])
            if other is None or other is e:
                continue
            if other.type in gd.FLUID_CARRIER_TYPES or any(p["tile"] in e.tiles for p in fluid_ports(other)):
                if port["kind"] in connected:
                    connected[port["kind"]] += 1
        if len(fl_in) > connected["input"]:
            yield _err("fluid-input-missing", f"{e.where()}: recipe '{e.recipe}' needs {len(fl_in)} fluid input(s) "
                       f"{fl_in} but only {connected['input']} input port(s) touch a pipe. "
                       "Check the machine's direction (ports rotate with it)", e)
        if len(fl_out) > connected["output"]:
            yield _err("fluid-output-missing", f"{e.where()}: recipe '{e.recipe}' produces {len(fl_out)} fluid(s) "
                       f"{fl_out} but only {connected['output']} output port(s) touch a pipe", e)


CHECKS = [check_names, check_overlap, check_power, check_inserters, check_belts, check_fluids]


def validate(layout: Layout) -> list[Issue]:
    issues: list[Issue] = []
    known = Layout([e for e in layout.entities if e.proto], layout.wires, layout.grid, layout.label)
    for check in CHECKS:
        issues.extend(check(layout if check is check_names else known))
    issues.sort(key=lambda i: (i.severity != "error", i.tile or (0, 0)))
    return issues


def has_errors(issues: list[Issue]) -> bool:
    return any(i.severity == "error" for i in issues)
