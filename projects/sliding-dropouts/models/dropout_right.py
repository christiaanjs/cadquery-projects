"""Right (drive side) sliding dropout insert: SRAM UDH hangerless interface + 12 mm thru-axle.

Shared parameters (hub width offset, axle X/Y offset, plate/tongue sizes) live in
_common.PARAMS; the UDH-specific ones are below. Units: mm. See _common.py for coordinates.
"""
import _common as c

PARAMS = {**c.PARAMS, **c.RIGHT_PARAMS}


def build(**p):
    body, info = c.build_right(p)
    lay = info["lay"]
    c.describe(p, "right", info)
    print(f"right: UDH pocket {c.UDH_RECESS_DEPTH.nominal:g} deep (floor = datum B at "
          f"|Y| {lay.y_in + c.UDH_RECESS_DEPTH.nominal:.2f}), outboard face at "
          f"|Y| {lay.y_in + info['total']:.2f}")
    ok = "OK" if info["stop_area"] >= 10 else "TOO SMALL"
    print(f"right: forward rotational stop face area {info['stop_area']:.1f} mm^2 "
          f"(>= 10 required) {ok}")
    return c.to_world(body, lay, "right")


show_object(build(**PARAMS), name="dropout_right", options={"color": "#5b6770"})
