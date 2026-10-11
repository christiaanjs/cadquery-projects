"""`cqp new` — project scaffolding."""

from __future__ import annotations

from pathlib import Path

from .project import PROJECTS_DIR, ProjectError, slugify

MODEL = '''\
"""{title}: parametric model. Dimensions are in {units}."""
import cadquery as cq

PARAMS = {{
    "length": 100,
    "width": 40,
    "height": 20,
    "hole_dia": 8,
}}


def build(length, width, height, hole_dia):
    return (
        cq.Workplane("XY")
        .box(length, width, height)
        .faces(">Z").workplane()
        .hole(hole_dia)
    )


# Either `result = build(**PARAMS)` or `show_object(...)` works; build() alone is enough.
'''

README = """# {title}

<One paragraph: what is it, what is it for, key design intent.>

## Status
**planning**   <!-- planning | modelling | ready-to-build | complete -->

## Notes
- Units: {units}
"""


def new_project(name: str, units: str = "mm", tags: list[str] | None = None) -> Path:
    slug = slugify(name)
    if not slug:
        raise ProjectError("project name must contain letters or digits")
    path = PROJECTS_DIR / slug
    if path.exists():
        raise ProjectError(f"{path} already exists")
    (path / "models").mkdir(parents=True)
    tag_list = ", ".join(f'"{t}"' for t in (tags or []))
    (path / "project.toml").write_text(
        f'title = "{name}"\ndescription = ""\nunits = "{units}"\ntags = [{tag_list}]\n',
        encoding="utf-8",
    )
    (path / "README.md").write_text(README.format(title=name, units=units), encoding="utf-8")
    (path / "models" / "main.py").write_text(
        MODEL.format(title=name, units=units), encoding="utf-8"
    )
    return path
