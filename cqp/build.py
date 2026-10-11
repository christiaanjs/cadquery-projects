"""Build a project: run models, export STEP/STL/GLB, render drawings, write a manifest."""

from __future__ import annotations

import json
import traceback
from dataclasses import dataclass, field
from pathlib import Path

import cadquery as cq

from . import drawings
from .loader import Model, ModelError, load_model
from .project import Project
from .render import RenderError, exact_bbox, fmt_len, render_svg, svg_to_png

FORMATS = ("step", "stl", "glb")


@dataclass
class BuildResult:
    project: Project
    models: list[dict] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def select_model_files(project: Project, only: str | None = None) -> list[Path]:
    files = project.model_files()
    if only:
        files = [f for f in files if f.stem == only.removesuffix(".py")]
        if not files:
            raise ModelError(f"{project.slug}: no model named '{only}'")
    return files


def load_project_models(project: Project, only: str | None = None) -> list[Model]:
    """Load models, raising on the first failure (used by single-model commands)."""
    return [load_model(f, project.scale_to_mm) for f in select_model_files(project, only)]


def export_model(model: Model, out_dir: Path, formats=FORMATS) -> dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    written = {}
    if "step" in formats:
        p = out_dir / f"{model.name}.step"
        model.assembly.export(str(p), exportType="STEP")
        written["step"] = p.name
    if "stl" in formats:
        p = out_dir / f"{model.name}.stl"
        model.compound().exportStl(str(p), tolerance=0.1, angularTolerance=0.2)
        written["stl"] = p.name
    if "glb" in formats:
        p = out_dir / f"{model.name}.glb"
        model.assembly.export(str(p), exportType="GLTF", binary=True)
        written["glb"] = p.name
    return written


def model_summary(model: Model, project: Project) -> dict:
    comp = model.compound()
    bb = exact_bbox(comp)
    solids = comp.Solids()
    return {
        "name": model.name,
        "params": model.params,
        "bbox_mm": [round(bb.xlen, 3), round(bb.ylen, 3), round(bb.zlen, 3)],
        "bbox_label": " × ".join(
            fmt_len(v, project.scale_to_mm, project.units).replace(f" {project.units}", "")
            for v in (bb.xlen, bb.ylen, bb.zlen)
        ) + f" {project.units}",
        "solids": len(solids),
        "volume_cm3": round(sum(s.Volume() for s in solids) / 1000.0, 3),
        "parts": drawings.part_rows(model, project.scale_to_mm, project.units),
        "log": model.log.strip(),
    }


def build_project(
    project: Project,
    *,
    only: str | None = None,
    formats=FORMATS,
    render: bool = True,
    out_dir: Path | None = None,
) -> BuildResult:
    out = out_dir or project.build_dir
    result = BuildResult(project)
    try:
        files = select_model_files(project, only)
    except ModelError as e:
        result.errors.append(str(e))
        return result
    if not files:
        result.errors.append(f"{project.slug}: no model files in {project.models_dir}")
        return result

    for file in files:
        try:
            model = load_model(file, project.scale_to_mm)
            info = model_summary(model, project)
            info["files"] = export_model(model, out, formats)
            if render:
                info["drawings"] = render_model_drawings(model, project, out)
            result.models.append(info)
        except (ModelError, RenderError) as e:
            result.errors.append(f"{project.slug}/{file.stem}: {e}")
        except Exception as e:
            tb = traceback.format_exc(limit=3)
            result.errors.append(f"{project.slug}/{file.stem}: {type(e).__name__}: {e}\n{tb}")
    if not only and result.models:
        write_manifest(project, result, out)
    return result


def render_model_drawings(model: Model, project: Project, out: Path) -> list[dict]:
    """Write SVG views (+ exploded) for a model; returns [{view, label, file}]."""
    out.mkdir(parents=True, exist_ok=True)
    comp = model.compound()
    multi = len(project.model_files()) > 1
    title = f"{project.title} — {model.name}" if multi else project.title
    units = dict(unit_mm=project.scale_to_mm, unit=project.units)
    entries = []
    opts = project.model_options(model.name)
    views = opts.get("views", project.views)
    for view in views:
        svg = render_svg(comp, view, title=title, **units)
        name = f"{model.name}-{view}.svg"
        (out / name).write_text(svg, encoding="utf-8")
        entries.append({"view": view, "label": view.title(), "file": name})
    if opts.get("exploded", True):
        svg = drawings.exploded_svg(model, title=title, **units, factor=opts.get("explode", 1.6))
        if svg:
            name = f"{model.name}-exploded.svg"
            (out / name).write_text(svg, encoding="utf-8")
            entries.append({"view": "exploded", "label": "Exploded", "file": name})
    return entries


def write_manifest(project: Project, result: BuildResult, out: Path) -> None:
    manifest = {
        "slug": project.slug,
        "title": project.title,
        "description": project.description,
        "units": project.units,
        "tags": project.tags,
        "background": project.background,
        "models": result.models,
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def write_preview_png(project: Project, view: str = "iso", model: str | None = None) -> Path:
    """Render a PNG preview into projects/<slug>/preview.png for quick visual checks."""
    models = load_project_models(project, model)
    m = models[0]
    svg = render_svg(
        m.compound(), view, title=project.title,
        unit_mm=project.scale_to_mm, unit=project.units,
    )
    path = project.path / ("preview.png" if view == "iso" else f"preview-{view}.png")
    svg_to_png(svg, path)
    return path


def info_text(project: Project, result: BuildResult) -> str:
    lines = [f"{project.slug}  ({project.units})"]
    for m in result.models:
        lines.append(
            f"  {m['name']}: {m['bbox_label']} (X×Y×Z), {m['solids']} solid(s), "
            f"{m['volume_cm3']} cm³, {len(m['parts'])} part group(s)"
        )
        if m["log"]:
            lines += ["    | " + ln for ln in m["log"].splitlines()]
    for e in result.errors:
        lines.append(f"  ERROR {e}")
    return "\n".join(lines)


__all__ = ["build_project", "write_preview_png", "info_text", "cq"]
