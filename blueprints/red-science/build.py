"""Automation science packs: one gear assembler feeds a science assembler on each side.

One unit (12 tiles wide, repeated UNITS times along x):

    y=0  input belt, travelling east. left lane (north) iron-plate, right lane (south) copper-plate
    y=1  inserters belt -> machines, medium poles
    y=2..4  [science] <- inserter <- [iron-gear-wheel] -> inserter -> [science]
    y=5  inserters science -> output belt, medium poles
    y=6  output belt, travelling east
"""

from fbp import kit
from fbp.kit import E, S, W

UNITS = 2
PITCH = 12


def build():
    bp = kit.new("Red science", "Automation science packs. In: iron (left lane) + copper (right lane).")
    width = UNITS * PITCH - 1
    kit.belt(bp, (0, 0), E, width)
    kit.belt(bp, (0, 6), E, width)
    for i in range(UNITS):
        x = i * PITCH
        kit.machine(bp, "assembling-machine-2", (x, 2), "automation-science-pack")
        kit.machine(bp, "assembling-machine-2", (x + 4, 2), "iron-gear-wheel")
        kit.machine(bp, "assembling-machine-2", (x + 8, 2), "automation-science-pack")
        kit.inserter(bp, (x + 1, 1), moves=S)   # copper plate -> science
        kit.inserter(bp, (x + 5, 1), moves=S)   # iron plate -> gears
        kit.inserter(bp, (x + 9, 1), moves=S)   # copper plate -> science
        kit.inserter(bp, (x + 3, 3), moves=W)   # gears -> left science
        kit.inserter(bp, (x + 7, 3), moves=E)   # gears -> right science
        kit.inserter(bp, (x + 1, 5), moves=S)   # science -> output belt
        kit.inserter(bp, (x + 9, 5), moves=S)
        for px in (x + 3, x + 7):
            bp.entities.append("medium-electric-pole", tile_position=(px, 1))
            bp.entities.append("medium-electric-pole", tile_position=(px, 5))
    return kit.finalize(bp)
