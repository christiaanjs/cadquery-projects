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
The insert sits on the INBOARD face of the frame's slotted socket plate. Two M6 bolts pass
outboard -> inboard through slots in the frame plate into tapped holes in the insert's tongue,
and an M4 adjuster screw pushes on the tongue's front end. The frame plate stops ahead of the
axle boss, so the boss can be as thick as the UDH / thru-axle interface needs.

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
    "axle_offset_x": 0.0,         # axle offset from the frame's nominal position; + = rearward (longer stays)
    "axle_offset_y": 0.0,         # + = axle up
    "plate_thickness": 9.0,       # insert plate thickness at hub_width_offset = 0
    "min_plate_thickness": 4.0,   # refuse to build thinner plates
    "tongue_length": 72.0,        # nominal axle -> front end of the insert
    "tongue_height": 26.0,
    "corner_radius": 5.0,
    "boss_radius": 19.0,          # outer profile around the axle (UDH: R14.5-19)
    "bolt_x": 32.0,               # first clamp bolt, forward of nominal axle
    "bolt_pitch": 22.0,
    "bolt_tap_dia": 5.0,          # M6x1 tap drill
    "adjuster_tap_dia": 3.3,      # M4x0.7 tap drill, along X into the front end
    "adjuster_depth": 10.0,
}

FRAME_PLATE = {
    "frame_plate_thickness": 6.0,
    "frame_edge_x": 30.0,         # frame plate rear edge, forward of nominal axle
    "frame_plate_front": 95.0,
    "frame_plate_margin": 7.0,    # plate beyond the insert tongue, top and bottom
    "slot_travel": 16.0,          # slot length minus bolt dia (adjustment range)
    "slot_width": 6.4,
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


def layout(p: dict) -> Layout:
    hub_old = p["frame_old"] + p["hub_width_offset"]
    t = p["plate_thickness"] - p["hub_width_offset"] / 2
    if t < p["min_plate_thickness"]:
        raise ValueError(
            f"hub_width_offset {p['hub_width_offset']} leaves a {t:.1f} mm insert plate "
            f"(< {p['min_plate_thickness']}); increase plate_thickness"
        )
    y_in = frame_span(hub_old) / 2
    return Layout(hub_old, y_in, t, frame_span(p["frame_old"]) / 2 + p["plate_thickness"],
                  0.0 - p["axle_offset_x"], p["axle_offset_y"])


def _circle_hull(circles) -> cq.Sketch:
    # cq's hull fails on circles nested inside another; they don't change the hull anyway.
    def inside(i):
        (x, y), r = circles[i]
        return any(
            j != i and math.hypot(x - cx, y - cy) + r <= cr + 1e-3 and (r < cr or j < i)
            for j, ((cx, cy), cr) in enumerate(circles)
        )

    s = cq.Sketch()
    for (x, y), r in (c for i, c in enumerate(circles) if not inside(i)):
        s = s.arc((x, y), r, 0.0, 360.0)
    return s.hull()


def outline_circles(p: dict, lay: Layout):
    """Circles whose convex hull is the insert's plate outline (axle boss + tongue)."""
    r = p["corner_radius"]
    h = p["tongue_height"] / 2 - r
    xf = p["tongue_length"] - r
    return [
        ((lay.ax, lay.ay), p["boss_radius"]),
        ((0.0, h), r), ((0.0, -h), r),
        ((xf, h), r), ((xf, -h), r),
    ]


def plate(p: dict, lay: Layout, extra_circles=(), depth=None) -> cq.Workplane:
    """Hull outline extruded from the inboard face (local z=0) outboard."""
    sk = _circle_hull(list(outline_circles(p, lay)) + list(extra_circles))
    return cq.Workplane("XY").placeSketch(sk).extrude(depth if depth is not None else lay.t)


def cylinder(x, y, r, z0, z1) -> cq.Workplane:
    return cq.Workplane("XY").workplane(offset=z0).center(x, y).circle(r).extrude(z1 - z0)


def tongue_holes(body: cq.Workplane, p: dict, lay: Layout) -> cq.Workplane:
    """Tapped clamp-bolt holes (through) and the front adjuster hole."""
    for i in range(2):
        x = p["bolt_x"] + i * p["bolt_pitch"]
        body = body.cut(cylinder(x, 0, p["bolt_tap_dia"] / 2, -50, 50))
    # Runs out of whatever is ahead of the tongue (e.g. a brake web), so drill long.
    adj = (
        cq.Workplane("YZ").workplane(offset=p["tongue_length"] - p["adjuster_depth"])
        .center(0, lay.t / 2).circle(p["adjuster_tap_dia"] / 2).extrude(200)
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
    "udh_thick_forward": 28.0,    # full-thickness (16.5) region extends this far ahead of the axle
    "udh_bore_clearance": 0.05,   # 20 +0.1/0 bore -> 20.05 nominal
}


def build_right(p: dict) -> tuple[cq.Workplane, dict]:
    lay = layout(p)
    depth = UDH_RECESS_DEPTH.nominal
    total = depth + UDH_FLOOR_TO_OUTBOARD.nominal          # 16.5 inboard face -> outboard face
    body = plate(p, lay)
    thick = plate(p, lay, depth=total).intersect(
        cq.Workplane("XY").box(400, 400, 100, centered=(False, True, False))
        .translate((lay.ax + p["udh_thick_forward"] - 400, 0, -1))
    )
    body = body.union(thick)

    # Hanger pocket, 4 deep from the inboard face; floor is datum B. Upper edge: R15 MIN arc.
    # Below the axle it is bounded only by the forward rotational stop face (14.4 from the
    # axle, normal 30 deg above +X) and opens to the rear for >= 60 deg backward rotation.
    a = math.radians(UDH_STOP_ANGLE.nominal)
    n = (math.cos(a), math.sin(a))
    d = UDH_STOP_OFFSET.nominal
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
        "frame_edge_min": lay.ax + p["udh_thick_forward"],
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
    "brake_angle": 0.0,           # deg; rotates the mount frame about the axle, 0 = along +X
    "rotor_clearance": 2.0,       # brake bosses stay this far outboard of the rotor
    "brake_boss_size": 18.0,      # boss width along the bolt line
    "post_height": 16.0,          # post mount: boss depth below the mount face (>= 13 engagement)
    "flat_tab_thickness": 10.0,   # flat mount: tab under the mount face (bolts from below)
    "is_tab_thickness": 8.0,      # IS: tab thickness outboard of its face
    "post_tap_dia": 5.0,          # M6 tapped (post mount threads in the frame)
    "flat_hole_dia": 5.5,         # M5 clearance (caliper is threaded)
    "is_hole_dia": 6.2,           # IS tab holes are unthreaded
}

ROTOR_THICKNESS = 1.75  # Verdone's lateral values assume 1.75 mm rotors


def brake_geometry(p: dict, lay: Layout):
    """Mount ordinates in the insert's local frame, or None when brake_mount == 'none'."""
    if p["brake_mount"] == "none":
        return None
    mp = dbm.mount_position(p["brake_mount"], p["rotor"])
    a = math.radians(p["brake_angle"])
    u = (math.cos(a), math.sin(a))
    v = (-math.sin(a), math.cos(a))

    def pt(uu, vv):
        return (lay.ax + uu * u[0] + vv * v[0], lay.ay + uu * u[1] + vv * v[1])

    rotor_face = dbm.rotor_face_from_center(int(round(lay.hub_old)))
    lateral = rotor_face + dbm.SCREWS_FROM_INNER_ROTOR_FACE[mp.mount]
    return {
        "pos": mp, "u": u, "v": v, "pt": pt, "angle": p["brake_angle"],
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


def _hole_along(pt, axis, uu, vv, r, length) -> cq.Workplane:
    """Cylinder through mount point (uu, vv), axis in the local xy plane."""
    c = pt(uu, vv)
    return cq.Workplane(cq.Plane(origin=(c[0], c[1], 0), xDir=(0, 0, 1),
                                 normal=(axis[0], axis[1], 0))).circle(r).extrude(length, both=True)


def build_left(p: dict) -> tuple[cq.Workplane, dict]:
    lay = layout(p)
    bg = brake_geometry(p, lay)
    s = p["brake_boss_size"] / 2
    extra = []
    if bg:
        mp = bg["pos"]
        # Web circles stay below the mount face (the caliper / adapter sits above it).
        depth = {"post": p["post_height"], "flat": p["flat_tab_thickness"]}.get(mp.mount, 2 * s)
        r = min(s, depth / 2)
        vc = mp.top if mp.mount == "is" else mp.top - r
        for b in (mp.bolt1, mp.bolt2):
            extra.append((bg["pt"](b, vc), r))
    body = plate(p, lay, extra_circles=extra)

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
                body = body.union(_block(pt, u, v, b - s, b + s, mp.top - p["post_height"],
                                         mp.top, z0, lay.t))
                body = body.cut(_hole_along(pt, v, b, mp.top, p["post_tap_dia"] / 2, 13.0))
        elif mp.mount == "flat":
            z0 = max(bg["z_lat"] - s / 2, bg["z_rotor"])
            body = body.union(_block(pt, u, v, b1 - s, b2 + s, mp.top - p["flat_tab_thickness"],
                                     mp.top, z0, lay.t))
            for b in (b1, b2):
                body = body.cut(_hole_along(pt, v, b, mp.top, p["flat_hole_dia"] / 2, 40.0))
        elif mp.mount == "is":
            z0 = bg["z_lat"]
            z1 = max(lay.t, z0 + p["is_tab_thickness"])
            body = body.union(_block(pt, u, v, b1 - s, b2 + s, mp.top - s, mp.top + s, z0, z1))
            for b in (b1, b2):
                c = pt(b, mp.top)
                body = body.cut(cylinder(c[0], c[1], p["is_hole_dia"] / 2, -50, 50))

    body = body.cut(cylinder(lay.ax, lay.ay, p["axle_hole_dia"] / 2, -50, 50))
    body = tongue_holes(body, p, lay)
    info = {
        "lay": lay, "brake": bg, "z_out": z_out, "hub_z": hub_z,
        "frame_edge_min": lay.ax + p["boss_radius"],
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
    edge = info["frame_edge_min"] + 1.0
    flag = "" if p.get("frame_edge_x", edge) >= edge else "  ** CLASHES with frame_edge_x **"
    print(f"{side}: frame plate rear edge must be >= {edge:.1f} ahead of nominal axle{flag}")
