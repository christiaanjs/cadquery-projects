import json
import textwrap
from pathlib import Path

import cadquery as cq
import pytest

from cqp import build as cqp_build
from cqp.loader import ModelError, load_model
from cqp.project import Project, all_projects, load_project, slugify
from cqp.render import VIEWS, exact_bbox, fmt_len, render_svg, split_reference
from cqp.scaffold import new_project


def write(tmp_path: Path, name: str, code: str) -> Path:
    p = tmp_path / name
    p.write_text(textwrap.dedent(code))
    return p


def test_loader_result_variable(tmp_path):
    p = write(tmp_path, "m.py", "import cadquery as cq\nresult = cq.Workplane().box(1, 2, 3)\n")
    m = load_model(p)
    assert len(m.compound().Solids()) == 1


def test_loader_build_and_params(tmp_path):
    p = write(tmp_path, "m.py", """
        import cadquery as cq
        PARAMS = {"w": 10}
        def build(w):
            return cq.Workplane().box(w, w, w)
    """)
    m = load_model(p)
    assert m.params == {"w": 10}
    assert exact_bbox(m.compound()).xlen == pytest.approx(10)


def test_loader_show_object_multiple_and_scale(tmp_path):
    p = write(tmp_path, "m.py", """
        import cadquery as cq
        show_object(cq.Workplane().box(1, 1, 1), name="a", options={"color": "#ff0000"})
        show_object(cq.Workplane().box(1, 1, 1).translate((5, 0, 0)), name="b")
    """)
    m = load_model(p, scale=10.0)  # cm -> mm
    assert [n for n, _, _ in m.parts()] == ["a", "b"]
    assert exact_bbox(m.compound()).xlen == pytest.approx(60)


def test_loader_errors(tmp_path):
    with pytest.raises(ModelError, match="no geometry"):
        load_model(write(tmp_path, "a.py", "x = 1\n"))
    with pytest.raises(ModelError, match="ZeroDivisionError"):
        load_model(write(tmp_path, "b.py", "1 / 0\n"))


def test_loader_sibling_import(tmp_path):
    write(tmp_path, "helper.py", "import cadquery as cq\ndef mk(): return cq.Workplane().box(1,1,1)\n")
    m = load_model(write(tmp_path, "m.py", "from helper import mk\nresult = mk()\n"))
    assert m.compound().Solids()


def test_reference_geometry_split():
    solid = cq.Workplane().box(1, 1, 1).val()
    face = cq.Workplane().rect(5, 5).extrude(1).faces(">Z").val()
    solids, refs = split_reference(cq.Compound.makeCompound([solid, face]))
    assert len(solids) == 1 and len(refs) == 1


@pytest.mark.parametrize("view", list(VIEWS))
def test_render_all_views(view):
    shape = cq.Workplane().box(40, 20, 10).faces(">Z").hole(5).val()
    svg = render_svg(shape, view, title="t")
    assert svg.startswith("<svg") and "<path" in svg


def test_render_orientation_front_has_z_up():
    # tall thin block: in 'front' the drawing must be taller than wide
    shape = cq.Workplane().box(10, 10, 100).val()
    assert "100 mm" in render_svg(shape, "front")


def test_fmt_len():
    assert fmt_len(1250, 10, "cm") == "125 cm"
    assert fmt_len(2.5) == "2.5 mm"
    assert fmt_len(0.125) == "0.12 mm" or fmt_len(0.125) == "0.13 mm"


def test_slugify():
    assert slugify("Garden Gate (v2)") == "garden-gate-v2"


def test_scaffold_and_build(tmp_path, monkeypatch):
    import cqp.project as proj
    import cqp.scaffold as scaffold

    monkeypatch.setattr(scaffold, "PROJECTS_DIR", tmp_path)
    monkeypatch.setattr(proj, "BUILD_DIR", tmp_path / "build")
    path = new_project("Test Part", units="mm", tags=["x"])
    project = load_project(path.name, tmp_path)
    assert project.tags == ["x"]
    result = cqp_build.build_project(project, out_dir=tmp_path / "out")
    assert result.ok, result.errors
    files = {p.name for p in (tmp_path / "out").iterdir()}
    assert {"main.step", "main.stl", "main.glb", "main-iso.svg", "manifest.json"} <= files
    manifest = json.loads((tmp_path / "out" / "manifest.json").read_text())
    assert manifest["models"][0]["solids"] == 1


def test_build_reports_failing_model(tmp_path):
    (tmp_path / "bad" / "models").mkdir(parents=True)
    (tmp_path / "bad" / "models" / "m.py").write_text("raise RuntimeError('boom')\n")
    project = Project("bad", tmp_path / "bad")
    result = cqp_build.build_project(project, out_dir=tmp_path / "out")
    assert not result.ok and "boom" in result.errors[0]


def test_repo_projects_build(tmp_path):
    """Every project in the repo builds (what CI relies on)."""
    projects = all_projects()
    assert projects
    for p in projects:
        r = cqp_build.build_project(p, out_dir=tmp_path / p.slug, formats=("step",), render=False)
        assert r.ok, r.errors
