"""Ore mining: electric mining drills on both sides of one collecting belt. Paste onto an ore patch.

Works for iron, copper, stone and coal alike (every drill mines whatever is under it).
One unit (7 tiles wide, repeated UNITS times along x):

    y=0..2  [drill facing S] pole [drill facing S]   (pole at y=1)
    y=3     collecting belt, travelling east. North drills fill the left lane, south drills the right lane
    y=4..6  [drill facing N] pole [drill facing N]   (pole at y=5)

Small poles sit in the 1-tile gap between the two drills of a unit and power both.
Each drill mines a 5x5 area, so the gap column is mined too (no ore left unreached).
Output: east end of the belt, x = UNITS * PITCH - 1. Mining cannot be measured by `fbp sim`
(the test map has no ore), so the rate here is the game-data figure, not a measurement.
"""

from fbp import kit
from fbp.kit import E, N, S

UNITS = 3
PITCH = 7


def build():
    bp = kit.new("Ore mining", "Electric drills on both sides of one belt; output at the east end. Any ore.")
    kit.belt(bp, (0, 3), E, UNITS * PITCH)
    for i in range(UNITS):
        x = i * PITCH
        for dx in (0, 4):
            kit.machine(bp, "electric-mining-drill", (x + dx, 0), direction=S)
            kit.machine(bp, "electric-mining-drill", (x + dx, 4), direction=N)
        bp.entities.append("small-electric-pole", tile_position=(x + 3, 1))
        bp.entities.append("small-electric-pole", tile_position=(x + 3, 5))
    return kit.finalize(bp)
