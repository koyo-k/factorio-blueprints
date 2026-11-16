"""Smelting column: stone furnaces fed from an ore belt and a coal belt (fuel arrives by belt).

Works for iron ore, copper ore and stone (bricks): furnaces pick the recipe from what they get.
One unit (2 tiles wide, repeated UNITS times along x):

    y=0  coal belt, travelling east (from a `mining-ore` on a coal patch)
    y=1  ore belt, travelling east (from a `mining-ore` on an ore patch; both lanes may carry ore)
    y=2  inserter ore -> furnace (x), long-handed inserter coal -> furnace (x+1, reaches over the ore belt)
    y=3..4  [stone furnace]
    y=5  inserter plates -> output belt (x); medium pole at x+1 every 3rd unit
    y=6  output belt, travelling east

Inputs: west ends of both belts (x = 0). Output: east end of the plate belt.
"""

from fbp import kit
from fbp.kit import E, S

UNITS = 24
PITCH = 2


def build():
    bp = kit.new("Smelting column", "Stone furnaces. In: coal belt (y=0) + ore belt (y=1). Out: plate belt (y=6).")
    width = UNITS * PITCH
    kit.belt(bp, (0, 0), E, width)
    kit.belt(bp, (0, 1), E, width)
    kit.belt(bp, (0, 6), E, width)
    for i in range(UNITS):
        x = i * PITCH
        bp.entities.append("stone-furnace", tile_position=(x, 3))
        kit.inserter(bp, (x, 2), moves=S)                                   # ore -> furnace
        kit.inserter(bp, (x + 1, 2), moves=S, name="long-handed-inserter")  # coal -> furnace
        kit.inserter(bp, (x, 5), moves=S)                                   # plates -> output belt
        if i % 3 == 1:
            bp.entities.append("medium-electric-pole", tile_position=(x + 1, 5))
    return kit.finalize(bp)
