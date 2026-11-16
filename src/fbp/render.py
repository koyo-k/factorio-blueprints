"""Draw a blueprint as text (for the model to read) and as a simple PNG (for people)."""

from __future__ import annotations

from pathlib import Path

from . import gamedata as gd
from .layout import VECTORS, Ent, Layout, inserter_tiles

BELT = {0: "↑", 4: "→", 8: "↓", 12: "←"}
UG_IN = {0: "⇑", 4: "⇒", 8: "⇓", 12: "⇐"}   # underground entrance (dives here)
UG_OUT = {0: "⇡", 4: "⇢", 8: "⇣", 12: "⇠"}  # underground exit (surfaces here)
SPLIT = {0: "⇈", 4: "⇉", 8: "⇊", 12: "⇇"}
INS = {0: "▲", 4: "▶", 8: "▼", 12: "◀"}      # points the way ITEMS MOVE
INS_LONG = {0: "△", 4: "▷", 8: "▽", 12: "◁"}
FIXED = {"electric-pole": "+", "pipe": "=", "pipe-to-ground": "#", "container": "c",
         "logistic-container": "c", "beacon": "*", "lamp": "o"}
LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZabdefghijklmnpqrstuvwxyz"


def _move_direction(e: Ent) -> int:
    """Direction items travel through an inserter (opposite of its `direction`)."""
    pick, drop = inserter_tiles(e)
    dx, dy = drop[0] - pick[0], drop[1] - pick[1]
    if abs(dx) >= abs(dy):
        return 4 if dx > 0 else 12
    return 8 if dy > 0 else 0


def glyphs(layout: Layout) -> tuple[dict[int, str], list[str]]:
    """Per-entity glyph and the legend lines."""
    out: dict[int, str] = {}
    groups: dict[tuple, str] = {}
    counts: dict[tuple, int] = {}
    used: dict[str, str] = {}
    for e in layout.entities:
        d = e.direction if e.direction in BELT else 0
        if e.type == "transport-belt":
            g, label = BELT[d], "belt (arrow = travel direction)"
        elif e.type == "underground-belt":
            is_out = e.raw.get("type") == "output"
            g = (UG_OUT if is_out else UG_IN)[d]
            label = "underground belt exit" if is_out else "underground belt entrance"
        elif e.type == "splitter":
            g, label = SPLIT[d], "splitter"
        elif e.type == "inserter":
            long = abs(e.proto["pickup_position"][1]) > 1.5
            g = (INS_LONG if long else INS)[_move_direction(e)]
            label = "inserter, arrow = the way items move (" + ("reach 2" if long else "reach 1") + ")"
        elif e.type in FIXED:
            g, label = FIXED[e.type], e.type
        else:
            key = (e.name, e.recipe)
            if key not in groups:
                groups[key] = LETTERS[len(groups) % len(LETTERS)]
            counts[key] = counts.get(key, 0) + 1
            out[e.number] = groups[key]
            continue
        out[e.number] = g
        used.setdefault(g, label)
    legend = [f"{g} {label}" for g, label in used.items()]
    for (name, recipe), letter in groups.items():
        size = "x".join(str(n) for n in gd.tile_size(name)) if name in gd.ENTITIES else "?"
        legend.append(f"{letter} {name}" + (f" [{recipe}]" if recipe else "") + f"  {size}  x{counts[(name, recipe)]}")
    return out, legend


def ascii_art(layout: Layout) -> str:
    """Grid with tile coordinates on both axes. One character per tile; '.' is empty."""
    if not layout.grid:
        return "(empty blueprint)\n"
    glyph, legend = glyphs(layout)
    x1, y1, x2, y2 = layout.bounds()
    x1, y1, x2, y2 = x1 - 1, y1 - 1, x2 + 1, y2 + 1
    pad = max(len(str(y1)), len(str(y2)))
    lines = []
    if layout.label:
        lines.append(f"# {layout.label}")
    lines.append(f"# x = {x1}..{x2}, y = {y1}..{y2} (tile coordinates; north is up)")
    # column ruler: tens line + ones line, so any x can be read off directly
    tens = "".join(str(abs(x) // 10 % 10) if x % 10 == 0 else " " for x in range(x1, x2 + 1))
    ones = "".join(str(abs(x) % 10) for x in range(x1, x2 + 1))
    lines.append(" " * (pad + 1) + tens)
    lines.append(" " * (pad + 1) + ones)
    for y in range(y1, y2 + 1):
        row = []
        for x in range(x1, x2 + 1):
            ents = layout.grid.get((x, y))
            row.append("." if not ents else ("!" if len(ents) > 1 else glyph[ents[0].number]))
        lines.append(f"{y:>{pad}} " + "".join(row))
    lines.append("")
    lines.append("legend: (! = overlapping entities)")
    lines.extend("  " + entry for entry in legend)
    return "\n".join(lines) + "\n"


_COLORS = {
    "transport-belt": (214, 178, 64), "underground-belt": (170, 138, 40), "splitter": (232, 200, 96),
    "inserter": (240, 150, 40), "electric-pole": (150, 100, 60), "pipe": (90, 140, 200),
    "pipe-to-ground": (60, 110, 170), "assembling-machine": (90, 130, 170), "furnace": (170, 100, 80),
    "container": (140, 120, 90), "logistic-container": (150, 90, 150), "lab": (200, 200, 220),
    "mining-drill": (110, 150, 110), "beacon": (120, 200, 200), "storage-tank": (100, 150, 190),
}


def png(layout: Layout, path: Path, scale: int = 32) -> None:
    from PIL import Image, ImageDraw

    if not layout.grid:
        Image.new("RGB", (scale, scale), (40, 40, 40)).save(path)
        return
    x1, y1, x2, y2 = layout.bounds()
    w, h = (x2 - x1 + 3) * scale, (y2 - y1 + 3) * scale
    img = Image.new("RGB", (w, h), (38, 38, 42))
    draw = ImageDraw.Draw(img)
    for gx in range(0, w, scale):
        draw.line([(gx, 0), (gx, h)], fill=(52, 52, 58))
    for gy in range(0, h, scale):
        draw.line([(0, gy), (w, gy)], fill=(52, 52, 58))
    letters, _ = glyphs(layout)

    def px(tx: float, ty: float) -> tuple[float, float]:
        return (tx - x1 + 1) * scale, (ty - y1 + 1) * scale

    for e in layout.entities:
        if not e.proto or not e.tiles:
            continue
        tx, ty = e.tile
        ew = max(t[0] for t in e.tiles) - tx + 1
        eh = max(t[1] for t in e.tiles) - ty + 1
        a, b = px(tx, ty), px(tx + ew, ty + eh)
        color = _COLORS.get(e.type, (130, 130, 140))
        m = 2 if ew * eh > 1 else 4
        draw.rectangle([a[0] + m, a[1] + m, b[0] - m, b[1] - m], fill=color, outline=(20, 20, 20))
        cx, cy = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
        if e.type in gd.BELT_TYPES or e.type == "inserter":
            d = _move_direction(e) if e.type == "inserter" else e.direction
            dx, dy = VECTORS.get(d, (0, -1))
            r = scale * 0.3
            tip = (cx + dx * r, cy + dy * r)
            left = (cx - dx * r - dy * r * 0.7, cy - dy * r + dx * r * 0.7)
            right = (cx - dx * r + dy * r * 0.7, cy - dy * r - dx * r * 0.7)
            draw.polygon([tip, left, right], fill=(25, 25, 25))
        elif ew * eh > 1:
            text = letters.get(e.number, "?")
            if e.recipe:
                text += " " + e.recipe[: max(3, ew * 4)]
            draw.text((a[0] + 5, a[1] + 4), text, fill=(255, 255, 255))
    img.save(path)
