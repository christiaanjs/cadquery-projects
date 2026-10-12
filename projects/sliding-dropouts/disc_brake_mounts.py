#!/usr/bin/env python3
"""
disc_brake_mounts.py
====================

Parametric geometry for **rear (frame) bicycle disc-brake caliper mounts**:

* IS (International Standard)  - 51 mm bolt spacing
* Post mount                   - 74 mm bolt spacing
* Flat mount (rear)            - 34 mm bolt spacing

Each mount is modelled as a function of rotor diameter. Moving to a larger
rotor shifts the caliper along a radial line, so the mounting-face and
bolt-hole positions are *linear* in rotor diameter; the bolt spacing is
constant.

Coordinate convention
---------------------
Positions are ordinates in an axle-centred frame (origin = rear axle
centreline), in millimetres, as defined by Verdone's drawings [V1][V2]:

* ``top``   - ordinate of the caliper mounting face / height plane.
* ``bolt1`` - ordinate of the first bolt hole.
* ``bolt2`` - ``bolt1 + spacing`` (the second bolt hole).

The exact axis orientation is defined in Verdone's drawings [V2]. The
interpretation used here is corroborated by two independent sources:

* Shimano's rear post mount dimensions A and C [S1] correspond to ``top``
  and ``bolt1`` for post mount.
* SRAM's rear flat mount "Dimension B" [R1] (36.5 mm @ 140, 45 mm @ 160)
  corresponds to ``bolt1`` for flat mount.

The model
---------
With rotor diameter ``D``, reference diameter ``D_ref``, base distance ``L0``,
perpendicular offset ``a``, mount angle ``theta`` and sign ``s``::

    L     = L0 + (D - D_ref) / 2
    top   = L*sin(theta) + s*a*cos(theta)
    bolt1 = L*cos(theta) - s*a*sin(theta)
    bolt2 = bolt1 + spacing

with ``s = -1`` for flat mount and ``s = +1`` for post mount and IS2000.
The constants are listed in :data:`MOUNTS`.

Caveats (please read)
---------------------
* The model is Verdone's own *systemised* geometry [V1]. He states it does not
  match any single published specification exactly. Real Shimano hardware
  deviates from the linear model at 180/203 mm (see :data:`SHIMANO_POST_REAR`
  and :func:`compare_post_mount_to_shimano`). Use the lookup table if you
  must match Shimano parts exactly.
* 203 mm is treated as a true 203 mm rotor here (as in Verdone's tables).
  Verdone recommends designing around 200 mm and adapting to 203 mm with
  ~1.5 mm shim washers [V1].
* Lateral (axial) values are from Verdone [V1] and assume Centerlock hubs
  and 1.75 mm rotors; his page is internally inconsistent for 142 mm hubs
  (see :data:`ROTOR_FACE_FROM_CENTER`).
* Verify against the frame/caliper manufacturer's documentation before
  machining anything. Safety-critical part.

References
----------
[V1] Peter Verdone Designs, "Disc Brake Mounting 2026" (2026-01-19).
     http://www.peterverdone.com/disc-brake-mounting-2026/
[V2] Peter Verdone Designs, "2026-01-19 PVD Caliper Mounting Systems" (PDF
     drawings with per-rotor ordinates).
     http://www.peterverdone.com/wp-content/uploads/2026/01/2026-01-19-PVD-Caliper-Mounting-Systems.pdf
[S1] SHIMANO INC., "Disc brake" dealer standards, Ver. 1.3, 2017-10-24
     (rear post mount dimensions A-E; flat mount drawings C-078..C-084).
     https://www.peterverdone.com/wp-content/uploads/2018/06/2019-Shimano-Disc-Brake-Standards.pdf
[R1] SRAM, "MTB & Road Disc Brake Caliper Mounting Specifications",
     GEN.0000000005232 Rev V (2025): mount identification (flat 34 mm rear /
     70 mm front, post 74 mm, IS 51 mm), flat mount dimensions A/B, bolt
     thread engagement, IS/post adapter tables.
     https://www.sram.com/globalassets/document-hierarchy/frame-fit-specifications/aftermarket/disc-brake-caliper-mounting-specifications-for-road-and-mtb.pdf
[T1] TRP disc brake adapter listings (post-mount +20/+23/+40/+43 mm).
     https://www.performancebike.com/trp-a5-is-adapter-black-203mm-front-abad000132/p1365798
[B1] Bikehugger, "Road disc brake tech: flat mount vs post mount"
     (rear flat mount native to 140 mm rotor).
     https://www.bikehugger.com/posts/road-disc-brake-tech-flat-mount-vs-post-mount/
[O1] Off Course, "Disc Brake Mounts" (IS/post/flat overview; M6 vs M5).
     https://offcourse.bike/product-category/disc-brake-mounts/

Usage
-----
>>> pos = mount_position("post", 180)
>>> round(pos.top, 2), round(pos.bolt1, 2), round(pos.bolt2, 2)
(64.56, 11.8, 85.97)
>>> adapter_offset(native_rotor=160, target_rotor=180)
20
"""

from __future__ import annotations

import argparse
import math
from dataclasses import dataclass
from typing import Dict, Optional, Tuple

__all__ = [
    "MountSpec",
    "MountPosition",
    "MOUNTS",
    "SHIMANO_POST_REAR",
    "SRAM_FLAT_REAR_DIM_B",
    "ROTOR_FACE_FROM_CENTER",
    "SCREWS_FROM_INNER_ROTOR_FACE",
    "mount_position",
    "adapter_offset",
    "rotor_face_from_center",
    "compare_post_mount_to_shimano",
    "self_check",
]


# --------------------------------------------------------------------------
# Data model
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class MountSpec:
    """Constants describing one rear caliper mount standard.

    Attributes:
        key: Short identifier ("flat", "post", "is").
        name: Human-readable name.
        theta_deg: Mount-system angle in degrees [V1].
        d_ref: Reference rotor diameter (mm) at which ``l0`` applies [V1].
        l0: Radial base distance at ``d_ref`` (mm) [V1].
        a: Perpendicular offset (mm) [V1].
        sign: -1 for flat mount, +1 for post/IS (selects the rotation
            sense in the formulas; see module docstring) [V1].
        spacing: Bolt spacing used by the model (mm). Verdone uses 74.17 for
            post mount; nominal is 74 (Shimano: 74.2 [S1]).
        nominal_spacing: Nominal bolt spacing (mm) as commonly quoted
            [R1][O1].
        bolt: Typical caliper/frame bolt size, or a note.
        thread_engagement: (min, max) mm of bolt thread engagement
            recommended by SRAM [R1]; ``None`` where not specified.
        threaded_in_frame: Whether the frame holes are threaded.
        native_rotors: Rotor diameters (mm) commonly "native" to rear frames
            of this standard.
        notes: Free-text notes.
    """

    key: str
    name: str
    theta_deg: float
    d_ref: float
    l0: float
    a: float
    sign: int
    spacing: float
    nominal_spacing: float
    bolt: str
    thread_engagement: Optional[Tuple[float, float]]
    threaded_in_frame: bool
    native_rotors: Tuple[int, ...]
    notes: str = ""


@dataclass(frozen=True)
class MountPosition:
    """Computed mount geometry for one rotor size (all mm)."""

    mount: str
    rotor: float
    top: float
    bolt1: float
    bolt2: float
    spacing: float


# Constants from Verdone [V1] (formulas) and [V2] (drawings).
MOUNTS: Dict[str, MountSpec] = {
    "flat": MountSpec(
        key="flat",
        name="Flat mount (rear)",
        theta_deg=30.5,
        d_ref=140.0,
        l0=39.570,
        a=4.739,
        sign=-1,
        spacing=34.0,
        nominal_spacing=34.0,
        bolt="M5 (countersunk/low profile) [O1]",
        thread_engagement=(5.0, 7.0),  # [R1]
        threaded_in_frame=True,
        native_rotors=(140,),  # [B1][S1]
        notes="Bolts enter from below the chainstay [B1]. Front flat mount "
              "is a different standard (70 mm) [R1].",
    ),
    "post": MountSpec(
        key="post",
        name="Post mount (rear)",
        theta_deg=60.0,
        d_ref=160.0,
        l0=51.811,
        a=22.061,
        sign=+1,
        spacing=74.17,  # Verdone; Shimano quotes 74.2 +/- 0.1 [S1]
        nominal_spacing=74.0,
        bolt="M6 [O1]",
        thread_engagement=(9.0, 13.0),  # [R1]
        threaded_in_frame=True,
        native_rotors=(140, 160, 180, 200, 203),  # frame-dependent [R1]
        notes="Native size is the smallest rotor the frame was designed "
              "for [B1]; adapters add +20/+23/+40/+43 mm [T1].",
    ),
    "is": MountSpec(
        key="is",
        name="IS2000 (rear)",
        theta_deg=60.0,
        d_ref=160.0,
        l0=39.874,
        a=1.437,
        sign=+1,
        spacing=51.0,
        nominal_spacing=51.0,
        bolt="Unthreaded tab holes; bolts parallel to the axle [O1]",
        thread_engagement=None,
        threaded_in_frame=False,
        native_rotors=(140, 160),  # per SRAM IS table [R1]
        notes="Calipers do not bolt directly to IS; an IS adapter is "
              "required [R1][O1].",
    ),
}

_ALIASES = {
    "flat": "flat", "flatmount": "flat", "flat_mount": "flat", "fm": "flat",
    "post": "post", "postmount": "post", "post_mount": "post", "pm": "post",
    "is": "is", "is2000": "is", "international_standard": "is",
}


# --------------------------------------------------------------------------
# Published reference values (for lookup / validation)
# --------------------------------------------------------------------------

#: Shimano rear post mount dimensions [S1], mm, keyed by rotor diameter.
#: ``A`` = mounting-face dimension (~ ``top``), ``B`` = bolt spacing,
#: ``C`` = first-bolt dimension (~ ``bolt1``). Tolerance +/-0.1 mm.
SHIMANO_POST_REAR: Dict[int, Dict[str, float]] = {
    140: {"A": 47.5, "B": 74.2, "C": 1.7},
    160: {"A": 55.9, "B": 74.2, "C": 6.8},
    180: {"A": 64.0, "B": 74.2, "C": 12.4},
    203: {"A": 73.9, "B": 74.2, "C": 18.8},
}

#: SRAM published rear flat mount "Dimension B" [R1], mm (axle centreline to
#: bottom-slot centreline). Corresponds to ``bolt1`` for flat mount.
SRAM_FLAT_REAR_DIM_B: Dict[int, float] = {140: 36.5, 160: 45.0}

#: Rotor inner face distance from wheel centre, by hub spacing (mm) [V1].
#: NOTE: [V1] lists 53.25 for 142 mm in its list but 52.25 in its equation
#: text. 53.25 is used here; verify before relying on it.
ROTOR_FACE_FROM_CENTER: Dict[int, float] = {
    148: 55.25,
    142: 53.25,
    110: 44.50,
    100: 39.50,
}

#: Caliper screw / mounting face distance from the inner rotor face (mm)
#: [V1]. Assumes Centerlock hubs and 1.75 mm rotors.
SCREWS_FROM_INNER_ROTOR_FACE: Dict[str, float] = {
    "post": 9.55,
    "flat": 12.20,
    "is": 15.25,  # IS2000 face, rear (front is 10.50)
}


# --------------------------------------------------------------------------
# Core functions
# --------------------------------------------------------------------------

def _resolve(mount: str) -> MountSpec:
    key = _ALIASES.get(mount.strip().lower().replace("-", "_").replace(" ", "_"))
    if key is None:
        raise ValueError(
            f"Unknown mount {mount!r}; expected one of {sorted(set(_ALIASES))}"
        )
    return MOUNTS[key]


def mount_position(mount: str, rotor_mm: float) -> MountPosition:
    """Compute mounting-face and bolt positions for a rear mount and rotor.

    Args:
        mount: "flat", "post" or "is" (a few aliases accepted).
        rotor_mm: Rotor diameter in mm (e.g. 140, 160, 180, 200, 203).

    Returns:
        :class:`MountPosition` with ``top``, ``bolt1``, ``bolt2`` in mm.

    Raises:
        ValueError: on unknown mount or non-positive rotor size.

    Source: formulas from Verdone [V1]; see module docstring.
    """
    if rotor_mm <= 0:
        raise ValueError("rotor_mm must be positive")
    m = _resolve(mount)
    theta = math.radians(m.theta_deg)
    length = m.l0 + (rotor_mm - m.d_ref) / 2.0
    top = length * math.sin(theta) + m.sign * m.a * math.cos(theta)
    bolt1 = length * math.cos(theta) - m.sign * m.a * math.sin(theta)
    return MountPosition(
        mount=m.key,
        rotor=float(rotor_mm),
        top=top,
        bolt1=bolt1,
        bolt2=bolt1 + m.spacing,
        spacing=m.spacing,
    )


def adapter_offset(native_rotor: float, target_rotor: float) -> float:
    """Adapter size (mm) needed to run ``target_rotor`` on a frame whose
    native rotor size is ``native_rotor``.

    An adapter shifts the caliper outward by the difference in rotor
    diameter (e.g. 160 -> 180 needs "+20") [T1]. Going *below* the native
    size is generally not possible and raises ``ValueError``.

    Common retail increments are +20, +23, +40, +43 mm [T1]; the return
    value is the exact difference, so check it against what is sold.
    """
    diff = target_rotor - native_rotor
    if diff < 0:
        raise ValueError(
            "Target rotor is smaller than the frame's native size; "
            "adapters cannot reduce rotor size."
        )
    return int(diff) if float(diff).is_integer() else diff


def rotor_face_from_center(hub_spacing_mm: int) -> float:
    """Inner rotor face distance from wheel centre for a hub spacing [V1].

    Supported hub spacings: 148, 142, 110, 100 mm.
    """
    try:
        return ROTOR_FACE_FROM_CENTER[hub_spacing_mm]
    except KeyError:
        raise ValueError(
            f"Unsupported hub spacing {hub_spacing_mm}; "
            f"supported: {sorted(ROTOR_FACE_FROM_CENTER)}"
        ) from None


def compare_post_mount_to_shimano() -> Dict[int, Dict[str, float]]:
    """Difference (model - Shimano) for rear post mount, per rotor size.

    Returns a dict ``{rotor: {"d_top": .., "d_bolt1": .., "d_spacing": ..}}``
    in mm. Demonstrates that the idealised linear model departs from
    Shimano's published numbers at 180/203 mm [S1][V1].
    """
    out: Dict[int, Dict[str, float]] = {}
    for rotor, s in SHIMANO_POST_REAR.items():
        p = mount_position("post", rotor)
        out[rotor] = {
            "d_top": p.top - s["A"],
            "d_bolt1": p.bolt1 - s["C"],
            "d_spacing": p.spacing - s["B"],
        }
    return out


# --------------------------------------------------------------------------
# Validation against Verdone's drawing ordinates [V2]
# --------------------------------------------------------------------------

#: (top, bolt1) per rotor from the drawing tables in [V2].
_VERDONE_DRAWING: Dict[str, Dict[int, Tuple[float, float]]] = {
    "flat": {
        120: (10.92, 27.88), 140: (16.00, 36.50), 160: (21.08, 45.12),
        180: (26.15, 53.73), 200: (31.23, 62.35), 203: (31.99, 63.64),
        220: (36.30, 70.97),
    },
    "post": {
        120: (38.58, -3.20), 140: (47.24, 1.80), 160: (55.90, 6.80),
        180: (64.56, 11.80), 200: (73.22, 16.80), 203: (74.52, 17.55),
        220: (81.88, 21.80),
    },
    "is": {
        120: (17.93, 8.69), 140: (26.59, 13.69), 160: (35.25, 18.69),
        180: (43.91, 23.69), 200: (52.57, 28.69), 203: (53.87, 29.44),
        220: (61.23, 33.69),
    },
}


def self_check(tol: float = 0.011) -> None:
    """Assert the implementation reproduces published reference values.

    Checks (all raise ``AssertionError`` on mismatch):

    * Verdone's drawing ordinates for every mount/rotor [V2] (tol 0.011 mm,
      i.e. rounding to 2 d.p.).
    * SRAM flat mount Dimension B at 140/160 mm [R1] (tol 0.2 mm).
    * Shimano post-mount A/C at 140/160 mm [S1] (tol 0.3 mm). Larger
      sizes legitimately diverge; see :func:`compare_post_mount_to_shimano`.
    """
    for mount, rows in _VERDONE_DRAWING.items():
        for rotor, (top, bolt1) in rows.items():
            p = mount_position(mount, rotor)
            assert abs(p.top - top) <= tol, (mount, rotor, "top", p.top, top)
            assert abs(p.bolt1 - bolt1) <= tol, (mount, rotor, "bolt1", p.bolt1, bolt1)
    for rotor, b in SRAM_FLAT_REAR_DIM_B.items():
        assert abs(mount_position("flat", rotor).bolt1 - b) <= 0.2, rotor
    for rotor in (140, 160):
        s = SHIMANO_POST_REAR[rotor]
        p = mount_position("post", rotor)
        assert abs(p.top - s["A"]) <= 0.3, rotor
        assert abs(p.bolt1 - s["C"]) <= 0.3, rotor


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def _print_table(rotors) -> None:
    hdr = f"{'rotor':>5} | " + " | ".join(
        f"{k + ' top':>9} {k + ' b1':>8} {k + ' b2':>8}" for k in MOUNTS
    )
    print(hdr)
    print("-" * len(hdr))
    for r in rotors:
        cells = []
        for k in MOUNTS:
            p = mount_position(k, r)
            cells.append(f"{p.top:9.2f} {p.bolt1:8.2f} {p.bolt2:8.2f}")
        print(f"{r:>5} | " + " | ".join(cells))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Parametric rear disc brake caliper mount geometry "
                    "(IS 51 / post 74 / flat 34 mm)."
    )
    ap.add_argument("--mount", choices=sorted(MOUNTS),
                    help="print a single mount (default: table of all)")
    ap.add_argument("--rotor", type=float, nargs="*",
                    default=[140, 160, 180, 200, 203],
                    help="rotor diameters in mm")
    ap.add_argument("--check", action="store_true",
                    help="run self-check against published values")
    args = ap.parse_args(argv)

    if args.check:
        self_check()
        print("self_check OK")
    if args.mount:
        for r in args.rotor:
            p = mount_position(args.mount, r)
            print(f"{p.mount} rotor={r:g}  top={p.top:.3f}  "
                  f"bolt1={p.bolt1:.3f}  bolt2={p.bolt2:.3f}")
    else:
        _print_table(args.rotor)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
