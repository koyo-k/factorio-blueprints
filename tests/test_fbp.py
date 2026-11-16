import json

import pytest
from draftsman.blueprintable import Blueprint

from fbp import codec, gamedata as gd, kit, layout, project, rates, render, validate
from fbp.kit import E, N, S, W
from fbp.sim import runner


def issues_of(bp: Blueprint) -> set[str]:
    return {i.code for i in validate.validate(layout.from_dict(codec.decode(bp.to_string())))}


def small_line() -> Blueprint:
    """belt -> inserter -> gear assembler -> inserter -> belt, powered."""
    bp = kit.new("test")
    kit.belt(bp, (0, 0), E, 3)
    kit.inserter(bp, (1, 1), moves=S)
    kit.machine(bp, "assembling-machine-2", (0, 2), "iron-gear-wheel")
    kit.inserter(bp, (1, 5), moves=S)
    kit.belt(bp, (0, 6), E, 3)
    bp.entities.append("medium-electric-pole", tile_position=(3, 3))
    return kit.finalize(bp)


def test_vanilla_data_only():
    assert gd.enabled_mods() == ["base"], "run scripts/setup.sh (DLC data must be disabled)"
    assert "foundry" not in gd.ENTITIES


def test_codec_roundtrip():
    data = {"blueprint": {"item": "blueprint", "entities": [], "label": "あ"}}
    assert codec.decode(codec.encode(data)) == data
    with pytest.raises(ValueError):
        codec.decode("not a blueprint")


def test_clean_line_has_no_issues():
    assert issues_of(small_line()) == set()


def test_inserter_direction_is_pickup_side():
    bp = kit.new("t")
    kit.belt(bp, (0, 0), E, 1)
    kit.inserter(bp, (0, 1), moves=S)
    kit.machine(bp, "assembling-machine-2", (0, 2), "iron-gear-wheel")
    lay = layout.from_dict(codec.decode(bp.to_string()))
    ins = next(e for e in lay.entities if e.type == "inserter")
    assert ins.direction == 0  # NORTH: picks up from the north
    assert layout.inserter_tiles(ins) == ((0, 0), (0, 2))


def test_detects_reversed_and_dangling_inserters():
    bp = small_line()
    bp.entities.append("inserter", tile_position=(6, 6))
    assert {"inserter-no-source", "inserter-no-target"} <= issues_of(bp)
    bp = kit.new("t")
    bp.entities.append("medium-electric-pole", tile_position=(0, 0))
    kit.inserter(bp, (0, 1), moves=S)
    kit.machine(bp, "assembling-machine-2", (0, 2), "iron-gear-wheel")
    assert "inserter-bad-source" in issues_of(bp)


def test_detects_overlap_power_recipe_problems():
    bp = small_line()
    bp.entities.append("transport-belt", tile_position=(1, 1))
    assert "overlap" in issues_of(bp)

    bp = small_line()
    kit.machine(bp, "assembling-machine-2", (20, 20), "iron-gear-wheel")
    assert "unpowered" in issues_of(bp)

    bp = kit.new("t")
    bp.entities.append("medium-electric-pole", tile_position=(0, 0))
    bp.entities.append("medium-electric-pole", tile_position=(4, 0))
    kit.machine(bp, "assembling-machine-2", (0, 1))
    kit.machine(bp, "assembling-machine-2", (4, 1), "plastic-bar")
    found = issues_of(bp)  # no finalize(): poles are not wired
    assert {"poles-disconnected", "no-recipe", "wrong-machine"} <= found


def test_detects_belt_problems():
    bp = kit.new("t")
    kit.belt(bp, (0, 0), E, 2)
    kit.belt(bp, (3, 0), W, 2)
    assert "belt-head-on" in issues_of(bp)

    bp = kit.new("t")
    kit.underground(bp, (0, 0), E, gap=4)
    assert issues_of(bp) == set()
    bp = kit.new("t")
    kit.underground(bp, (0, 0), E, gap=5)  # one too far for the basic underground
    assert "underground-unpaired" in issues_of(bp)
    bp = kit.new("t")
    bp.entities.append("underground-belt", tile_position=(0, 0), direction=E, io_type="output")
    bp.entities.append("underground-belt", tile_position=(3, 0), direction=E, io_type="input")
    assert "underground-unpaired" in issues_of(bp)


def test_detects_missing_fluid_connection():
    bp = kit.new("t")
    kit.machine(bp, "chemical-plant", (0, 0), "plastic-bar")
    assert "fluid-input-missing" in issues_of(bp)
    bp.entities.append("pipe", tile_position=(0, -1))  # north side = input ports when facing north
    assert "fluid-input-missing" not in issues_of(bp)
    bp = kit.new("t")
    kit.machine(bp, "chemical-plant", (0, 0), "plastic-bar", direction=S)
    bp.entities.append("pipe", tile_position=(0, -1))  # rotated: inputs are now on the south side
    assert "fluid-input-missing" in issues_of(bp)


def test_rates_follow_game_data():
    recipe = gd.RECIPES["iron-gear-wheel"]
    per_machine = gd.ENTITIES["assembling-machine-2"]["crafting_speed"] / gd.recipe_time(recipe) * 60
    plan = rates.plan("iron-gear-wheel", per_machine * 2, stop_at={"iron-plate"})
    assert plan.steps[0].machines == pytest.approx(2)
    assert plan.raw == {"iron-plate": pytest.approx(per_machine * 4)}
    assert "iron-plate" in rates.format_plan(plan)
    with pytest.raises(ValueError):
        rates.plan("no-such-item", 1)


def test_render_shows_item_flow():
    art = render.ascii_art(layout.from_dict(codec.decode(small_line().to_string())))
    assert "→→→" in art and "▼" in art and "iron-gear-wheel" in art


@pytest.mark.parametrize("name", ["green-circuits", "red-science", "mining-ore", "smelting-column"])
def test_samples_build_clean_and_match_committed_output(name):
    built = project.build(name, write=False)
    assert not built.issues
    assert (built.directory / "blueprint.txt").read_text().strip() == built.string, "run `fbp build` and commit"


def have_factorio() -> bool:
    try:
        runner.find_factorio()
        return True
    except runner.FactorioNotFound:
        return False


needs_factorio = pytest.mark.skipif(not have_factorio(), reason="headless Factorio not installed")
BELT_IO = dict(
    inputs=[{"kind": "belt", "position": [0, 0], "item": "iron-plate"}],
    outputs=[{"kind": "belt", "position": [2, 6]}],
    warmup_ticks=600, measure_ticks=3600,
)


@needs_factorio
def test_sim_measures_real_production():
    result = runner.run(small_line().to_string(), runner.SimSpec(**BELT_IO))
    # one basic inserter feeds ~55 plates/min, so ~27 gears/min, far below the recipe's 90/min
    verdict = runner.evaluate(result, [runner.Target("iron-gear-wheel", 25)])
    assert verdict["passed"], json.dumps(verdict, indent=1)
    assert verdict["consumed_per_minute"]["iron-plate"] == pytest.approx(2 * verdict["output_per_minute"]["iron-gear-wheel"], rel=0.1)


@needs_factorio
def test_sim_catches_a_reversed_inserter():
    bp = kit.new("t")
    kit.belt(bp, (0, 0), E, 3)
    kit.inserter(bp, (1, 1), moves=N)  # wrong way: pulls from the machine onto the input belt
    kit.machine(bp, "assembling-machine-2", (0, 2), "iron-gear-wheel")
    kit.inserter(bp, (1, 5), moves=S)
    kit.belt(bp, (0, 6), E, 3)
    bp.entities.append("medium-electric-pole", tile_position=(3, 3))
    result = runner.run(kit.finalize(bp).to_string(), runner.SimSpec(**BELT_IO))
    verdict = runner.evaluate(result, [runner.Target("iron-gear-wheel", 30)])
    assert not verdict["passed"]
    assert any("never worked" in e and "iron-gear-wheel" in e for e in verdict["errors"])


@needs_factorio
def test_sim_reports_bad_spec_position():
    spec = runner.SimSpec(inputs=[{"kind": "belt", "position": [50, 50], "item": "iron-plate"}])
    verdict = runner.evaluate(runner.run(small_line().to_string(), spec), [])
    assert not verdict["passed"] and "no belt entity" in verdict["errors"][0]
