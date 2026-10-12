"""Both inserts in their frame socket plates, with the thru-axle, hub and rotor for reference.

Uses the shared defaults in _common.py (PARAMS, RIGHT_PARAMS, LEFT_PARAMS, FRAME_PLATE);
edit those (or override below) to change both sides together. Units: mm.
"""
import _common as c
import cadquery as cq
import udh_frame_spec as udh

PARAMS = {**c.PARAMS, **c.RIGHT_PARAMS, **c.LEFT_PARAMS, **c.FRAME_PLATE}

GHOST = {"color": "#9aa5ad", "alpha": 0.35}


def frame_plate(p, lay, side):
    """The frame's socket plate (fixed), outboard of the insert; the insert key rides in its slot."""
    x0, x1 = p["frame_edge_x"], p["frame_plate_front"]
    h = p["tongue_height"] / 2 + p["frame_plate_margin"]
    t = p["frame_plate_thickness"]
    plate = cq.Workplane("XY").center((x0 + x1) / 2, 0).rect(x1 - x0, 2 * h).extrude(t)
    plate = plate.edges("|Z").fillet(4)
    slot = (cq.Workplane("XY").workplane(offset=-1)
            .center(p["bolt_x"] + p["bolt_pitch"] / 2, 0)
            .slot2D(c.key_length(p) + p["slot_travel"], p["key_width"] + 0.2).extrude(t + 2))
    plate = plate.cut(slot)
    w = plate.rotate((0, 0, 0), (1, 0, 0), 90).translate((0, -lay.seat_y, 0))
    return w.mirror("XZ") if side == "left" else w

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


right, rinfo = c.build_right(PARAMS)
left, linfo = c.build_left(PARAMS)
lay = rinfo["lay"]
c.describe(PARAMS, "right", rinfo)
c.describe(PARAMS, "left", linfo)

show_object(c.to_world(right, lay, "right"), name="dropout_right", options={"color": "#5b6770"})
show_object(c.to_world(left, lay, "left"), name="dropout_left", options={"color": "#5b6770"})
show_object(frame_plate(PARAMS, lay, "right"), name="frame_plate_right", options=GHOST)
show_object(frame_plate(PARAMS, lay, "left"), name="frame_plate_left", options=GHOST)
show_object(axle_ref(PARAMS, lay), name="thru_axle", options={"color": "#222222", "alpha": 0.6})
show_object(hub_ref(PARAMS, lay), name="hub", options={"color": "#c8b07a", "alpha": 0.3})
if linfo["brake"]:
    show_object(rotor_ref(PARAMS, lay, linfo["brake"]), name="rotor",
                options={"color": "#b0b0b0", "alpha": 0.3})
