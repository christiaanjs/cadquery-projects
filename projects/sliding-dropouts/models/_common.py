"""Shared geometry for the sliding dropout inserts. Units: mm.

World coordinates (all models)
------------------------------
Origin = the frame's nominal axle centre. X forward (towards the BB, along the slide),
Z up, Y along the axle with +Y = left (non-drive, brake) side, -Y = right (drive, UDH) side.

Each insert is built in a *local* frame and then placed:
local x = world X, local y = world Z, local z = distance outboard of the insert's inboard face.
Inboard features (NDS hub boss, brake posts) have negative local z.

Construction
------------
Proportions follow the Tange sliding inserts in the project folder (tange-*.jpg/png): a flat
plate from the axle boss up and forward to a raised key holding two clamp bolts. The insert sits
on the INBOARD face of the frame's socket plate with the key riding in the frame slot; two M5
bolts through an outer clamp plate thread into the key, and an M4 adjuster screw pushes on the
tongue's front end. The frame plate is cut away around the axle boss (over the slide travel),
so the boss can be as thick as the UDH / thru-axle interface needs.

Frame / hub interface: the frame's insert seats (frame_seat_span apart) are fixed, and the hub
(hub_old wide) sits hub_gap inside each insert's inboard face. Where the two disagree the axle
region of the insert is offset from the seat and the plate is bent (or thinned) to take it up.

Specs used (project root): ``udh_frame_spec.py`` (SRAM UDH frame spec 90-7518-190-000 H.14,
see ``udh-spec.pdf``) and ``disc_brake_mounts.py`` (Verdone rear caliper mount ordinates).
"""

from __future__ import annotations

import math
import sys
from dataclasses import dataclass
from pathlib import Path

import cadquery as cq
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import disc_brake_mounts as dbm  # noqa: E402
import udh_frame_spec as udh  # noqa: E402

# Parameters shared by both inserts (and the assembly).
PARAMS = {
    # Frame / hub interface, all face to face. The frame's insert seats are fixed; the hub is the
    # one being fitted; the insert's axle region sits hub_gap outboard of each hub end face and
    # the plate steps (bends) to the seat. Examples: seats 149 + hub 142 is the UDH native fit
    # (OLD + 7), seats 149 + hub 148 fits a wider hub to a 142 frame, and a QR flat-dropout frame
    # (seats 135) taking a 142 hub is frame_seat_span = 135, hub_old = 142.
    "frame_seat_span": 149.0,     # spacing of the frame's insert seats (slider-region inboard faces)
    "hub_old": 142.0,             # target hub width (OLD, end face to end face)
    "hub_gap": 3.5,               # per side: hub end face -> insert inboard face (UDH: OLD + 7 -> 3.5)
    "axle_offset_x": 32.0,        # axle offset from the frame's nominal position; + = rearward (longer stays)
    "axle_offset_y": 32.0,        # + = axle up
    "plate_thickness": 9.0,       # insert plate thickness
    "min_plate_thickness": 4.0,   # refuse to build thinner plates (hub_offset_mode "thin")
    "hub_offset_mode": "bend",    # "bend": full-thickness plate, axle region joggled out (or in)
                                  #   by the step to the seat; "thin": whole plate thinner instead
    "bend_start": 30.0,           # bend starts this far from the key centre towards the axle
    "bend_length": 8.0,           # length of the sloped transition
    "tongue_length": 56.0,        # nominal axle -> front end of the insert
    "tongue_height": 24.0,        # tongue (key region) height, centred on bolt_z
    "corner_radius": 5.0,
    "boss_radius": 18.0,          # outer profile around the axle (UDH: R14.5-19)
    "bolt_x": 24.0,               # first clamp bolt, forward of nominal axle
    "bolt_z": 26.0,               # clamp bolt / key line, above nominal axle (Tange: key up and forward)
    "bolt_pitch": 18.0,
    "key_length": 31.0,           # raised key around the bolts; rides in the frame slot
    "key_width": 10.0,
    "key_height": 3.0,            # key protrudes outboard into the slot (< frame plate thickness)
    "bolt_tap_dia": 4.2,          # M5x0.8 tap drill
    "adjuster_tap_dia": 3.3,      # M4x0.7 tap drill, along X into the front end
    "adjuster_depth": 10.0,
    # Reliefs: smooth concave curves in the outline between features (each section on/off).
    # Each is sized automatically to keep relief_margin from the key, brake bosses etc.
    "relieve_brake_posts": True,  # between the two brake bosses
    "relieve_brake_axle": True,   # between the brake mount and the axle boss
    "relieve_axle_slider": False, # between the axle boss and the slider (key) region
    "relieve_slider_brake": True, # between the slider (key) region and the brake mount
    "relief_max_depth": 12.0,     # deepest a relief may cut in from the hull edge
    "relief_max_ratio": 0.35,     # ... and at most this fraction of the edge length
    "relief_margin": 4.0,         # material kept around the key, holes, brake bosses, UDH stop
    "relief_min_chord": 15.0,     # skip edges shorter than this (a relief would read as a notch)
}

FRAME_PLATE = {
    "frame_plate_thickness": 6.0,
    "frame_plate_margin": 7.0,    # plate around the key slot
    "frame_boss_clearance": 1.5,  # frame cut-out around the insert's axle boss
    "slot_travel": 12.0,          # slot length minus key length (adjustment range)
}

UDH_BORE = udh.DROPOUT["hanger_bore_dia"]                   # 20 +0.1/0
UDH_RECESS_DEPTH = udh.DROPOUT["hanger_recess_depth"]       # 4 +0.5/-0.2 (floor = datum B)
UDH_FLOOR_TO_OUTBOARD = udh.DROPOUT["recess_floor_to_inboard_face"]  # 12.5 +/-0.2 (see note)
UDH_POCKET_R_MIN = udh.DROPOUT["boss_inner_radius_min"]     # R15 MIN, pos. dia 0.5 to A
UDH_STOP_OFFSET = udh.DROPOUT["stop_face_offset"]           # 14.4 +/-0.1
UDH_STOP_ANGLE = udh.DROPOUT["stop_face_angle"]             # 30 +/-3 deg
NDS_PROTRUSION_DIA_MIN = udh.DROPOUT["contact_face_dia_min_alt_protrusion"]  # 25 MIN
AXLE_DIA = udh.AXLE["shank_dia"]                            # 11.96 -0.07


@dataclass
class Layout:
    hub_old: float
    y_in: float          # |world Y| of the insert inboard face in the axle region
    t: float             # insert plate thickness
    seat_y: float        # |world Y| of the frame plate's inboard face (= insert outboard face)
    seat_span: float     # face-to-face spacing of the frame's insert seats
    gap: float           # per-side gap, hub end face -> insert inboard face
    step: float          # how far the axle region sits outboard of the seat (+) or inboard (-)
    ax: float            # axle centre, local x
    ay: float            # axle centre, local y (world Z)
    zs: float = 0.0      # local z shift of the slider (key) region; non-zero when bent
    kx: float = 0.0      # key centre, local x / y
    ky: float = 0.0


def layout(p: dict) -> Layout:
    """Insert placement. Local z = 0 is the insert's inboard face in the axle region.

    That face sits hub_gap outboard of the hub end face: |Y| = hub_old / 2 + hub_gap. The frame's
    slider seat is fixed at frame_seat_span / 2, so the axle region is `step` = (hub_old / 2 +
    hub_gap) - frame_seat_span / 2 further out (+) or in (-) than the seat. "bend" keeps the plate
    thickness and joggles the slider region onto the seat (zs = -step); "thin" instead thins the
    whole plate by `step`.
    """
    gap, hub_old, seat_span = p["hub_gap"], p["hub_old"], p["frame_seat_span"]
    y_in = hub_old / 2 + gap
    step = y_in - seat_span / 2
    t, zs = p["plate_thickness"], 0.0
    if p["hub_offset_mode"] == "thin":
        t -= step
        if t < p["min_plate_thickness"]:
            raise ValueError(
                f"the {step:.1f} mm step between hub and frame seat leaves a {t:.1f} mm insert plate "
                f"(< {p['min_plate_thickness']}); increase plate_thickness or use 'bend'"
            )
    elif p["hub_offset_mode"] == "bend":
        zs = 0.0 - step + 0.0
    else:
        raise ValueError(f"hub_offset_mode must be 'bend' or 'thin', not {p['hub_offset_mode']!r}")
    return Layout(hub_old, y_in, t, seat_span / 2 + p["plate_thickness"], seat_span, gap, step,
                  0.0 - p["axle_offset_x"], p["axle_offset_y"], zs,
                  p["bolt_x"] + p["bolt_pitch"] / 2, p["bolt_z"])


def _hull_pieces(circles, n: int = 720):
    """Convex hull of circles as counter-clockwise pieces [(circle index, a0, a1)] (radians).

    Consecutive pieces are joined by straight tangent lines. cq.Sketch.hull() fails on some
    layouts, so this samples points on each circle, hulls them, and turns each run of points
    from one circle back into an arc of that exact circle (a0 == a1 for a single point).
    """
    pts = []
    for i, ((x, y), r) in enumerate(circles):
        for k in range(n):
            a = 2 * math.pi * k / n
            pts.append((x + r * math.cos(a), y + r * math.sin(a), i, k))
    pts.sort()

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    def chain(seq):
        out = []
        for q in seq:
            while len(out) >= 2 and cross(out[-2], out[-1], q) <= 1e-12:
                out.pop()
            out.append(q)
        return out

    hull = chain(pts)[:-1] + chain(reversed(pts))[:-1]   # counter-clockwise
    if len({q[2] for q in hull}) == 1:                   # one circle contains the rest
        return [(hull[0][2], 0.0, 2 * math.pi)]
    # Start at a change of circle so no run wraps around the end of the list.
    start = next(j for j in range(len(hull)) if hull[j][2] != hull[j - 1][2])
    hull = hull[start:] + hull[:start]
    runs = []
    for q in hull:
        if runs and runs[-1][0][2] == q[2]:
            runs[-1].append(q)
        else:
            runs.append([q])
    pieces = []
    for run in runs:
        a0 = 2 * math.pi * run[0][3] / n
        a1 = 2 * math.pi * run[-1][3] / n
        if a1 < a0:
            a1 += 2 * math.pi
        pieces.append((run[0][2], a0, a1))
    return pieces


def _on(circle, a):
    (x, y), r = circle
    return np.array([x + r * math.cos(a), y + r * math.sin(a)])


def _tangent(a):
    return np.array([-math.sin(a), math.cos(a)])        # direction of travel, counter-clockwise


def _bezier(p0, t0, p1, t1, n=48):
    k = np.linalg.norm(p1 - p0) / 3
    c = [p0, p0 + k * t0, p1 - k * t1, p1]
    s = np.linspace(0, 1, n)[:, None]
    return ((1 - s) ** 3 * c[0] + 3 * (1 - s) ** 2 * s * c[1] + 3 * (1 - s) * s ** 2 * c[2]
            + s ** 3 * c[3]), c


def _arc_pts(circle, a0, a1, step=0.0873):          # ~5 deg
    m = max(2, int(abs(a1 - a0) / step) + 1)
    return np.array([_on(circle, a) for a in np.linspace(a0, a1, m)])


def _poly_hits(poly, centres, radii):
    """True where a disc (centre, radius) overlaps the closed polygon poly (N x 2)."""
    a, b = poly, np.roll(poly, -1, axis=0)
    ab = b - a
    ap = centres[:, None, :] - a[None]
    t = np.clip((ap * ab).sum(-1) / np.maximum((ab * ab).sum(-1), 1e-12), 0, 1)
    d = np.linalg.norm(ap - t[..., None] * ab, axis=-1).min(1)
    x, y = centres[:, 0:1], centres[:, 1:2]
    ya, yb = a[None, :, 1], b[None, :, 1]
    cross = ((ya > y) != (yb > y)) & (
        x < a[None, :, 0] + (y - ya) * (b[None, :, 0] - a[None, :, 0]) / np.where(yb == ya, 1e-12, yb - ya))
    inside = cross.sum(1) % 2 == 1
    return inside | (d < radii)


def outline_circles(p: dict, lay: Layout):
    """(centre, radius, role) circles whose convex hull is the plate outline (boss + tongue)."""
    r = p["corner_radius"]
    h = p["tongue_height"] / 2 - r
    xf = p["tongue_length"] - r
    z = p["bolt_z"]
    return [
        ((lay.ax, lay.ay), p["boss_radius"], "axle"),
        ((0.0, z + h), r, "slider"), ((0.0, z - h), r, "slider"),
        ((xf, z + h), r, "slider"), ((xf, z - h), r, "slider"),
    ]


RELIEF_PAIRS = {
    frozenset({"brake"}): "relieve_brake_posts",
    frozenset({"brake", "axle"}): "relieve_brake_axle",
    frozenset({"axle", "slider"}): "relieve_axle_slider",
    frozenset({"slider", "brake"}): "relieve_slider_brake",
}


def protected_circles(p: dict, lay: Layout):
    """Features reliefs must keep relief_margin away from: key (+ slide), adjuster."""
    m = p["relief_margin"]
    out = []
    half = (p["key_length"] - p["key_width"]) / 2
    for k in range(11):
        out.append(((lay.kx - half + 2 * half * k / 10, lay.ky), p["key_width"] / 2 + m))
    x0 = p["tongue_length"] - p["adjuster_depth"]
    out += [((x0 + i, lay.ky), p["adjuster_tap_dia"] / 2 + m) for i in range(0, 11, 2)]
    return out


def outline_face(p: dict, lay: Layout, extra=(), protect=()):
    """Plate outline: convex hull of the feature circles with smooth concave reliefs.

    A relief replaces the straight hull edge between two features: the outline follows the
    first feature's circle a little further round, then a cubic Bezier runs tangent-
    continuously into the second feature's circle. The largest relief (by area removed) is
    used whose depth stays within relief_max_depth and relief_max_ratio x edge length, and
    that keeps every protected circle (key and slide, holes, other features, brake bosses,
    UDH stop) clear by its margin. Returns (face, reliefs = [(role_a, role_b, depth, length)]).
    """
    circles = list(outline_circles(p, lay)) + list(extra)
    cg = [(c, r) for c, r, _ in circles]
    pieces = _hull_pieces(cg)
    # Guards: (centre, radius, owner). A relief ignores guards owned by its own end features
    # (their other corners, the margin under the boss it wraps); everything else stays clear.
    feat = [(c, r + 0.5, role) for c, r, role in circles]  # no relief may cut another feature
    guard = [g if len(g) == 3 else (*g, None)
             for g in list(protected_circles(p, lay)) + list(protect)] + feat
    gc = np.array([g[0] for g in guard], float)
    gr = np.array([g[1] for g in guard], float)
    owner = [g[2] for g in guard]
    ext = [[0.0, 0.0] for _ in pieces]                     # extra wrap (radians) at each end
    joins = {}
    reliefs = []
    npc = len(pieces)
    for j in range(npc if npc > 1 else 0):
        ia, _, a1 = pieces[j]
        ib, b0, _ = pieces[(j + 1) % npc]
        ra, rb = circles[ia][2], circles[ib][2]
        toggle = RELIEF_PAIRS.get(frozenset({ra.split(":")[0], rb.split(":")[0]}))
        if ra == rb or not toggle or not p.get(toggle, False):
            continue                                       # same boss, or section switched off
        ca, cb = cg[ia], cg[ib]
        ta, tb = _on(ca, a1), _on(cb, b0)
        length = float(np.linalg.norm(tb - ta))
        if length < p["relief_min_chord"]:
            continue
        u = (tb - ta) / length
        n_in = np.array([-u[1], u[0]])                    # left of a CCW edge = into the plate
        cap = min(p["relief_max_depth"], p["relief_max_ratio"] * length)
        mine = np.array([o not in (ra, rb) for o in owner])
        best = None
        for ratio in (1.0, 0.6, 1.6, 0.35, 2.8):
            for w in np.arange(1.0, 60.0, 1.0):
                wa, wb = w * min(1, 1 / ratio), w * min(1, ratio)
                da, db = wa / ca[1], wb / cb[1]
                if da > math.radians(100) or db > math.radians(100):
                    break
                pa, pb = _on(ca, a1 + da), _on(cb, b0 - db)
                curve, _ = _bezier(pa, _tangent(a1 + da), pb, _tangent(b0 - db))
                depth = float(((curve - ta) @ n_in).max())
                if depth > cap:
                    break
                region = np.vstack([curve, _arc_pts(cb, b0 - db, b0)[1:], [ta],
                                    _arc_pts(ca, a1, a1 + da)[1:-1]])
                if _poly_hits(region, gc[mine], gr[mine]).any():
                    break
                x, y = region[:, 0], region[:, 1]
                area = 0.5 * abs(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1)))
                if best is None or area > best[0]:
                    best = (area, da, db, depth)
        if best is None or best[3] < 0.5:
            continue
        _, da, db, depth = best
        ext[j][1] = da
        ext[(j + 1) % npc][0] = db
        joins[j] = True
        reliefs.append((ra.split(":")[0], rb.split(":")[0], round(depth, 2), round(length, 1)))

    # Assemble: arcs (extended where relieved), lines or Bezier joins between them.
    arcs = []
    for k, (i, a0, a1) in enumerate(pieces):
        lo, hi = a0 - ext[k][0], a1 + ext[k][1]
        (x, y), r = cg[i]
        arc = (cq.Edge.makeCircle(r, cq.Vector(x, y, 0), cq.Vector(0, 0, 1),
                                  math.degrees(lo), math.degrees(hi)) if hi - lo > 1e-9 else None)
        arcs.append((arc, lo, hi, i))
    if npc == 1:
        return cq.Face.makeFromWires(cq.Wire.assembleEdges([arcs[0][0]])), reliefs
    edges = []
    for k, (arc, _lo, hi, i) in enumerate(arcs):
        if arc is not None:
            edges.append(arc)
        nxt, nlo, _, ni = arcs[(k + 1) % npc]
        p0 = arc.endPoint() if arc is not None else cq.Vector(*_on(cg[i], hi), 0)
        p1 = nxt.startPoint() if nxt is not None else cq.Vector(*_on(cg[ni], nlo), 0)
        if k in joins:
            _, ctrl = _bezier(np.array([p0.x, p0.y]), _tangent(hi), np.array([p1.x, p1.y]),
                              _tangent(nlo))
            pts = [p0] + [cq.Vector(c[0], c[1], 0) for c in ctrl[1:3]] + [p1]
            edges.append(cq.Edge.makeBezier(pts))
        elif (p1 - p0).Length > 1e-9:
            edges.append(cq.Edge.makeLine(p0, p1))
    return cq.Face.makeFromWires(cq.Wire.assembleEdges(edges)), reliefs


def _prism(face: cq.Face, z0: float, z1: float) -> cq.Solid:
    return cq.Solid.extrudeLinear(face.translate((0, 0, z0)), cq.Vector(0, 0, z1 - z0))


def plate(p: dict, lay: Layout, face: cq.Face, depth=None) -> cq.Workplane:
    """Outline extruded outboard from the inboard face (local z = 0).

    With a bend (lay.zs != 0) the slider region sits at z in [zs, zs + t], the axle region at
    [0, t], joined by a sloped joggle across bend_length, bend lines square to key -> axle.
    ``depth`` gives a plain extrusion [0, depth] (used for thick bosses near the axle).
    """
    if depth is not None or lay.zs == 0:
        return cq.Workplane("XY").add(_prism(face, 0, depth if depth is not None else lay.t))
    dx, dy = lay.ax - lay.kx, lay.ay - lay.ky
    dist = math.hypot(dx, dy)
    dx, dy = dx / dist, dy / dist
    s0 = p["bend_start"]
    s1 = s0 + p["bend_length"]
    if s1 > dist - p["boss_radius"] - 2:
        raise ValueError(
            f"bend ({s0:g}..{s1:g} from the key) does not fit before the axle boss "
            f"({dist - p['boss_radius']:.1f} away); reduce bend_start / bend_length or use "
            "hub_offset_mode = 'thin'"
        )
    zs, t, big = lay.zs, lay.t, 500.0
    prof = [(-big, zs), (s0, zs), (s1, 0), (big, 0), (big, t), (s1, t), (s0, zs + t), (-big, zs + t)]
    plane = cq.Plane(origin=(lay.kx, lay.ky, 0), xDir=(dx, dy, 0), normal=(dy, -dx, 0))
    joggle = cq.Workplane(plane).polyline(prof).close().extrude(big, both=True)
    lo, hi = min(zs, 0) - 1, max(zs, 0) + t + 1
    return cq.Workplane("XY").add(_prism(face, lo, hi)).intersect(joggle)


def cylinder(x, y, r, z0, z1) -> cq.Workplane:
    return cq.Workplane("XY").workplane(offset=z0).center(x, y).circle(r).extrude(z1 - z0)


def tongue_holes(body: cq.Workplane, p: dict, lay: Layout) -> cq.Workplane:
    """Raised slot key, tapped clamp-bolt holes (through) and the front adjuster hole.

    The key (as on Tange's inserts) sits in the frame plate's slot and locates the insert
    while it slides; an outer clamp plate bears on the frame around the slot.
    """
    key = (
        cq.Workplane("XY").workplane(offset=lay.zs + lay.t - 0.01)
        .center(lay.kx, lay.ky)
        .slot2D(p["key_length"], p["key_width"]).extrude(p["key_height"] + 0.01)
    )
    body = body.union(key)
    for i in range(2):
        x = p["bolt_x"] + i * p["bolt_pitch"]
        body = body.cut(cylinder(x, p["bolt_z"], p["bolt_tap_dia"] / 2, -50, 50))
    # Runs out of whatever is ahead of the tongue (e.g. a brake web), so drill long.
    adj = (
        cq.Workplane("YZ").workplane(offset=p["tongue_length"] - p["adjuster_depth"])
        .center(p["bolt_z"], lay.zs + lay.t / 2).circle(p["adjuster_tap_dia"] / 2).extrude(200)
    )
    return body.cut(adj)


def to_world(obj: cq.Workplane, lay: Layout, side: str) -> cq.Workplane:
    """Local insert frame -> world. side: 'right' (drive, -Y) or 'left' (+Y)."""
    w = obj.rotate((0, 0, 0), (1, 0, 0), 90).translate((0, -lay.y_in, 0))
    return w.mirror("XZ") if side == "left" else w


def faces_area(shape: cq.Shape, normal, tol=1e-3) -> float:
    n = cq.Vector(*normal).normalized()
    total = 0.0
    for f in shape.Faces():
        if f.geomType() != "PLANE":
            continue
        if (f.normalAt() - n).Length < tol:
            total += f.Area()
    return total


# --------------------------------------------------------------------------- #
# Right (drive side): UDH hangerless interface + thru-axle
# --------------------------------------------------------------------------- #

RIGHT_PARAMS = {
    "udh_pocket_radius": 15.5,    # R15 MIN (+ position tol 0.5): the hanger turns inside this
    "udh_thick_forward": 28.0,    # below the axle, the full-thickness (16.5) region runs this far forward
    "udh_bore_clearance": 0.05,   # 20 +0.1/0 bore -> 20.05 nominal
}


def build_right(p: dict) -> tuple[cq.Workplane, dict]:
    lay = layout(p)
    depth = UDH_RECESS_DEPTH.nominal
    total = depth + UDH_FLOOR_TO_OUTBOARD.nominal          # 16.5 inboard face -> outboard face
    a = math.radians(UDH_STOP_ANGLE.nominal)
    n = (math.cos(a), math.sin(a))
    d = UDH_STOP_OFFSET.nominal
    # Keep reliefs off the forward rotational stop: protect points just ahead of the stop line.
    m = p["relief_margin"]
    w = (-n[1], n[0])
    protect = [((lay.ax + (d + 3) * n[0] - k * w[0], lay.ay + (d + 3) * n[1] - k * w[1]), m + 3)
               for k in range(0, 32, 2)]
    face, reliefs = outline_face(p, lay, protect=protect)

    # Full thickness: the boss, plus the plate below the axle back from udh_thick_forward
    # (so the whole pocket floor has 12.5 behind it). The key region above stays thin.
    body = plate(p, lay, face)
    below = plate(p, lay, face, depth=total).intersect(
        cq.Workplane("XY").box(400, 400, 100, centered=(False, False, False))
        .translate((lay.ax + p["udh_thick_forward"] - 400, lay.ay - 400, -1))
    )
    body = body.union(below).union(cylinder(lay.ax, lay.ay, p["boss_radius"], 0, total))

    # Hanger pocket, 4 deep from the inboard face; floor is datum B. Upper edge: R15 MIN arc.
    # Below the axle it is bounded only by the forward rotational stop face (14.4 from the
    # axle, normal 30 deg above +X) and opens to the rear for >= 60 deg backward rotation.
    far = 200.0
    x0 = d / n[0]
    xb = (d + far * n[1]) / n[0]
    half = (
        cq.Workplane("XY").workplane(offset=-1)
        .polyline([(lay.ax + x0, lay.ay), (lay.ax + xb, lay.ay - far),
                   (lay.ax - far, lay.ay - far), (lay.ax - far, lay.ay)]).close()
        .extrude(depth + 1)
    )
    pocket = cylinder(lay.ax, lay.ay, p["udh_pocket_radius"], -1, depth).union(half)
    body = body.cut(pocket)
    body = body.cut(cylinder(lay.ax, lay.ay, (UDH_BORE.nominal + p["udh_bore_clearance"]) / 2,
                             -50, 50))
    body = tongue_holes(body, p, lay)

    stop_area = faces_area(body.val(), (-n[0], -n[1], 0))
    info = {
        "lay": lay,
        "total": total,
        "stop_area": stop_area,
        "reliefs": reliefs,
    }
    return body, info


# --------------------------------------------------------------------------- #
# Left (non-drive): thru-axle + brake mount
# --------------------------------------------------------------------------- #

LEFT_PARAMS = {
    "nds_thickness_D": 15.0,      # 'D' on sheet 3: hub contact face -> axle-head face (+/-0.2)
    "nds_protrusion_dia": 26.0,   # cylindrical hub-contact protrusion (sheet 1 alt. design, >= 25)
    "axle_hole_dia": 12.2,        # clearance for the 11.96 axle shank
    "brake_mount": "flat",        # "flat" | "post" | "is" | "none"
    "rotor": 160,                 # rotor diameter the mount is positioned for
    "caliper_mount_angle": None,  # deg about the axle (0 = mount line along +X, face up);
                                  # None = CALIPER_MOUNT_ANGLE for the chosen mount
    "rotor_clearance": 2.0,       # brake bosses stay this far outboard of the rotor
    "brake_boss_size": 18.0,      # boss width along the bolt line
    "brake_edge_radius": 3.0,     # rounds the post / flat-tab corners (side profile)
    "post_height": 16.0,          # post mount: boss depth below the mount face (>= 13 engagement)
    "flat_tab_thickness": 10.0,   # flat mount: tab under the mount face (bolts from below)
    "is_tab_thickness": 8.0,      # IS: ear thickness outboard of its face
    "is_ear_radius": 6.5,         # IS: ear boss radius around each hole
    "post_tap_dia": 5.0,          # M6 tapped (post mount threads in the frame)
    "flat_hole_dia": 5.5,         # M5 clearance (caliper is threaded)
    "flat_head_dia": 10.0,        # counterbore for the M5 bolt heads, below the tab
    "flat_head_clearance": 8.0,
    "is_hole_dia": 6.2,           # IS tab holes are unthreaded
}

ROTOR_THICKNESS = 1.75  # Verdone's lateral values assume 1.75 mm rotors

# Default caliper mount angles, measured off the Tange L inserts (tange-left-*.jpg, 160 rotor):
# IS ears up and behind/above the axle, flat-mount arm and post-mount flange up and forward.
CALIPER_MOUNT_ANGLE = {"flat": 55.0, "post": 38.0, "is": 51.0}


def brake_geometry(p: dict, lay: Layout):
    """Mount ordinates in the insert's local frame, or None when brake_mount == 'none'."""
    if p["brake_mount"] == "none":
        return None
    mp = dbm.mount_position(p["brake_mount"], p["rotor"])
    angle = p["caliper_mount_angle"]
    if angle is None:
        angle = CALIPER_MOUNT_ANGLE[mp.mount]
    a = math.radians(angle)
    u = (math.cos(a), math.sin(a))
    v = (-math.sin(a), math.cos(a))

    def pt(uu, vv):
        return (lay.ax + uu * u[0] + vv * v[0], lay.ay + uu * u[1] + vv * v[1])

    rotor_face = dbm.rotor_face_from_center(int(round(lay.hub_old)))
    lateral = rotor_face + dbm.SCREWS_FROM_INNER_ROTOR_FACE[mp.mount]
    return {
        "pos": mp, "u": u, "v": v, "pt": pt, "angle": angle,
        "rotor_face": rotor_face, "lateral": lateral,
        "z_lat": lateral - lay.y_in,                                  # local z of bolt plane / IS face
        "z_rotor": rotor_face + ROTOR_THICKNESS + p["rotor_clearance"] - lay.y_in,
    }


def _block(pt, u, v, u0, u1, v0, v1, z0, z1) -> cq.Workplane:
    """Box in the mount frame: u in [u0,u1], v in [v0,v1], local z in [z0,z1]."""
    c = pt((u0 + u1) / 2, (v0 + v1) / 2)
    ang = math.degrees(math.atan2(u[1], u[0]))
    return (
        cq.Workplane("XY").box(u1 - u0, v1 - v0, z1 - z0)
        .rotate((0, 0, 0), (0, 0, 1), ang)
        .translate((c[0], c[1], (z0 + z1) / 2))
    )


def _rounded(block: cq.Workplane, r: float) -> cq.Workplane:
    """Round a brake boss's corners in the side profile (edges square to the plate)."""
    return block.edges("|Z").fillet(r) if r > 0 else block


def _rod(pt, v, uu, v0, v1, z, r) -> cq.Workplane:
    """Cylinder along the mount's v axis at u = uu from v0 to v1, at local z (bolt plane)."""
    c = pt(uu, v0)
    return cq.Workplane(cq.Plane(origin=(c[0], c[1], z), xDir=(0, 0, 1),
                                 normal=(v[0], v[1], 0))).circle(r).extrude(v1 - v0)


def build_left(p: dict) -> tuple[cq.Workplane, dict]:
    lay = layout(p)
    bg = brake_geometry(p, lay)
    s = p["brake_boss_size"] / 2
    extra, protect = [], []
    if bg:
        mp, pt = bg["pos"], bg["pt"]
        m = p["relief_margin"]
        # Hull features for each boss, tagged "brake:<n>" so no relief cuts across one boss.
        # Post blocks and the flat tab: circles at their rounded corners (the outline hugs the
        # boss); IS: one circle per ear. The boss side facing the plate keeps relief_margin.
        rr = max(p["brake_edge_radius"], 0.5)
        if mp.mount == "post":
            boxes = [(b - s, b + s, mp.top - p["post_height"], mp.top) for b in (mp.bolt1, mp.bolt2)]
        elif mp.mount == "flat":
            boxes = [(mp.bolt1 - s, mp.bolt2 + s, mp.top - p["flat_tab_thickness"], mp.top)]
        else:
            boxes = []
        for n_box, (u0, u1, v0, v1) in enumerate(boxes):
            for uu in (u0 + rr, u1 - rr):
                for vv in (v0 + rr, v1 - rr):
                    # 0.3 inside the boss so plate and boss faces never coincide
                    extra.append((pt(uu, vv), rr - 0.3, f"brake:{n_box}"))
            nu = max(2, int((u1 - u0) / 2))
            protect += [(pt(u0 + (u1 - u0) * k / nu, v0), m, f"brake:{n_box}") for k in range(nu + 1)]
        if mp.mount == "is":
            for n_ear, b in enumerate((mp.bolt1, mp.bolt2)):
                extra.append((pt(b, mp.top), p["is_ear_radius"], f"brake:{n_ear}"))
                protect.append((pt(b, mp.top), p["is_ear_radius"] + m, f"brake:{n_ear}"))
    face, reliefs = outline_face(p, lay, extra=extra, protect=protect)
    body = plate(p, lay, face)

    z_out = p["nds_thickness_D"] - (lay.y_in - lay.hub_old / 2)    # outer face, local z
    body = body.union(cylinder(lay.ax, lay.ay, p["boss_radius"], 0, z_out))
    hub_z = -lay.gap                                                # hub contact face
    if lay.gap > 0:
        body = body.union(cylinder(lay.ax, lay.ay, p["nds_protrusion_dia"] / 2, hub_z, 0.1))

    if bg:
        mp, u, v, pt = bg["pos"], bg["u"], bg["v"], bg["pt"]
        b1, b2 = mp.bolt1, mp.bolt2
        if mp.mount == "post":
            z0 = max(bg["z_lat"] - s / 2, bg["z_rotor"])
            for b in (b1, b2):
                body = body.union(_rounded(_block(pt, u, v, b - s, b + s, mp.top - p["post_height"],
                                                  mp.top, z0, lay.t), p["brake_edge_radius"]))
                body = body.cut(_rod(pt, v, b, mp.top - 13.0, mp.top + 1, bg["z_lat"],
                                     p["post_tap_dia"] / 2))
        elif mp.mount == "flat":
            z0 = max(bg["z_lat"] - s / 2, bg["z_rotor"])
            body = body.union(_rounded(_block(pt, u, v, b1 - s, b2 + s,
                                              mp.top - p["flat_tab_thickness"], mp.top, z0, lay.t),
                                       p["brake_edge_radius"]))
            tab0 = mp.top - p["flat_tab_thickness"]
            for b in (b1, b2):
                # Through the tab, plus a counterbore below it for the bolt head.
                body = body.cut(_rod(pt, v, b, tab0 - 1, mp.top + 1, bg["z_lat"],
                                     p["flat_hole_dia"] / 2))
                body = body.cut(_rod(pt, v, b, tab0 - p["flat_head_clearance"], tab0,
                                     bg["z_lat"], p["flat_head_dia"] / 2))
        elif mp.mount == "is":
            z0 = bg["z_lat"]
            z1 = max(lay.t, z0 + p["is_tab_thickness"])
            for b in (b1, b2):
                c = pt(b, mp.top)
                body = body.union(cylinder(c[0], c[1], p["is_ear_radius"], z0, z1))
                body = body.cut(cylinder(c[0], c[1], p["is_hole_dia"] / 2, -50, 50))

    body = body.cut(cylinder(lay.ax, lay.ay, p["axle_hole_dia"] / 2, -50, 50))
    body = tongue_holes(body, p, lay)
    info = {
        "lay": lay, "brake": bg, "z_out": z_out, "hub_z": hub_z, "reliefs": reliefs,
    }
    return body, info


def describe(p: dict, side: str, info: dict) -> None:
    lay = info["lay"]
    span = 2 * lay.y_in
    lo, hi = udh.frame_span(lay.hub_old)[1:]
    print(f"{side}: hub OLD {lay.hub_old:g}, hub gap {lay.gap:g}/side -> insert face spacing "
          f"{span:.1f} (UDH OLD + 7 -0/+3 = {lo:g}..{hi:g}: {'OK' if lo - 1e-6 <= span <= hi + 1e-6 else 'OUT'})")
    print(f"{side}: frame seat spacing {lay.seat_span:g}, axle region {lay.step:+.2f}/side "
          f"{'outboard of' if lay.step > 0 else 'inboard of' if lay.step < 0 else 'level with'} the seat")
    print(f"{side}: insert plate {lay.t:.2f} thick, inboard face |Y| = {lay.y_in:.2f}, "
          f"frame seat |Y| = {lay.seat_y:.2f}")
    print(f"{side}: axle at X {lay.ax:+.1f} Z {lay.ay:+.1f} from nominal "
          f"(chainstay {p['axle_offset_x']:+.1f})")
    if lay.zs:
        print(f"{side}: bent plate: slider region {-lay.zs:+.2f} inboard of the axle region "
              f"(bend {p['bend_start']:g}..{p['bend_start'] + p['bend_length']:g} from the key)")
    for a, b, d, c in info.get("reliefs", []):
        print(f"{side}: relief {a}-{b}: {d:g} deep over {c:g}")
