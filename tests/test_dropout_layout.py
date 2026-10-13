"""Frame / hub interface maths of the sliding-dropout models (projects/sliding-dropouts)."""
import importlib
import re
import sys
from pathlib import Path

import pytest

from cqp.loader import load_model

MODELS = Path(__file__).resolve().parent.parent / "projects" / "sliding-dropouts" / "models"


@pytest.fixture(scope="module")
def common():
    sys.path.insert(0, str(MODELS))
    try:
        yield importlib.import_module("_common")
    finally:
        sys.path.remove(str(MODELS))


def params(common, **kw):
    return {**common.PARAMS, "axle_offset_x": 0.0, "axle_offset_y": 0.0, **kw}


def test_native_frame_has_no_step(common):
    lay = common.layout(params(common))
    assert (lay.y_in, lay.seat_y, lay.step, lay.zs, lay.t) == (74.5, 83.5, 0.0, 0.0, 9.0)


def test_wider_hub_on_the_same_seats(common):
    lay = common.layout(params(common, hub_old=148.0))
    assert lay.hub_old == 148 and lay.y_in == 77.5 and lay.seat_y == 83.5
    assert lay.step == 3.0 and lay.zs == -3.0 and lay.t == 9.0
    thin = common.layout(params(common, hub_old=148.0, hub_offset_mode="thin"))
    assert thin.zs == 0 and thin.t == 6.0


def test_narrower_hub_steps_the_other_way(common):
    lay = common.layout(params(common, hub_old=135.0))
    assert lay.step == -3.5 and lay.zs == 3.5 and lay.t == 9.0


def test_old_offset_parameters_are_gone(common):
    assert "frame_old" not in common.PARAMS and "hub_width_offset" not in common.PARAMS


def test_explicit_seat_span_for_a_qr_frame_taking_a_142_hub(common):
    lay = common.layout(params(common, frame_seat_span=135.0, hub_old=142.0))
    assert lay.y_in == 74.5                       # UDH: 142 + 7 between insert faces
    assert lay.seat_y == 135 / 2 + 9
    assert lay.step == 7.0 and lay.zs == -7.0 and lay.t == 9.0
    with pytest.raises(ValueError, match="step"):  # 9 - 7 = 2 mm is too thin to be an option
        common.layout(params(common, frame_seat_span=135.0, hub_old=142.0, hub_offset_mode="thin"))


def test_hub_gap_moves_the_insert_face(common):
    lay = common.layout(params(common, hub_gap=0.0, frame_seat_span=135.0, hub_old=135.0))
    assert lay.y_in == 67.5 and lay.step == 0.0


def assembly_log(**overrides):
    base = {"brake_mount": "none", "frame_seat_span": 135.0, "hub_old": 142.0,
            "axle_offset_x": 32.0, "axle_offset_y": 32.0}
    return load_model(MODELS / "assembly.py", overrides={**base, **overrides}).log


def test_frame_plate_is_cut_back_past_the_bend():
    clear = assembly_log(bend_start=30.0)
    assert "cut back past the bend (clear of the key slot)" in clear
    assert re.search(r"overlap 0\.00 mm", clear) and "CLASH" not in clear
    close = assembly_log(bend_start=12.0)
    assert "breaks into the key slot" in close
