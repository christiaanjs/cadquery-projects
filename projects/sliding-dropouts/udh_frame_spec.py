"""
SRAM UDH & Full Mount RD frame spec, transcribed to Python.

Source drawing : 90-7518-190-000, version H.14 ("UDH&FULL_MOUNT_RD_FRAME_SPEC"),
                 8 sheets, A2, released. Third-angle projection, all dims in mm,
                 GD&T per ASME Y14.5-2009.
Companion CAD  : UDH&FULL_MOUNT_RD_3D_MODELS_REV_H.stp (clearance models; see MODELS)

NOTES
-----
* The drawing is marked SRAM-proprietary and UDH use requires a (free) licence from
  SRAM (license@sram.com). Treat this file as personal working notes. It is NOT a
  substitute for the drawing, and the 3D clearance models are the real acceptance test.
* Every value carries a `confidence`:
    "high"   - value and feature are both explicit in the drawing text/callout
    "medium" - value is exact, but I mapped it to a feature by reading the drawing
    "low"    - value is exact, but which feature it controls is a best guess
  Check "medium"/"low" items against the PDF before using them for a design.
* Dim kinds:
    "pm"    nominal with +plus/-minus tolerance (plus/minus given as magnitudes)
    "min"   minimum allowed          "max"  maximum allowed
    "range" lo..hi allowed           "ref"  reference only (parenthesised on drawing)
    "basic" boxed basic dimension    "info" informational, not a pass/fail limit
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

DRAWING_NUMBER = "90-7518-190-000"
DRAWING_REV = "H.14"

# --------------------------------------------------------------------------- #
# Dimension container
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Dim:
    name: str
    nominal: Optional[float]
    kind: str = "pm"                 # pm | min | max | range | ref | basic | info
    plus: float = 0.0                # tolerance magnitudes (kind == "pm")
    minus: float = 0.0
    hi: Optional[float] = None       # kind == "range"
    unit: str = "mm"                 # "mm", "deg", "mm2"
    sheet: int = 0
    confidence: str = "high"
    note: str = ""

    @property
    def lo_limit(self) -> Optional[float]:
        if self.kind == "pm":
            return self.nominal - self.minus
        if self.kind in ("min", "range"):
            return self.nominal
        return None

    @property
    def hi_limit(self) -> Optional[float]:
        if self.kind == "pm":
            return self.nominal + self.plus
        if self.kind == "max":
            return self.nominal
        if self.kind == "range":
            return self.hi
        return None

    def check(self, value: float) -> bool:
        """True if `value` is within this dimension's limits (ref/basic/info always True)."""
        lo, hi = self.lo_limit, self.hi_limit
        return (lo is None or value >= lo) and (hi is None or value <= hi)

    def __str__(self) -> str:
        u = {"mm": "mm", "deg": "deg", "mm2": "mm^2"}.get(self.unit, self.unit)
        if self.nominal is None:
            t = "(nominal set by your design)"
            if self.kind == "info":
                t += f" +/-{AXLE_D_TOLERANCE} mm" if self.name == "dropout_thickness_D" else ""
            return f"{self.name}: {t}  [sheet {self.sheet}, {self.confidence}]"
        if self.kind == "pm":
            if self.plus == self.minus:
                t = f"{self.nominal} +/-{self.plus} {u}"
            else:
                t = f"{self.nominal} +{self.plus}/-{self.minus} {u}"
        elif self.kind == "min":
            t = f">= {self.nominal} {u}"
        elif self.kind == "max":
            t = f"<= {self.nominal} {u}"
        elif self.kind == "range":
            t = f"{self.nominal}..{self.hi} {u}"
        elif self.kind == "ref":
            t = f"({self.nominal}) {u} ref"
        elif self.kind == "basic":
            t = f"[{self.nominal}] {u} basic"
        else:
            t = f"{self.nominal} {u}"
        return f"{self.name}: {t}  [sheet {self.sheet}, {self.confidence}]"


def _d(name, nominal, kind="pm", plus=0.0, minus=0.0, **kw) -> Dim:
    return Dim(name, nominal, kind, plus, minus, **kw)


# --------------------------------------------------------------------------- #
# General (untoleranced) tolerances - sheet 1 title block
# --------------------------------------------------------------------------- #

GENERAL_LENGTH_TOLERANCE = [  # (over_mm, up_to_mm, +/- mm)
    (0.5, 6, 0.1),
    (6, 30, 0.2),
    (30, 120, 0.3),
    (120, 400, 0.5),
]
GENERAL_ANGLE_TOLERANCE_DEG = 2.0


def general_tolerance(length_mm: float) -> float:
    """+/- tolerance for an untoleranced length dimension."""
    for lo, hi, tol in GENERAL_LENGTH_TOLERANCE:
        if lo <= length_mm <= hi:
            return tol
    raise ValueError(f"{length_mm} mm is outside the general tolerance table (0.5-400 mm)")


# --------------------------------------------------------------------------- #
# Frame-side hangerless interface (dropout)  - sheets 1, 2
# --------------------------------------------------------------------------- #

DROPOUT = {
    d.name: d
    for d in [
        # --- Section Z-Z ---------------------------------------------------- #
        _d("hanger_bore_dia", 20.0, plus=0.1, minus=0.0, sheet=2, confidence="medium",
           note="Bore in the dropout boss that the hanger's sleeve (19.9 +/-0.1) enters."),
        _d("hanger_recess_depth", 4.0, plus=0.5, minus=0.2, sheet=2, confidence="medium",
           note="Outboard recess/step the hanger flange sits in; its floor is datum B."),
        _d("recess_floor_to_inboard_face", 12.5, plus=0.2, minus=0.2, sheet=2,
           confidence="medium",
           note="From recess floor (datum B) to inboard dropout face; parallel 0.2 to B."),
        _d("edge_radius_max", 1.0, kind="max", sheet=2,
           note="'R1 MAX' on both recess edges."),
        _d("edge_break_recess", 0.5, kind="range", hi=1.0, sheet=2, confidence="medium",
           note="'0.5-1.0 (BROKEN EDGE)'."),
        _d("edge_break_bore_inboard", 0.0, kind="range", hi=0.5, sheet=2,
           confidence="medium", note="'0-0.5 (BROKEN EDGE)' at the inboard end of the bore."),
        # --- Section Y-Y ---------------------------------------------------- #
        _d("contact_face_dia_min", 28.0, kind="min", sheet=1,
           note="Flat contact area, concentric to the axle hole, FREE OF PAINT. "
                "Mates with the hanger's 28 +/-0.1 flange."),
        _d("contact_face_dia_min_alt_protrusion", 25.0, kind="min", sheet=1,
           note="Alternative design with a cylindrical protrusion: min dia 25 flat contact "
                "area, concentric to axle hole, free of paint."),
        _d("boss_inner_radius_min", 15.0, kind="min", sheet=2, confidence="medium",
           note="'R15 MIN' with position tolerance dia 0.5 to datum A (axle axis)."),
        _d("boss_outer_radius", 14.5, kind="range", hi=19.0, sheet=2, confidence="medium",
           note="'R14.5-19.0' outer profile around the axle hole."),
        _d("stop_face_offset", 14.4, plus=0.1, minus=0.1, sheet=2, confidence="medium",
           note="Axle axis to the flat stop face; face parallel 0.2 to A. "
                "Matches the hanger's 14.4 +/-0.1."),
        _d("stop_face_angle", 30.0, plus=3.0, minus=3.0, unit="deg", sheet=2,
           confidence="medium", note="Hanger counterpart is 30 +/-2 deg."),
        _d("backward_clearance_angle_min", 60.0, kind="min", unit="deg", sheet=2,
           note="'60 deg MIN BACKWARD ROTATIONAL CLEARANCE' (hanger rotates back on impact)."),
        _d("frame_opening_angle", 85.0, plus=5.0, minus=10.0, unit="deg", sheet=2,
           confidence="low", note="85 +5/-10 deg angular dimension on the Y-Y view."),
        _d("pin_dia", 8.0, kind="ref", sheet=2, confidence="medium",
           note="(dia 8) cylinder shown beside the stop; reference only."),
        _d("pin_offset", 22.17, kind="ref", sheet=2, confidence="low",
           note="(22.17) reference dimension near the pin."),
        _d("stop_window_a", 11.0, kind="info", sheet=2, confidence="low",
           note="Detail A shows two offsets, 11 and 16, bracketing the forward-stop contact."),
        _d("stop_window_b", 16.0, kind="info", sheet=2, confidence="low"),
        _d("forward_stop_contact_area_min", 10.0, kind="min", unit="mm2", sheet=2,
           note="Forward rotational stop: minimum contact area."),
    ]
}

# Qualitative frame requirements (sheet 2)
DROPOUT_RULES = [
    "Forward rotational stop required: >= 10 mm^2 contact area (sheet 2, Detail A).",
    "Backward rotational stop: any protrusion, at the frame designer's discretion (sheet 2).",
    "There must be one element that defines the angular position of the UDH when mounted.",
    "Contact faces concentric to the axle hole must be flat and free of paint.",
    "Hangerless interface must clear reference model 90-7518-190-070 Rev H (3D check).",
]

# Geometric tolerances read from the drawing (feature -> frame)
GDT = [
    ("recess floor (datum B)", "perpendicularity", 0.2, "A", 2),
    ("inboard face", "parallelism", 0.2, "B", 2),
    ("stop face", "parallelism", 0.2, "A", 2),
    ("R15 MIN profile", "position (dia)", 0.5, "A", 2),
    ("dropout face (sheet 1 axle view)", "parallelism", 0.2, "B", 1),
    ("dropout face (sheet 1 axle view)", "perpendicularity", 0.2, "A", 1),
]

# Clearance reference values on sheet 1 (all reference-only unless noted)
CLEARANCE_REFERENCE = {
    "upper_pulley_space_height": _d("upper_pulley_space_height", 58.0, kind="ref", sheet=1,
                                    confidence="medium"),
    "upper_pulley_space_radius": _d("upper_pulley_space_radius", 34.0, kind="ref", sheet=1,
                                    confidence="medium", note="(R34)"),
    "upper_pulley_space_width": _d("upper_pulley_space_width", 46.3, kind="ref", sheet=1,
                                   confidence="medium"),
    "section_xx_ref": _d("section_xx_ref", 10.0, kind="ref", sheet=1, confidence="low"),
    "chain_shift_gap": _d("chain_shift_gap", 1.5, kind="info", sheet=1, confidence="low",
                          note="Next to 'space needed for chain to shift from smallest cog'."),
    "hub_endcap_clearance": _d("hub_endcap_clearance", 7.0, kind="basic", sheet=1,
                               confidence="low", note="Boxed 7 by the hub end cap, flagged KC."),
}

# --------------------------------------------------------------------------- #
# Thru-axle and frame width  - sheet 3  (142 / 148 / 157 mm OLD systems)
# --------------------------------------------------------------------------- #

SUPPORTED_OLD_MM = (142, 148, 157)

AXLE = {
    d.name: d
    for d in [
        _d("shank_dia", 11.96, plus=0.0, minus=0.07, sheet=3, note="Straightness dia 0.1 at MMC."),
        _d("valid_thread_length_min", 12.7, kind="min", sheet=3, note="M12x1.0-6g."),
        _d("dropout_thickness_D", None, kind="info", sheet=3, confidence="medium",
           note="Symbol D, +/-0.2, drawn on the axle-head (non-drive) dropout. "
                "Nominal comes from your frame design."),
    ]
}
AXLE_THREAD = "M12x1.0-6g"        # axle (external)
HANGER_THREAD = "M12x1.0-6H"      # hanger (internal), sheet 8
AXLE_D_TOLERANCE = 0.2            # D +/- 0.2

# "FRAME ONLY: OLD+7, -0/+3": span drawn between the dropouts (sheet 3).
FRAME_SPAN_OFFSET_MM = 7.0
FRAME_SPAN_TOL = (0.0, 3.0)       # (-, +)


def axle_length(D: float, OLD: float) -> tuple[float, float, float]:
    """L1 = D + OLD + 17 (+0.1/-1). Returns (nominal, min, max)."""
    nom = D + OLD + 17.0
    return nom, nom - 1.0, nom + 0.1


def axle_min_unthreaded_length(D: float, OLD: float) -> float:
    """L2 = D + OLD + 2 (minimum)."""
    return D + OLD + 2.0


def frame_span(OLD: float) -> tuple[float, float, float]:
    """Frame-only span OLD + 7 (-0/+3). Returns (nominal, min, max)."""
    nom = OLD + FRAME_SPAN_OFFSET_MM
    return nom, nom - FRAME_SPAN_TOL[0], nom + FRAME_SPAN_TOL[1]


# --------------------------------------------------------------------------- #
# UDH hanger itself  - sheet 8 (what the frame interface must accept)
# --------------------------------------------------------------------------- #

HANGER = {
    d.name: d
    for d in [
        _d("flange_dia", 28.0, plus=0.1, minus=0.1, sheet=8),
        _d("sleeve_dia", 19.9, plus=0.1, minus=0.1, sheet=8,
           note="Enters the frame's 20 +0.1/0 bore."),
        _d("dia_25", 25.0, kind="ref", sheet=8, confidence="medium"),
        _d("dia_26", 26.0, kind="ref", sheet=8, confidence="medium"),
        _d("section_3_5", 3.5, plus=0.1, minus=0.1, sheet=8, confidence="medium"),
        _d("section_5", 5.0, plus=0.1, minus=0.1, sheet=8, confidence="medium"),
        _d("section_7", 7.0, plus=0.15, minus=0.15, sheet=8, confidence="medium"),
        _d("section_8", 8.0, plus=0.2, minus=0.2, sheet=8, confidence="medium"),
        _d("stackup_frame_washer_bolt", 5.7, plus=0.4, minus=0.4, sheet=8, confidence="medium",
           note="Labelled 'FRAME WIDTH / WASHER / BOLT / TOLERANCE STACK UP'."),
        _d("side_30", 30.0, plus=0.2, minus=0.2, sheet=8, confidence="low"),
        _d("side_8", 8.0, plus=0.2, minus=0.2, sheet=8, confidence="low"),
        _d("stop_face_offset", 14.4, plus=0.1, minus=0.1, sheet=8, confidence="medium"),
        _d("stop_face_angle", 30.0, plus=2.0, minus=2.0, unit="deg", sheet=8, confidence="medium"),
        _d("basic_angle", 15.42, kind="basic", unit="deg", sheet=8, confidence="low"),
        _d("basic_89_9", 89.9, kind="basic", unit="deg", sheet=8, confidence="low",
           note="Boxed 89.9, units not stated; probably degrees."),
    ]
}

# --------------------------------------------------------------------------- #
# Cable routing - sheet 4
# --------------------------------------------------------------------------- #

# Minimum distance (mm) from axle to the housing exit point, by exit location.
CABLE_EXIT_MIN_MM = {
    "top_of_seat_stay":        {"preferred": True,  "min_mm": 60},
    "top_of_chain_stay":       {"preferred": True,  "min_mm": 100},
    "bottom_of_chain_stay":    {"preferred": False, "min_mm": 100},
    "inside_of_chain_stay":    {"preferred": False, "min_mm": 150},
}

CABLE_SPEC = {
    "axs_extension_cord_test_cylinder_dia_mm": 5.8,    # cylinder must pass through
    "axs_extension_cord_test_cylinder_len_mm": 19.0,   # the internal routing path
    "cable_dia_mm": 1.1,
    "ferrule_dia_mm": (5.7, 0.1),                      # 5.7 +0.1
    "max_total_bend_deg": 500.0,
    "min_bend_radius_mm": 50.0,
    "housing": "compressionless, low-friction liner, aluminium ferrules, "
               "unsealed, 1.1 mm polished cable, continuous housing only",
    "avoid": ["S-bends with small radii", "pinch spots (high housing clamping force)"],
    "rear_exit_best": ["seat stay", "top of chain stay"],
    "notes": ["Exit points need verifying against the suspension design",
              "Minimise cable bending from suspension and handlebar motion",
              "Rear cable entrance location: dummy 90-7518-190-080"],
}


def check_cable_routing(total_bend_deg: float, min_radius_mm: float,
                        exit_location: Optional[str] = None,
                        exit_distance_mm: Optional[float] = None) -> list[str]:
    """Return a list of problems (empty list = routing meets the drawing's limits)."""
    problems = []
    if total_bend_deg > CABLE_SPEC["max_total_bend_deg"]:
        problems.append(f"total bend {total_bend_deg} deg > {CABLE_SPEC['max_total_bend_deg']}")
    if min_radius_mm < CABLE_SPEC["min_bend_radius_mm"]:
        problems.append(f"bend radius {min_radius_mm} mm < {CABLE_SPEC['min_bend_radius_mm']}")
    if exit_location is not None:
        if exit_location not in CABLE_EXIT_MIN_MM:
            problems.append(f"unknown exit location {exit_location!r}")
        else:
            info = CABLE_EXIT_MIN_MM[exit_location]
            if exit_distance_mm is not None and exit_distance_mm < info["min_mm"]:
                problems.append(f"{exit_location}: {exit_distance_mm} mm < min {info['min_mm']} mm")
            if not info["preferred"]:
                problems.append(f"{exit_location} is a 'less preferred' exit (warning)")
    return problems


# --------------------------------------------------------------------------- #
# Chain growth - sheet 7
# --------------------------------------------------------------------------- #

MAX_CHAIN_GROWTH_MM = 54.0   # fully extended minus fully compressed, in the smallest cog
SMALLEST_COG_PITCH_CIRCLE_DIA_MM = 41.1   # sheet 5, for frames with an upper idler


def chain_growth_ok(len_compressed_mm: float, len_extended_mm: float) -> bool:
    """Total chain growth (extended - compressed, smallest cog) must not exceed 54 mm.
    A lower idler pulley is strongly recommended to stay within it."""
    return (len_extended_mm - len_compressed_mm) <= MAX_CHAIN_GROWTH_MM


# --------------------------------------------------------------------------- #
# Road AXS keep-out zone - sheet 6 (use WITH the -070 clearance model)
# --------------------------------------------------------------------------- #

ROAD_KEEP_OUT = {
    "model": "90-7518-190-130",
    "x_offset_from_axle_mm": 15.0,    # zone starts 15 mm from the axle centreline
    "x_extent_mm": 67.0,              # to 67 mm from the axle centreline
    "y_below_connection_line_start_mm": 13.0,   # top edge 13 mm below the BB connection line
    "y_below_connection_line_end_mm": 67.0,     # bottom edge 67 mm below it
    "corner_radius_mm": 32.0,
    "confidence": "medium",
    "note": "Read from the 2D view on sheet 6; confirm orientation in the STEP model.",
}

# --------------------------------------------------------------------------- #
# Coordinate system for the 3D models - sheet 5
# --------------------------------------------------------------------------- #

COORDINATE_SYSTEM = {
    "x_axis": "hub axis",
    "x_plane": "end face of the drive-side hub axle end cap",
    "y_axis_no_upper_idler": "plane through hub axis and BB axis, in the sag position",
    "no_upper_idler_alignment": "chain middle plane tangent to smallest cog pitch circle "
                                "(41.1 mm) and idler pulley pitch circle, in sag position",
    "wheel_removal_state": "50 deg from the operational state (cable entrance dummy contact 2)",
}

MODELS = {
    "90-7518-190-050": "Reference chain wave model (worst-case; contact SRAM on collision)",
    "90-7518-190-070": "Hangerless interface clearance model, Rev H",
    "90-7518-190-080": "Rear cable entrance dummy (contact 1 = operational, contact 2 = wheel removal)",
    "90-7518-190-090": "Front cable entrance dummy",
    "90-7518-190-130": "Road keep-out zone (Road AXS RD on UDH)",
    "STEP file": "UDH&FULL_MOUNT_RD_3D_MODELS_REV_H.stp",
}

# --------------------------------------------------------------------------- #
# Validation helper
# --------------------------------------------------------------------------- #


def validate_dropout(measured: dict[str, float]) -> dict[str, bool]:
    """Check measured frame values against DROPOUT limits.

    `measured` maps DROPOUT dim names to measured values, e.g.
        validate_dropout({"hanger_bore_dia": 20.05, "stop_face_offset": 14.45})
    Reference/info dims always pass. Unknown names raise KeyError.
    """
    return {name: DROPOUT[name].check(v) for name, v in measured.items()}


# --------------------------------------------------------------------------- #
# Demo
# --------------------------------------------------------------------------- #

if __name__ == "__main__":
    print(f"SRAM UDH frame spec {DRAWING_NUMBER} rev {DRAWING_REV}\n")
    for title, table in [("FRAME DROPOUT", DROPOUT), ("AXLE", AXLE), ("HANGER", HANGER)]:
        print(f"== {title} ==")
        for dim in table.values():
            print("  ", dim)
        print()

    print("== Example checks ==")
    print("validate_dropout:", validate_dropout({"hanger_bore_dia": 20.05, "stop_face_offset": 14.6}))
    nom, lo, hi = axle_length(D=8.0, OLD=148)
    print(f"axle L1 for D=8, OLD=148: {nom} (min {lo}, max {hi})")
    print("frame span for OLD=148:", frame_span(148))
    print("cable check:", check_cable_routing(450, 60, "top_of_chain_stay", 120))
    print("chain growth ok (150 -> 200):", chain_growth_ok(150, 200))
    print("general tol for 45 mm:", general_tolerance(45))
