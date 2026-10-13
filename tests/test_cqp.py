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


VARIANT_MODEL = """
    import cadquery as cq
    PARAMS = {"w": 10, "h": 2}
    def build(w, h):
        print(f"w={w}")
        show_object(cq.Workplane().box(w, w, h), name="plate", options={"color": "#336699"})
    build(**PARAMS)
"""


def test_loader_overrides_rebuild_with_merged_params(tmp_path):
    p = write(tmp_path, "m.py", VARIANT_MODEL)
    m = load_model(p, overrides={"w": 30, "other": 1})
    assert m.params == {"w": 30, "h": 2} and m.overrides == {"w": 30}
    assert [n for n, _, _ in m.parts()] == ["plate"]          # build()'s show_object kept
    assert exact_bbox(m.compound()).xlen == pytest.approx(30)
    assert m.log.strip() == "w=30"                             # default run's output dropped


def test_loader_overrides_need_build(tmp_path):
    p = write(tmp_path, "m.py", "import cadquery as cq\nPARAMS = {'w': 1}\nresult = cq.Workplane().box(1, 1, 1)\n")
    with pytest.raises(ModelError, match="need a build"):
        load_model(p, overrides={"w": 2})
    assert load_model(p, overrides={"unrelated": 2}).params == {"w": 1}


def _variant_project(tmp_path, variants_toml):
    root = tmp_path / "proj"
    (root / "models").mkdir(parents=True)
    (root / "models" / "m.py").write_text(textwrap.dedent(VARIANT_MODEL))
    (root / "project.toml").write_text('title = "V"\n' + textwrap.dedent(variants_toml))
    return load_project("proj", tmp_path)


def test_build_variants(tmp_path):
    project = _variant_project(tmp_path, """
        [[variants]]
        slug = "small"
        title = "Small"
        params = { w = 5 }
        [[variants]]
        title = "Big One"
        params = { w = 50 }
    """)
    assert [v.slug for v in project.variants] == ["small", "big-one"]
    out = tmp_path / "out"
    result = cqp_build.build_project(project, out_dir=out, formats=("glb",))
    assert result.ok, result.errors
    manifest = json.loads((out / "manifest.json").read_text())
    assert manifest["models"] == []
    assert [v["slug"] for v in manifest["variants"]] == ["small", "big-one"]
    big = manifest["variants"][1]["models"][0]
    assert big["params"]["w"] == 50 and big["overrides"] == ["w"]
    assert (out / "small" / "m.glb").exists() and (out / "big-one" / "m-iso.svg").exists()
    assert "[big-one] Big One" in cqp_build.info_text(project, result)


def test_variant_unknown_param_is_an_error(tmp_path):
    project = _variant_project(tmp_path, """
        [[variants]]
        slug = "typo"
        params = { width = 5 }
    """)
    result = cqp_build.build_project(project, out_dir=tmp_path / "out", formats=(), render=False)
    assert not result.ok and "width" in result.errors[0]


def test_variant_slug_validation(tmp_path):
    from cqp.project import ProjectError

    project = _variant_project(tmp_path, """
        [[variants]]
        slug = "Bad Slug"
    """)
    with pytest.raises(ProjectError, match="slug"):
        _ = project.variants


def test_serve_builds_variants_on_request(tmp_path):
    from cqp.server import create_app

    project = _variant_project(tmp_path, """
        [[variants]]
        slug = "small"
        params = { w = 5 }
        [[variants]]
        slug = "big"
        params = { w = 50 }
    """)
    client = create_app(project).test_client()
    status = client.get("/status").get_json()
    assert [v["slug"] for v in status["variants"]] == ["small", "big"]
    assert status["models"] == ["m"]

    def glb(variant):
        r = client.get("/model.glb", query_string={"model": "m", "variant": variant})
        assert r.status_code == 200 and r.data[:4] == b"glTF"
        return r.data

    small, big, defaults = glb("small"), glb("big"), glb("")
    assert len({small, big, defaults}) == 3          # each parameter set builds its own geometry
    assert client.get("/model.glb?model=m&variant=nope").status_code == 404
    assert client.get("/model.glb?model=nope").status_code == 500


def test_serve_reports_build_errors_per_variant(tmp_path):
    from cqp.server import create_app

    project = _variant_project(tmp_path, """
        [[variants]]
        slug = "bad"
        params = { w = 0 }
        [[variants]]
        slug = "ok"
        params = { w = 5 }
    """)
    client = create_app(project).test_client()
    bad = client.get("/model.glb?model=m&variant=bad")
    assert bad.status_code == 500 and b"m.py" in bad.data          # error text, not a stale file
    assert client.get("/model.glb?model=m&variant=ok").status_code == 200
