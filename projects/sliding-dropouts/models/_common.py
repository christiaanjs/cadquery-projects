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

Hub width offset: the frame's plate seats are fixed, so a wider hub is taken up by a thinner
insert plate (each side loses hub_width_offset / 2), with the spec interface faces moving out.

Specs used (project root): ``udh_frame_spec.py`` (SRAM UDH frame spec 90-7518-190-000 H.14,
see ``udh-spec.pdf``) and ``disc_brake_mounts.py`` (Verdone rear caliper mount ordinates).
"""

from __future__ import annotations

import math
import sys
from dataclasses import dataclass
from pathlib import Path

import cadquery as cq

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import disc_brake_mounts as dbm  # noqa: E402
import udh_frame_spec as udh  # noqa: E402

# Parameters shared by both inserts (and the assembly).
PARAMS = {
    "frame_old": 142,             # hub OLD the frame's dropout seats were built for (142/148/157)
    "hub_width_offset": 0.0,      # extra hub OLD to adapt to, total (e.g. 6 for a 142 frame -> 148 hub)
    "axle_offset_x": 32.0,        # axle offset from the frame's nominal position; + = rearward (longer stays)
    "axle_offset_y": 32.0,        # + = axle up
    "plate_thickness": 9.0,       # insert plate thickness
    "min_plate_thickness": 4.0,   # refuse to build thinner plates (hub_offset_mode "thin")
    "hub_offset_mode": "bend",    # "bend": full-thickness plate, axle region joggled outboard by
                                  #   hub_width_offset / 2; "thin": whole plate thinner instead
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
    # Reliefs: concave cut-outs in the outline between features (max depth in mm, 0 = off).
    # Each is reduced automatically to keep relief_margin from the boss, key, brake bosses etc.
    "relief_brake_posts": 10.0,   # between the two brake bosses
    "relief_brake_axle": 10.0,    # between the brake mount and the axle boss
    "relief_axle_slider": 8.0,    # between the axle boss and the slider (key) region
    "relief_slider_brake": 0.0,   # between the slider region and the brake mount
    "relief_margin": 4.0,         # material kept around protected features
    "relief_round": 3.0,          # fillet where a relief meets the straight edge
    "relief_min_chord": 15.0,     # skip reliefs shorter than this (they read as notches)
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


def frame_span(old: float) -> float:
    """Inboard face to inboard face, OLD + 7 (sheet 3)."""
    return udh.frame_span(old)[0]


@dataclass
class Layout:
    hub_old: float
    y_in: float          # |world Y| of the insert inboard face
    t: float             # insert plate thickness
    seat_y: float        # |world Y| of the frame plate's inboard face (= insert outboard face)
    ax: float            # axle centre, local x
    ay: float            # axle centre, local y (world Z)
    zs: float = 0.0      # local z shift of the slider (key) region; non-zero when bent
    kx: float = 0.0      # key centre, local x / y
    ky: float = 0.0


def layout(p: dict) -> Layout:
    """Insert placement. Local z = 0 is the hub's inboard face, (OLD + 7) / 2 from centre.

    The frame's plate seat is fixed by frame_old. A hub_width_offset moves the hub faces out
    by offset / 2 per side; "bend" keeps the plate thickness and joggles the slider region
    back inboard onto the seat (zs = -offset / 2), "thin" thins the whole plate instead.
    """
    off = p["hub_width_offset"]
    hub_old = p["frame_old"] + off
    t, zs = p["plate_thickness"], 0.0
    if p["hub_offset_mode"] == "thin":
        t -= off / 2
        if t < p["min_plate_thickness"]:
            raise ValueError(
                f"hub_width_offset {off} leaves a {t:.1f} mm insert plate "
                f"(< {p['min_plate_thickness']}); increase plate_thickness or use 'bend'"
            )
    elif p["hub_offset_mode"] == "bend":
        zs = -off / 2
    else:
        raise ValueError(f"hub_offset_mode must be 'bend' or 'thin', not {p['hub_offset_mode']!r}")
    y_in = frame_span(hub_old) / 2
    return Layout(hub_old, y_in, t, frame_span(p["frame_old"]) / 2 + p["plate_thickness"],
                  0.0 - p["axle_offset_x"], p["axle_offset_y"], zs,
                  p["bolt_x"] + p["bolt_pitch"] / 2, p["bolt_z"])


def _circle_hull(circles, n: int = 720):
    """Convex hull of circles as a closed wire: exact arcs joined by tangent lines.

    Returns (wire, lines) with lines = [(i, j, start, end)]: each straight hull edge, running
    counter-clockwise from circle i to circle j.

    cq.Sketch.hull() fails on some layouts (e.g. post/IS webs with a large axle offset), so
    hull points sampled on each circle, then rebuild every run of points from one circle as an
    arc of that exact circle. Exact arcs matter: the boss cylinder is unioned on top and
    near-coincident faces break later booleans.
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
        (x, y), r = circles[hull[0][2]]
        return cq.Wire.makeCircle(r, cq.Vector(x, y, 0), cq.Vector(0, 0, 1)), []
    # Start at a change of circle so no run wraps around the end of the list.
    start = next(j for j in range(len(hull)) if hull[j][2] != hull[j - 1][2])
    hull = hull[start:] + hull[:start]
    runs = []
    for q in hull:
        if runs and runs[-1][0][2] == q[2]:
            runs[-1].append(q)
        else:
            runs.append([q])

    # Each run -> an exact arc (or a single point when it is too short to matter).
    pieces = []
    for run in runs:
        (x, y), r = circles[run[0][2]]
        if len(run) >= 3:
            a0 = 360.0 * run[0][3] / n
            a1 = 360.0 * run[-1][3] / n
            if a1 <= a0:
                a1 += 360.0
            arc = cq.Edge.makeCircle(r, cq.Vector(x, y, 0), cq.Vector(0, 0, 1), a0, a1)
            pieces.append((arc, arc.startPoint(), arc.endPoint(), run[0][2]))
        else:
            v = cq.Vector(run[0][0], run[0][1], 0)
            pieces.append((None, v, v, run[0][2]))
    edges, lines = [], []
    for j, (arc, _, end, i) in enumerate(pieces):
        if arc is not None:
            edges.append(arc)
        _, nxt, _, k = pieces[(j + 1) % len(pieces)]
        if (nxt - end).Length > 1e-9:
            edges.append(cq.Edge.makeLine(end, nxt))
            lines.append((i, k, end, nxt))
    return cq.Wire.assembleEdges(edges), lines


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
    frozenset({"brake"}): "relief_brake_posts",
    frozenset({"brake", "axle"}): "relief_brake_axle",
    frozenset({"axle", "slider"}): "relief_axle_slider",
    frozenset({"slider", "brake"}): "relief_slider_brake",
}


def protected_circles(p: dict, lay: Layout):
    """Features reliefs must keep relief_margin away from: boss, key (+ slide), adjuster."""
    m = p["relief_margin"]
    out = [((lay.ax, lay.ay), p["boss_radius"] + 0.5)]   # the boss is an edge end: don't cut it
    half = (p["key_length"] - p["key_width"]) / 2
    for k in range(11):
        out.append(((lay.kx - half + 2 * half * k / 10, lay.ky), p["key_width"] / 2 + m))
    x0 = p["tongue_length"] - p["adjuster_depth"]
    out += [((x0 + i, lay.ky), p["adjuster_tap_dia"] / 2 + m) for i in range(0, 11, 2)]
    return out


def outline_face(p: dict, lay: Layout, extra=(), protect=()):
    """Plate outline: convex hull of the feature circles minus concave reliefs.

    Each straight hull edge between two features gets a circular relief, centred on the edge,
    up to the matching relief_* depth. The largest (chord x depth) cut that clears every
    protected circle is used; its sharp ends are filleted with relief_round. Returns
    (face, reliefs) with reliefs = [(role_a, role_b, depth, chord)].
    """
    circles = list(outline_circles(p, lay)) + list(extra)
    wire, lines = _circle_hull([(c, r) for c, r, _ in circles])
    hull_face = cq.Face.makeFromWires(wire)
    guard = list(protected_circles(p, lay)) + list(protect)
    m = p["relief_margin"]
    cuts, corners, reliefs = [], [], []
    for i, j, a, b in lines:
        key = RELIEF_PAIRS.get(frozenset({circles[i][2], circles[j][2]}))
        want = p.get(key, 0.0) if key else 0.0
        edge = b - a
        length = edge.Length
        if want <= 0 or length - 2 * m < 6:
            continue
        u = edge / length
        n_out = cq.Vector(u.y, -u.x, 0)        # hull is counter-clockwise: outward is right
        mid = (a + b) * 0.5
        # Endpoint features only need to stay uncut; everything else keeps the margin.
        ends = [(circles[k][0], circles[k][1] + 0.5) for k in (i, j)]

        def clear(c, d, mid=mid, n_out=n_out, ends=ends):
            r = (c * c / 4 + d * d) / (2 * d)
            ctr = mid + n_out * (r - d)
            ok = all(math.hypot(ctr.x - gx, ctr.y - gy) >= r + gr for (gx, gy), gr in guard + ends)
            return ok, ctr, r

        best = None
        c = length - 2 * m                     # chord of the cut along the edge
        while c >= max(6.0, p["relief_min_chord"]):
            d = min(want, 0.3 * c)             # gentle curves only (sag <= 0.3 x chord)
            while d >= 1.0:
                ok, ctr, r = clear(c, d)
                if ok:
                    if best is None or c * d > best[0]:
                        best = (c * d, c, d, ctr, r)
                    break
                d -= 0.5
            c -= 2.0
        if best is None:
            continue
        _, c, d, ctr, r = best
        cuts.append((ctr, r))
        corners += [mid - u * (c / 2), mid + u * (c / 2)]
        reliefs.append((circles[i][2], circles[j][2], round(d, 2), round(c, 1)))
    if not cuts:
        return hull_face, reliefs
    sk = cq.Sketch().face(hull_face)
    for ctr, r in cuts:
        sk = sk.push([(ctr.x, ctr.y)]).circle(r, mode="s").reset()
    face = max(sk._faces.Faces(), key=lambda f: f.Area())
    # Round each relief corner; fall back to a smaller radius (then none) where it won't fit.
    for pt in corners:
        v = min(face.Vertices(), key=lambda x: (x.Center() - pt).Length)
        if (v.Center() - pt).Length > 0.05:
            continue
        for rr in (p["relief_round"], p["relief_round"] / 2):
            if rr <= 0:
                break
            try:
                face = face.fillet2D(rr, [v])
                break
            except Exception:
                continue
    return face, reliefs


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
        # Web circles stay below the mount face (the caliper / adapter sits above it).
        depth = {"post": p["post_height"], "flat": p["flat_tab_thickness"]}.get(mp.mount, 2 * s)
        r = p["is_ear_radius"] if mp.mount == "is" else min(s, depth / 2)
        vc = mp.top if mp.mount == "is" else mp.top - r
        for b in (mp.bolt1, mp.bolt2):
            extra.append((pt(b, vc), r, "brake"))
            if mp.mount == "is":
                protect.append((pt(b, vc), r + m))           # ears: keep a ring around the hole
        # Boss footprints (post blocks / flat tab), sampled along their outlines.
        if mp.mount == "post":
            boxes = [(b - s, b + s, mp.top - p["post_height"], mp.top) for b in (mp.bolt1, mp.bolt2)]
        elif mp.mount == "flat":
            boxes = [(mp.bolt1 - s, mp.bolt2 + s, mp.top - p["flat_tab_thickness"], mp.top)]
        else:
            boxes = []
        for u0, u1, v0, v1 in boxes:
            nu, nv = max(2, int((u1 - u0) / 2)), max(2, int((v1 - v0) / 2))
            for k in range(nu + 1):
                for vv in (v0, v1):
                    protect.append((pt(u0 + (u1 - u0) * k / nu, vv), m))
            for k in range(nv + 1):
                for uu in (u0, u1):
                    protect.append((pt(uu, v0 + (v1 - v0) * k / nv), m))
    face, reliefs = outline_face(p, lay, extra=extra, protect=protect)
    body = plate(p, lay, face)

    z_out = p["nds_thickness_D"] - (lay.y_in - lay.hub_old / 2)    # outer face, local z
    body = body.union(cylinder(lay.ax, lay.ay, p["boss_radius"], 0, z_out))
    hub_z = lay.hub_old / 2 - lay.y_in                              # hub contact face (-3.5)
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
    print(f"{side}: hub OLD {lay.hub_old:g} on a {p['frame_old']:g} frame "
          f"(offset {p['hub_width_offset']:+g}); frame span OLD+7 = {2 * lay.y_in:.1f}")
    print(f"{side}: insert plate {lay.t:.2f} thick, inboard face |Y| = {lay.y_in:.2f}, "
          f"frame seat |Y| = {lay.seat_y:.2f}")
    print(f"{side}: axle at X {lay.ax:+.1f} Z {lay.ay:+.1f} from nominal "
          f"(chainstay {p['axle_offset_x']:+.1f})")
    if lay.zs:
        print(f"{side}: bent plate: slider region {-lay.zs:+.2f} inboard of the axle region "
              f"(bend {p['bend_start']:g}..{p['bend_start'] + p['bend_length']:g} from the key)")
    for a, b, d, c in info.get("reliefs", []):
        print(f"{side}: relief {a}-{b}: {d:g} deep over {c:g}")
