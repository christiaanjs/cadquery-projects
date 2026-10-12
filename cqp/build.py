"""Build a project: run models, export STEP/STL/GLB, render drawings, write a manifest."""

from __future__ import annotations

import json
import traceback
from dataclasses import dataclass, field
from pathlib import Path

import cadquery as cq

from . import drawings
from .loader import Model, ModelError, load_model
from .project import Project, Variant
from .render import RenderError, exact_bbox, fmt_len, render_svg, svg_to_png

FORMATS = ("step", "stl", "glb")


@dataclass
class BuildResult:
    project: Project
    models: list[dict] = field(default_factory=list)      # projects without variants
    variants: list[dict] = field(default_factory=list)    # {slug, title, description, params, models}
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


def load_project_models(
    project: Project, only: str | None = None, variant: str | None = None
) -> list[Model]:
    """Load models, raising on the first failure (used by single-model commands)."""
    overrides = project.variant(variant).params if variant else None
    return [load_model(f, project.scale_to_mm, overrides) for f in select_model_files(project, only)]


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
        "overrides": sorted(model.overrides),
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
    variant: str | None = None,
    formats=FORMATS,
    render: bool = True,
    out_dir: Path | None = None,
) -> BuildResult:
    """Build every model, once per configured variant (into ``<out>/<variant>/``).

    Projects without ``[[variants]]`` build straight into ``<out>/`` as before.
    """
    out = out_dir or project.build_dir
    result = BuildResult(project)
    try:
        files = select_model_files(project, only)
        variants = [project.variant(variant)] if variant else project.variants
    except Exception as e:  # ModelError / ProjectError
        result.errors.append(str(e))
        return result
    if not files:
        result.errors.append(f"{project.slug}: no model files in {project.models_dir}")
        return result

    if not variants:
        result.models = _build_models(project, files, out, None, formats, render, result.errors)
    for v in variants:
        n_err = len(result.errors)
        models = _build_models(project, files, out / v.slug, v, formats, render, result.errors)
        if not only and len(result.errors) == n_err:
            known = {k for m in models for k in m["params"]}
            unknown = sorted(set(v.params) - known)
            if unknown:
                result.errors.append(
                    f"{project.slug}: variant '{v.slug}' sets {unknown}, which no model has in PARAMS"
                )
        result.variants.append({
            "slug": v.slug, "title": v.title, "description": v.description,
            "params": v.params, "models": models,
        })
    if not only and not variant and (result.models or result.variants):
        write_manifest(project, result, out)
    return result


def _build_models(
    project: Project, files: list[Path], out: Path, variant: Variant | None,
    formats, render: bool, errors: list[str],
) -> list[dict]:
    where = f"{project.slug}[{variant.slug}]" if variant else project.slug
    models = []
    for file in files:
        try:
            model = load_model(file, project.scale_to_mm, variant.params if variant else None)
            info = model_summary(model, project)
            info["files"] = export_model(model, out, formats)
            if render:
                info["drawings"] = render_model_drawings(model, project, out, variant)
            models.append(info)
        except (ModelError, RenderError) as e:
            errors.append(f"{where}/{file.stem}: {e}")
        except Exception as e:
            tb = traceback.format_exc(limit=3)
            errors.append(f"{where}/{file.stem}: {type(e).__name__}: {e}\n{tb}")
    return models


def render_model_drawings(
    model: Model, project: Project, out: Path, variant: Variant | None = None
) -> list[dict]:
    """Write SVG views (+ exploded) for a model; returns [{view, label, file}]."""
    out.mkdir(parents=True, exist_ok=True)
    comp = model.compound()
    multi = len(project.model_files()) > 1
    title = project.title + (f" — {variant.title}" if variant else "")
    if multi:
        title += f" — {model.name}"
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
        "variants": result.variants,
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def write_preview_png(
    project: Project, view: str = "iso", model: str | None = None, variant: str | None = None
) -> Path:
    """Render a PNG preview into projects/<slug>/preview.png for quick visual checks.

    Without ``variant`` the models' own PARAMS defaults are used.
    """
    models = load_project_models(project, model, variant)
    m = models[0]
    title = project.title + (f" — {project.variant(variant).title}" if variant else "")
    svg = render_svg(
        m.compound(), view, title=title,
        unit_mm=project.scale_to_mm, unit=project.units,
    )
    path = project.path / ("preview.png" if view == "iso" else f"preview-{view}.png")
    svg_to_png(svg, path)
    return path


def info_text(project: Project, result: BuildResult) -> str:
    lines = [f"{project.slug}  ({project.units})"]

    def models(ms, indent):
        for m in ms:
            lines.append(
                f"{indent}{m['name']}: {m['bbox_label']} (X×Y×Z), {m['solids']} solid(s), "
                f"{m['volume_cm3']} cm³, {len(m['parts'])} part group(s)"
            )
            if m["log"]:
                lines.extend(f"{indent}  | " + ln for ln in m["log"].splitlines())

    models(result.models, "  ")
    for v in result.variants:
        lines.append(f"  [{v['slug']}] {v['title']}")
        models(v["models"], "    ")
    for e in result.errors:
        lines.append(f"  ERROR {e}")
    return "\n".join(lines)


__all__ = ["build_project", "write_preview_png", "info_text", "cq"]
