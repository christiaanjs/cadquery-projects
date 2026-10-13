"""Both inserts in their frame socket plates, with the thru-axle, hub and rotor for reference.

Uses the shared defaults in _common.py (PARAMS, RIGHT_PARAMS, LEFT_PARAMS, FRAME_PLATE);
edit those (or override below) to change both sides together. Units: mm.
"""
import math

import _common as c
import cadquery as cq
import udh_frame_spec as udh

PARAMS = {**c.PARAMS, **c.RIGHT_PARAMS, **c.LEFT_PARAMS, **c.FRAME_PLATE}

GHOST = {"color": "#9aa5ad", "alpha": 0.35}


def frame_plate(p, lay, side):
    """The frame's socket plate (fixed), outboard of the insert; the insert key rides in its slot.

    Cut away around the insert's axle boss over the slide travel. When the insert is bent so its
    axle region sits outboard of the seat, the plate is also cut back past the bend (over the
    whole slide travel), since that part of the insert passes through the plane of the plate.
    """
    t = p["frame_plate_thickness"]
    m = p["frame_plate_margin"]
    xc, z = p["bolt_x"] + p["bolt_pitch"] / 2, p["bolt_z"]
    slot_len = p["key_length"] + p["slot_travel"]
    plate = (cq.Workplane("XY").center(xc, z).rect(slot_len + 2 * m, p["key_width"] + 2 * m)
             .extrude(t).edges("|Z").fillet(m))
    slot = (cq.Workplane("XY").workplane(offset=-1).center(xc, z)
            .slot2D(slot_len, p["key_width"] + 0.2).extrude(t + 2))
    r = p["boss_radius"] + p["frame_boss_clearance"]
    relief = (cq.Workplane("XY").workplane(offset=-1).center(lay.ax, lay.ay)
              .slot2D(p["slot_travel"] + 2 * r, 2 * r).extrude(t + 2))
    plate = plate.cut(slot).cut(relief)
    cut = bend_cut(p, lay)
    if cut is not None:
        plate = plate.cut(cut)
    w = plate.rotate((0, 0, 0), (1, 0, 0), 90).translate((0, -lay.seat_y, 0))
    return w.mirror("XZ") if side == "left" else w


def bend_cut(p, lay):
    """Solid (in the plate's local frame) beyond the bend line, or None when nothing is raised."""
    if lay.zs >= 0:
        return None
    dx, dy = lay.ax - lay.kx, lay.ay - lay.ky
    d = math.hypot(dx, dy)
    dx, dy = dx / d, dy / d
    # The bend line moves with the insert along X: take its worst case over the slide travel.
    s_cut = p["bend_start"] - p["frame_boss_clearance"] - p["slot_travel"] / 2 * abs(dx)
    big = 500.0
    a = (lay.kx + dx * s_cut, lay.ky + dy * s_cut)
    n = (-dy, dx)
    pts = [(a[0] + n[0] * big, a[1] + n[1] * big), (a[0] - n[0] * big, a[1] - n[1] * big),
           (a[0] - n[0] * big + dx * big, a[1] - n[1] * big + dy * big),
           (a[0] + n[0] * big + dx * big, a[1] + n[1] * big + dy * big)]
    t = p["frame_plate_thickness"]
    return cq.Workplane("XY").workplane(offset=-1).polyline(pts).close().extrude(t + 2)


def axle_ref(p, lay):
    D = p["nds_thickness_D"]
    l1 = udh.axle_length(D, lay.hub_old)[0]
    y_head = lay.hub_old / 2 + D
    shank = (cq.Workplane("XZ").workplane(offset=-y_head).center(lay.ax, lay.ay)
             .circle(c.AXLE_DIA.nominal / 2).extrude(l1))
    head = (cq.Workplane("XZ").workplane(offset=-y_head - 3).center(lay.ax, lay.ay)
            .circle(12).extrude(3))
    return shank.union(head)


def hub_ref(p, lay):
    return (cq.Workplane("XZ").workplane(offset=-lay.hub_old / 2).center(lay.ax, lay.ay)
            .circle(15).extrude(lay.hub_old))


def rotor_ref(p, lay, bg):
    y0 = bg["rotor_face"]
    return (cq.Workplane("XZ").workplane(offset=-y0 - c.ROTOR_THICKNESS).center(lay.ax, lay.ay)
            .circle(p["rotor"] / 2).circle(17).extrude(c.ROTOR_THICKNESS))


def build(**p):
    right, rinfo = c.build_right(p)
    left, linfo = c.build_left(p)
    lay = rinfo["lay"]
    c.describe(p, "right", rinfo)
    c.describe(p, "left", linfo)

    parts = {
        "dropout_right": c.to_world(right, lay, "right"),
        "dropout_left": c.to_world(left, lay, "left"),
        "frame_plate_right": frame_plate(p, lay, "right"),
        "frame_plate_left": frame_plate(p, lay, "left"),
    }
    cut = bend_cut(p, lay)
    if cut is not None:
        xc, z = p["bolt_x"] + p["bolt_pitch"] / 2, p["bolt_z"]
        slot = (cq.Workplane("XY").center(xc, z).slot2D(p["key_length"] + p["slot_travel"], p["key_width"])
                .extrude(p["frame_plate_thickness"]))
        broke = sum(v.Volume() for v in slot.intersect(cut).solids().vals())
        print("frame plate: cut back past the bend" + (
            f"; it breaks into the key slot ({broke:.0f} mm^3): start the bend further from the key"
            if broke > 0.5 else " (clear of the key slot)"))
    for side in ("right", "left"):
        clash = parts[f"dropout_{side}"].intersect(parts[f"frame_plate_{side}"])
        vol = sum(v.Volume() for v in clash.solids().vals())
        print(f"{side}: insert / frame plate overlap {vol:.2f} mm^3 "
              f"({'OK' if vol < 1 else 'CLASH'}; the key is meant to sit inside the slot)")

    for name, obj in parts.items():
        show_object(obj, name=name, options=GHOST if name.startswith("frame") else
                    {"color": "#5b6770"})
    show_object(axle_ref(p, lay), name="thru_axle", options={"color": "#222222", "alpha": 0.6})
    show_object(hub_ref(p, lay), name="hub", options={"color": "#c8b07a", "alpha": 0.3})
    if linfo["brake"]:
        show_object(rotor_ref(p, lay, linfo["brake"]), name="rotor",
                    options={"color": "#b0b0b0", "alpha": 0.3})


build(**PARAMS)
