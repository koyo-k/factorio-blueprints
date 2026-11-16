"""Electronic circuits by direct insertion: copper-cable assembler -> circuit assembler.

One unit (7 tiles wide, repeated UNITS times along x):

    y=0  input belt, travelling east. left lane (north) iron-plate, right lane (south) copper-plate
    y=1  inserters belt -> machines, one medium pole
    y=2..4  [copper-cable] -> fast inserter -> [electronic-circuit]
    y=5  inserter circuits -> output belt, one medium pole
    y=6  output belt, travelling east

The cable -> circuit hand-off is the bottleneck (see spec.toml for the measured rate),
so the machine count is set by inserter throughput, not by the 3:2 recipe ratio.
"""

from fbp import kit
from fbp.kit import E, S

UNITS = 4
PITCH = 7


def build():
    bp = kit.new("Green circuits", "Direct-insertion electronic circuits. In: iron (left lane) + copper (right lane).")
    width = UNITS * PITCH
    kit.belt(bp, (0, 0), E, width)
    kit.belt(bp, (0, 6), E, width)
    for i in range(UNITS):
        x = i * PITCH
        kit.machine(bp, "assembling-machine-2", (x, 2), "copper-cable")
        kit.machine(bp, "assembling-machine-2", (x + 4, 2), "electronic-circuit")
        kit.inserter(bp, (x + 1, 1), moves=S)                           # copper plate -> cable machine
        kit.inserter(bp, (x + 5, 1), moves=S)                           # iron plate -> circuit machine
        kit.inserter(bp, (x + 3, 3), moves=E, name="fast-inserter")     # cable -> circuit machine
        kit.inserter(bp, (x + 5, 5), moves=S)                           # circuits -> output belt
        bp.entities.append("medium-electric-pole", tile_position=(x + 3, 1))
        bp.entities.append("medium-electric-pole", tile_position=(x + 3, 5))
    return kit.finalize(bp)
