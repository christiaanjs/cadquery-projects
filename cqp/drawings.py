"""Extra drawings: exploded isometric and a parts sheet."""

from __future__ import annotations

import cadquery as cq

from .loader import Model
from .render import exact_bbox, fmt_len, render_svg


def exploded_shape(model: Model, factor: float = 1.6) -> cq.Compound:
    """Push every part away from the assembly centre by ``factor``."""
    parts = model.parts()
    bb = exact_bbox(model.compound())
    centre = cq.Vector(bb.center.x, bb.center.y, bb.center.z)
    moved = []
    for _, shape, _ in parts:
        pc = shape.Center()
        d = pc - centre
        moved.append(shape.translate(d * (factor - 1.0)))
    return cq.Compound.makeCompound(moved)


def exploded_svg(model: Model, *, title: str, unit_mm: float, unit: str, factor: float = 1.6):
    if len(model.parts()) < 2:
        return None
    return render_svg(
        exploded_shape(model, factor), "iso", title=f"{title} — exploded",
        unit_mm=unit_mm, unit=unit, dimensions=False,
    )


def part_rows(model: Model, unit_mm: float = 1.0, unit: str = "mm") -> list[dict]:
    """One row per distinct part (identical name stems and sizes are grouped)."""
    import re

    groups: dict[tuple, dict] = {}
    for name, shape, color in model.parts():
        bb = exact_bbox(shape)
        dims = sorted((bb.xlen, bb.ylen, bb.zlen), reverse=True)
        base = re.sub(r"[_-]\d+$", "", name)
        key = (base, tuple(round(d, 2) for d in dims))
        row = groups.setdefault(
            key,
            {
                "name": base,
                "qty": 0,
                "size": " × ".join(fmt_len(d, unit_mm, unit).replace(f" {unit}", "") for d in dims)
                + f" {unit}",
                "volume_cm3": round(shape.Volume() / 1000.0, 2) if shape.ShapeType() in
                ("Solid", "Compound", "CompSolid") else 0.0,
                "color": _hex(color),
            },
        )
        row["qty"] += 1
    return sorted(groups.values(), key=lambda r: r["name"])


def _hex(color) -> str | None:
    if color is None:
        return None
    try:
        r, g, b, _ = color.toTuple()
        return f"#{int(r * 255):02x}{int(g * 255):02x}{int(b * 255):02x}"
    except Exception:
        return None
