"""Hidden-line-removal SVG views of a CadQuery shape (adapted from diy/view.py).

Every view is (direction towards the viewer, screen-right axis). Screen-up is
cross(direction, right), so Z is up in all side views and +Y is up in the plan.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cadquery as cq

VIEWS: dict[str, tuple[tuple[float, float, float], tuple[float, float, float]]] = {
    "iso": ((1.0, -1.0, 0.8), (0.7071, 0.7071, 0.0)),
    "front": ((0.0, -1.0, 0.0), (1.0, 0.0, 0.0)),    # looking along +Y
    "back": ((0.0, 1.0, 0.0), (-1.0, 0.0, 0.0)),     # looking along -Y
    "side": ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0)),      # from +X, looking along -X
    "left": ((-1.0, 0.0, 0.0), (0.0, -1.0, 0.0)),    # from -X
    "top": ((0.0, 0.0, 1.0), (1.0, 0.0, 0.0)),       # plan, +Y up
    "bottom": ((0.0, 0.0, -1.0), (1.0, 0.0, 0.0)),
}
ORTHO_VIEWS = {"front", "back", "side", "left", "top", "bottom"}

LINE = "#111"
HIDDEN = "#9aa0a6"
DIM = "#1a6bb5"


class RenderError(Exception):
    pass


def _cross(a, b):
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def _norm(v):
    m = sum(c * c for c in v) ** 0.5
    return tuple(c / m for c in v)


@dataclass
class Projection:
    visible: list[str]
    hidden: list[str]
    reference: list[str]
    umin: float
    umax: float
    vmin: float
    vmax: float

    @property
    def width(self) -> float:
        return self.umax - self.umin

    @property
    def height(self) -> float:
        return self.vmax - self.vmin


def split_reference(shape: cq.Shape) -> tuple[list[cq.Shape], list[cq.Shape]]:
    """Split into (solids, reference shapes). Faces/edges/wires are reference geometry
    (planes, boundaries, axes): drawn, but they never hide anything."""
    solids, refs = [], []

    def visit(s):
        kind = s.ShapeType()
        if kind in ("Solid", "CompSolid"):
            solids.append(s)
        elif kind == "Compound":
            for child in s:
                visit(child)
        else:
            refs.append(s)

    visit(shape)
    return solids, refs


def _ax2(view):
    from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt

    proj_dir, x_dir = VIEWS[view]
    return gp_Ax2(gp_Pnt(), gp_Dir(*_norm(proj_dir)), gp_Dir(*_norm(x_dir)))


def _project_reference(refs: list[cq.Shape], view: str):
    """Edges of reference shapes projected without hidden-line removal."""
    from cadquery.occ_impl.exporters.svg import getPaths
    from cadquery.occ_impl.shapes import TOLERANCE, Compound, Shape
    from OCP.BRepLib import BRepLib
    from OCP.HLRAlgo import HLRAlgo_Projector
    from OCP.HLRBRep import HLRBRep_Algo, HLRBRep_HLRToShape

    hlr = HLRBRep_Algo()
    for r in refs:
        hlr.Add(r.wrapped)
    hlr.Projector(HLRAlgo_Projector(_ax2(view)))
    hlr.Update()  # no Hide(): everything stays visible
    res = HLRBRep_HLRToShape(hlr)
    comps = []
    for getter in (res.VCompound, res.Rg1LineVCompound, res.OutLineVCompound):
        s = getter()
        if not s.IsNull():
            comps.append(s)
    for el in comps:
        BRepLib.BuildCurves3d_s(el, TOLERANCE)
    shapes = [Shape(s) for s in comps]
    if not shapes:
        return [], None
    _, paths = getPaths(shapes, [])
    return paths, Compound.makeCompound(shapes).BoundingBox()


def project(shape: cq.Shape, view: str) -> Projection:
    """Project ``shape`` into 2D SVG path strings: hidden-line removal for solids,
    plain wireframe for reference geometry (faces, edges)."""
    if view not in VIEWS:
        raise RenderError(f"unknown view '{view}' (choose from {', '.join(VIEWS)})")
    solids, refs = split_reference(shape)
    p = _project_solids(cq.Compound.makeCompound(solids), view) if solids else None
    if refs:
        paths, bb = _project_reference(refs, view)
        if p is None and not paths:
            raise RenderError("nothing to draw in this view")
        if p is None:
            p = Projection([], [], [], bb.xmin, bb.xmax, bb.ymin, bb.ymax)
        if bb is not None:
            p.reference = paths
            p.umin, p.umax = min(p.umin, bb.xmin), max(p.umax, bb.xmax)
            p.vmin, p.vmax = min(p.vmin, bb.ymin), max(p.vmax, bb.ymax)
    if p is None:
        raise RenderError("nothing to draw in this view")
    return p


def _project_solids(shape: cq.Shape, view: str) -> Projection:
    """Hidden-line removal for solids."""
    from cadquery.occ_impl.exporters.svg import getPaths
    from cadquery.occ_impl.shapes import TOLERANCE, Compound, Shape
    from OCP.BRepLib import BRepLib
    from OCP.HLRAlgo import HLRAlgo_Projector
    from OCP.HLRBRep import HLRBRep_Algo, HLRBRep_HLRToShape

    hlr = HLRBRep_Algo()
    hlr.Add(shape.wrapped)
    hlr.Projector(HLRAlgo_Projector(_ax2(view)))
    hlr.Update()
    hlr.Hide()
    res = HLRBRep_HLRToShape(hlr)

    visible, hidden = [], []
    for getter in (res.VCompound, res.Rg1LineVCompound, res.OutLineVCompound):
        s = getter()
        if not s.IsNull():
            visible.append(s)
    for getter in (res.HCompound, res.OutLineHCompound):
        s = getter()
        if not s.IsNull():
            hidden.append(s)
    for el in visible + hidden:
        BRepLib.BuildCurves3d_s(el, TOLERANCE)

    vis_shapes = [Shape(s) for s in visible]
    hid_shapes = [Shape(s) for s in hidden]
    if not vis_shapes and not hid_shapes:
        return Projection([], [], [], 0, 0, 0, 0)
    hidden_paths, visible_paths = getPaths(vis_shapes, hid_shapes)
    bb = Compound.makeCompound(vis_shapes + hid_shapes).BoundingBox()
    return Projection(visible_paths, hidden_paths, [], bb.xmin, bb.xmax, bb.ymin, bb.ymax)


def exact_bbox(shape: cq.Shape):
    """Tight bounding box that ignores any triangulation left on the shape by exports
    (cq's default BoundingBox() grows once a mesh exists)."""
    from cadquery.occ_impl.geom import BoundBox
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib

    box = Bnd_Box()
    BRepBndLib.AddOptimal_s(shape.wrapped, box, False, False)
    return BoundBox(box)


def fmt_len(mm: float, unit_mm: float = 1.0, unit: str = "mm") -> str:
    v = mm / unit_mm
    a = abs(v)
    s = f"{v:.0f}" if a >= 100 else f"{v:.1f}" if a >= 10 else f"{v:.2f}"
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return f"{s} {unit}"


def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _hdim(x1, x2, y, label):
    return (
        f'<g stroke="{DIM}" stroke-width="1" fill="none">'
        f'<line x1="{x1:.1f}" y1="{y:.1f}" x2="{x2:.1f}" y2="{y:.1f}"/>'
        f'<line x1="{x1:.1f}" y1="{y - 5:.1f}" x2="{x1:.1f}" y2="{y + 5:.1f}"/>'
        f'<line x1="{x2:.1f}" y1="{y - 5:.1f}" x2="{x2:.1f}" y2="{y + 5:.1f}"/></g>'
        f'<text x="{(x1 + x2) / 2:.1f}" y="{y + 16:.1f}" text-anchor="middle" '
        f'fill="{DIM}" font-size="13">{_esc(label)}</text>'
    )


def _vdim(x, y1, y2, label):
    ym = (y1 + y2) / 2
    return (
        f'<g stroke="{DIM}" stroke-width="1" fill="none">'
        f'<line x1="{x:.1f}" y1="{y1:.1f}" x2="{x:.1f}" y2="{y2:.1f}"/>'
        f'<line x1="{x - 5:.1f}" y1="{y1:.1f}" x2="{x + 5:.1f}" y2="{y1:.1f}"/>'
        f'<line x1="{x - 5:.1f}" y1="{y2:.1f}" x2="{x + 5:.1f}" y2="{y2:.1f}"/></g>'
        f'<text x="{x + 8:.1f}" y="{ym:.1f}" fill="{DIM}" font-size="13" '
        f'transform="rotate(90 {x + 8:.1f} {ym:.1f})" text-anchor="middle">{_esc(label)}</text>'
    )


def render_svg(
    shape: cq.Shape,
    view: str = "iso",
    *,
    title: str | None = None,
    unit_mm: float = 1.0,
    unit: str = "mm",
    dimensions: bool | None = None,
    show_hidden: bool = True,
    width: int = 1200,
    height: int = 800,
) -> str:
    """Render one view as an SVG string. Geometry is expected in millimetres.

    ``unit_mm``/``unit`` only affect the labels (the project's display unit).
    Orthographic views get overall dimension lines unless ``dimensions=False``.
    """
    bb = exact_bbox(shape)
    p = project(shape, view)
    if dimensions is None:
        dimensions = view in ORTHO_VIEWS

    top_pad = 48 if title else 24
    pad_l, pad_r, pad_b = 24, (64 if dimensions else 24), (84 if dimensions else 56)
    aw, ah = width - pad_l - pad_r, height - top_pad - pad_b
    s = min(aw / max(p.width, 1e-9), ah / max(p.height, 1e-9))
    ox = pad_l + (aw - p.width * s) / 2
    oy = top_pad + (ah - p.height * s) / 2

    def px(u, v):
        return ox + (u - p.umin) * s, oy + (p.vmax - v) * s

    def group(paths, color, dash=""):
        # Stroke widths are in model units (the group is scaled), so divide by s to get px.
        d = "".join(f'<path d="{d}"/>' for d in paths)
        return (
            f'<g stroke="{color}" fill="none" stroke-width="{1.4 / s:.5f}" '
            f'stroke-linejoin="round" stroke-linecap="round"{dash}>{d}</g>'
        )

    tf = f"translate({ox - p.umin * s:.3f},{oy + p.vmax * s:.3f}) scale({s:.6f},{-s:.6f})"
    body = [f'<g transform="{tf}">']
    if p.reference:
        body.append(group(p.reference, DIM, f' stroke-dasharray="{9 / s:.4f},{3 / s:.4f}"'))
    if show_hidden and p.hidden:
        body.append(group(p.hidden, HIDDEN, f' stroke-dasharray="{5 / s:.4f},{4 / s:.4f}"'))
    body.append(group(p.visible, LINE))
    body.append("</g>")

    ann = []
    if dimensions:
        x1, y1 = px(p.umin, p.vmin)
        x2, _ = px(p.umax, p.vmin)
        _, yt = px(p.umin, p.vmax)
        ann.append(_hdim(x1, x2, y1 + 26, fmt_len(p.width, unit_mm, unit)))
        ann.append(_vdim(x2 + 26, yt, y1, fmt_len(p.height, unit_mm, unit)))
    caption = (
        f"Overall {fmt_len(bb.xlen, unit_mm, unit)} × {fmt_len(bb.ylen, unit_mm, unit)} × "
        f"{fmt_len(bb.zlen, unit_mm, unit)}  (X × Y × Z)   view: {view}"
    )
    ann.append(
        f'<text x="{pad_l}" y="{height - 14}" fill="#555" font-size="12">{_esc(caption)}</text>'
    )
    ann.append(_scale_bar(width - pad_r - 4, height - 14, s, unit_mm, unit))
    if title:
        ann.append(
            f'<text x="{pad_l}" y="30" fill="#111" font-size="20" font-weight="600">'
            f"{_esc(title)}</text>"
        )

    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" font-family="system-ui, Helvetica, Arial, sans-serif">'
        f'<rect width="{width}" height="{height}" fill="#fff"/>'
        + "".join(body)
        + "".join(ann)
        + "</svg>"
    )


def _nice(v: float) -> float:
    """Round down to 1/2/5 × 10^n."""
    import math

    if v <= 0:
        return 1.0
    e = 10 ** math.floor(math.log10(v))
    for m in (5, 2, 1):
        if m * e <= v:
            return m * e
    return e


def _scale_bar(x_right, y, s_px_per_mm, unit_mm, unit):
    target_units = (110 / s_px_per_mm) / unit_mm  # about 110px long
    nice = _nice(target_units)
    length = nice * unit_mm * s_px_per_mm
    x0 = x_right - length
    return (
        f'<g stroke="#333" stroke-width="1.5" fill="none">'
        f'<line x1="{x0:.1f}" y1="{y - 8}" x2="{x_right:.1f}" y2="{y - 8}"/>'
        f'<line x1="{x0:.1f}" y1="{y - 13}" x2="{x0:.1f}" y2="{y - 3}"/>'
        f'<line x1="{x_right:.1f}" y1="{y - 13}" x2="{x_right:.1f}" y2="{y - 3}"/></g>'
        f'<text x="{x_right:.1f}" y="{y - 18}" text-anchor="end" fill="#333" font-size="12">'
        f"{fmt_len(nice * unit_mm, unit_mm, unit)}</text>"
    )


def svg_to_png(svg: str | Path, png_path: Path, width: int | None = None) -> None:
    import cairosvg

    data = svg if isinstance(svg, str) else Path(svg).read_text(encoding="utf-8")
    cairosvg.svg2png(bytestring=data.encode(), write_to=str(png_path), output_width=width)
