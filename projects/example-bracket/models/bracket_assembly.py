"""Bracket with two screws, to show multi-part models. Units: mm."""
import cadquery as cq
from bracket import PARAMS as BRACKET
from bracket import build as build_bracket

show_object(build_bracket(**BRACKET), name="bracket", options={"color": "#8a9ba8"})
for i, y in enumerate((-BRACKET["base_w"] / 4, BRACKET["base_w"] / 4)):
    screw = (
        cq.Workplane("XY").circle(2.5).extrude(12).faces(">Z").workplane().circle(4.5).extrude(3)
        .translate((8, y, BRACKET["thickness"] - 12 + 3 + 0.0))
    )
    show_object(screw, name=f"screw_{i}", options={"color": "#333333"})
