"""Left (non-drive) sliding dropout insert: 12 mm thru-axle + choice of rear brake mount.

brake_mount: "flat" (34 mm), "post" (74 mm), "is" (IS2000, 51 mm) or "none". Mount positions
come from disc_brake_mounts.py (Verdone ordinates) for `rotor`, rotated by `brake_angle`
about the axle; lateral positions from the rotor face of the actual hub (frame_old +
hub_width_offset). Shared parameters live in _common.PARAMS. Units: mm.
"""
import _common as c
import udh_frame_spec as udh

PARAMS = {**c.PARAMS, **c.LEFT_PARAMS}


def build(**p):
    body, info = c.build_left(p)
    lay = info["lay"]
    c.describe(p, "left", info)
    D = p["nds_thickness_D"]
    l1, l1_min, l1_max = udh.axle_length(D, lay.hub_old)
    print(f"left: hub contact face |Y| {lay.hub_old / 2:.2f}, axle-head face |Y| "
          f"{lay.hub_old / 2 + D:.2f} (D = {D:g})")
    print(f"left: thru-axle L1 = D + OLD + 17 = {l1:.1f} ({l1_min:.1f}..{l1_max:.1f}), "
          f"L2 >= {udh.axle_min_unthreaded_length(D, lay.hub_old):.1f}, {udh.AXLE_THREAD}")
    bg = info["brake"]
    if bg:
        mp = bg["pos"]
        print(f"left: {mp.mount} mount for {mp.rotor:g} rotor at {bg['angle']:g} deg: "
              f"face {mp.top:.2f}, bolts {mp.bolt1:.2f} / {mp.bolt2:.2f} along the mount line")
        for name, b in (("bolt1", mp.bolt1), ("bolt2", mp.bolt2)):
            x, z = bg["pt"](b, mp.top)
            print(f"left:   {name} at X {x:+.2f} Z {z:+.2f} (world)")
        print(f"left: rotor inner face |Y| {bg['rotor_face']:.2f}, mount lateral |Y| "
              f"{bg['lateral']:.2f}")
    return c.to_world(body, lay, "left")


show_object(build(**PARAMS), name="dropout_left", options={"color": "#5b6770"})
