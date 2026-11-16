"""fbp - Factorio blueprint toolkit. Run `fbp --help`."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import codec, gamedata as gd, layout, project, rates, render, validate
from .sim import runner


def _print_issues(issues: list[validate.Issue]) -> None:
    errors = sum(i.severity == "error" for i in issues)
    for issue in issues:
        print(issue)
    print(f"validate: {errors} error(s), {len(issues) - errors} warning(s)")


def cmd_decode(args) -> int:
    print(json.dumps(codec.decode(project.load_string(args.blueprint)), indent=2))
    return 0


def cmd_encode(args) -> int:
    text = sys.stdin.read() if args.json == "-" else Path(args.json).read_text()
    print(codec.encode(json.loads(text)))
    return 0


def cmd_validate(args) -> int:
    lay = layout.from_dict(codec.decode(project.load_string(args.blueprint)))
    issues = validate.validate(lay)
    _print_issues(issues)
    return 1 if validate.has_errors(issues) else 0


def cmd_render(args) -> int:
    lay = layout.from_dict(codec.decode(project.load_string(args.blueprint)))
    print(render.ascii_art(lay), end="")
    if args.png:
        render.png(lay, Path(args.png))
        print(f"wrote {args.png}")
    return 0


def cmd_build(args) -> int:
    built = project.build(args.name)
    print(render.ascii_art(built.layout))
    _print_issues(built.issues)
    print(f"wrote {built.directory}/blueprint.txt, preview.txt, preview.png")
    return 1 if validate.has_errors(built.issues) else 0


def _print_sim(verdict: dict) -> None:
    if verdict.get("log_tail"):
        print("--- factorio log tail ---")
        print(verdict["log_tail"])
    for check in verdict.get("checks", []):
        mark = "OK  " if check["ok"] else "FAIL"
        print(f"{mark} {check['item']}: measured {check['measured']}/min, target {check['target']}/min")
    for key, title in (("output_per_minute", "collected at outputs"), ("input_per_minute", "fed at inputs"),
                       ("produced_per_minute", "produced by machines"), ("consumed_per_minute", "consumed by machines")):
        if verdict.get(key):
            print(f"{title} (per minute): " + ", ".join(f"{v:g} {k}" for k, v in verdict[key].items()))
    if verdict.get("utilisation"):
        print("utilisation (share of time working; idle reason when not):")
        for u in verdict["utilisation"]:
            recipe = f" [{u['recipe']}]" if u.get("recipe") else ""
            print(f"  {u['count']:3d} x {u['name']}{recipe}: {u['working']:.0%} working, else {u['idle_reason']}")
    for warning in verdict.get("warnings", []):
        print("WARNING " + warning)
    for error in verdict.get("errors", []):
        print("ERROR  " + error)
    print("sim: " + ("PASSED" if verdict["passed"] else "FAILED"))


def cmd_sim(args) -> int:
    built = project.build(args.name)
    _print_issues(built.issues)
    if validate.has_errors(built.issues) and not args.force:
        print("sim: skipped because validate found errors (fix them, or pass --force)")
        return 1
    targets, spec = project.load_spec(built.directory)
    try:
        result = runner.run(built.string, spec, keep_dir=Path(args.keep) if args.keep else None)
    except runner.FactorioNotFound as exc:
        print(f"sim: NOT RUN - {exc}")
        return 2
    verdict = runner.evaluate(result, targets)
    if args.json:
        print(json.dumps({"verdict": verdict, "raw": result}, indent=2))
    else:
        _print_sim(verdict)
    return 0 if verdict["passed"] else 1


def _pairs(values: list[str] | None, cast=str) -> dict:
    out = {}
    for value in values or []:
        key, _, val = value.partition("=")
        if not val:
            raise SystemExit(f"expected KEY=VALUE, got '{value}'")
        out[key] = cast(val)
    return out


def cmd_rates(args) -> int:
    plan = rates.plan(args.item, args.per_minute, machines=_pairs(args.machine), modules=_pairs(args.module, int),
                      stop_at=set(args.stop_at or []), recipes=_pairs(args.recipe))
    print(rates.format_plan(plan, args.belt))
    return 0


def cmd_recipe(args) -> int:
    names = [args.name] if args.name in gd.RECIPES else list(gd.recipes_producing(args.name))
    if not names:
        print(f"no recipe named or producing '{args.name}'. Try: fbp search {args.name}")
        return 1
    for name in names:
        recipe = gd.RECIPES[name]
        ins, outs = gd.recipe_io(recipe)
        cats = gd.recipe_categories(recipe)
        machines = sorted(n for n, e in gd.ENTITIES.items() if set(e.get("crafting_categories") or []) & set(cats))
        print(f"{name}: time {gd.recipe_time(recipe):g}s, categories {cats}, "
              f"productivity {'allowed' if recipe.get('allow_productivity') else 'not allowed'}")
        print("  in:  " + ", ".join(f"{v:g} {k}" for k, v in ins.items()))
        print("  out: " + ", ".join(f"{v:g} {k}" for k, v in outs.items()))
        print("  made in: " + ", ".join(machines))
    return 0


_ENTITY_KEYS = ["type", "crafting_speed", "crafting_categories", "module_slots", "allowed_effects", "energy_usage",
                "speed", "max_distance", "supply_area_distance", "maximum_wire_distance", "pickup_position",
                "insert_position", "rotation_speed", "extension_speed", "fixed_recipe", "mining_speed",
                "resource_searching_radius", "inventory_size", "researching_speed", "distribution_effectivity"]


def cmd_entity(args) -> int:
    proto = gd.ENTITIES.get(args.name)
    if proto is None:
        print(f"no entity '{args.name}'. Try: fbp search {args.name}")
        return 1
    w, h = gd.tile_size(args.name)
    print(f"{args.name}: {w}x{h} tiles")
    for key in _ENTITY_KEYS:
        if proto.get(key) is not None:
            print(f"  {key}: {proto[key]}")
    source = proto.get("energy_source") or {}
    if source.get("type"):
        print(f"  energy_source: {source['type']}")
    if proto["type"] in gd.BELT_TYPES and proto.get("speed"):
        print(f"  throughput: {gd.belt_items_per_minute(args.name):g} items/min (both lanes)")
    ports = layout.fluid_ports(layout.Ent(0, args.name, w / 2, h / 2, 0, {}, proto))
    for port in ports:
        print(f"  fluid port ({port['kind']}): touches tile {port['tile']} when the machine's top-left is (0, 0), facing north")
    return 0


def cmd_search(args) -> int:
    needle = args.text.lower()
    for title, table in (("entities", gd.ENTITIES), ("recipes", gd.RECIPES), ("items", gd.ITEMS), ("fluids", gd.FLUIDS)):
        hits = sorted(n for n in table if needle in n.lower())
        if hits:
            print(f"{title}: " + ", ".join(hits))
    return 0


def cmd_info(args) -> int:
    print(f"game data: Factorio {gd.game_version()}, mods: {', '.join(gd.enabled_mods())}")
    try:
        print(f"headless binary: {runner.find_factorio()}")
    except runner.FactorioNotFound as exc:
        print(f"headless binary: MISSING - {exc}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="fbp", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    bp_help = "project name under blueprints/, a file with a blueprint string or JSON, or '-' for stdin"

    p = sub.add_parser("build", help="run blueprints/<name>/build.py, validate, write blueprint.txt + previews")
    p.add_argument("name"); p.set_defaults(func=cmd_build)
    p = sub.add_parser("sim", help="build, then run in headless Factorio and compare with spec.toml targets")
    p.add_argument("name"); p.add_argument("--json", action="store_true", help="full result as JSON")
    p.add_argument("--force", action="store_true", help="simulate even if validate reports errors")
    p.add_argument("--keep", metavar="DIR", help="keep the Factorio run directory (logs) here")
    p.set_defaults(func=cmd_sim)
    p = sub.add_parser("validate", help="static checks only"); p.add_argument("blueprint", help=bp_help)
    p.set_defaults(func=cmd_validate)
    p = sub.add_parser("render", help="print the ASCII view"); p.add_argument("blueprint", help=bp_help)
    p.add_argument("--png", metavar="FILE"); p.set_defaults(func=cmd_render)
    p = sub.add_parser("decode", help="blueprint string -> JSON"); p.add_argument("blueprint", help=bp_help)
    p.set_defaults(func=cmd_decode)
    p = sub.add_parser("encode", help="JSON -> blueprint string"); p.add_argument("json", help="file or '-'")
    p.set_defaults(func=cmd_encode)
    p = sub.add_parser("rates", help="machines and inputs needed for a target rate")
    p.add_argument("item"); p.add_argument("per_minute", type=float)
    p.add_argument("--machine", action="append", metavar="CATEGORY=MACHINE", help="e.g. crafting=assembling-machine-3")
    p.add_argument("--module", action="append", metavar="MODULE=COUNT", help="per machine, e.g. productivity-module=2")
    p.add_argument("--stop-at", action="append", metavar="ITEM", help="treat ITEM as supplied (repeatable)")
    p.add_argument("--recipe", action="append", metavar="ITEM=RECIPE", help="pick a recipe for ITEM")
    p.add_argument("--belt", default="transport-belt"); p.set_defaults(func=cmd_rates)
    p = sub.add_parser("recipe", help="show recipe data (by recipe or product name)"); p.add_argument("name")
    p.set_defaults(func=cmd_recipe)
    p = sub.add_parser("entity", help="show entity data (size, speed, ports...)"); p.add_argument("name")
    p.set_defaults(func=cmd_entity)
    p = sub.add_parser("search", help="find entity/recipe/item names containing TEXT"); p.add_argument("text")
    p.set_defaults(func=cmd_search)
    p = sub.add_parser("info", help="show game data version and headless binary status"); p.set_defaults(func=cmd_info)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (FileNotFoundError, ValueError, AttributeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
