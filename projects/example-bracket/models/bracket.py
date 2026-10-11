"""L-bracket with slotted base holes. Units: mm."""
import cadquery as cq

PARAMS = {
    "base_len": 60,
    "base_w": 30,
    "height": 40,
    "thickness": 4,
    "slot_len": 12,
    "slot_w": 5.5,
    "hole_dia": 6,
    "fillet": 3,
}


def build(base_len, base_w, height, thickness, slot_len, slot_w, hole_dia, fillet):
    base = cq.Workplane("XY").box(base_len, base_w, thickness, centered=(True, True, False))
    upright = (
        cq.Workplane("XY")
        .box(thickness, base_w, height, centered=(False, True, False))
        .translate((-base_len / 2, 0, 0))
    )
    body = base.union(upright)
    body = body.edges("|Y").edges(cq.selectors.BoxSelector(
        (-base_len / 2 + thickness - 0.1, -base_w, thickness - 0.1),
        (-base_len / 2 + thickness + 0.1, base_w, thickness + 0.1))).fillet(fillet)
    body = (
        body.faces(">Z[-2]").workplane(origin=(0, 0, thickness))
        .pushPoints([(8, -base_w / 4), (8, base_w / 4)])
        .slot2D(slot_len, slot_w, 0)
        .cutThruAll()
    )
    hole = (
        cq.Workplane("YZ").workplane(offset=-base_len / 2 - 1)
        .center(0, height * 0.65).circle(hole_dia / 2).extrude(thickness + 2)
    )
    return body.cut(hole)


result = build(**PARAMS)
