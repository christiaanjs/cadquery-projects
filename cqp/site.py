"""Static site: index of projects, per-project pages with 3D viewer, drawings and downloads.

All links are relative so the site works at a domain root, under /<repo>/, and under
/<repo>/pr-<n>/ (PR previews).
"""

from __future__ import annotations

import html
import json
import shutil
from datetime import UTC, datetime
from pathlib import Path

import markdown

from .build import build_project, info_text
from .project import REPO_ROOT, Project, all_projects

VIEWER_DIR = REPO_ROOT / "viewer"
SITE_TITLE = "CadQuery Projects"

CSS = """
:root { color-scheme: light dark; --bg:#f6f7f9; --fg:#1b1f24; --muted:#667; --card:#fff; --line:#dde1e6; --accent:#1a6bb5; }
@media (prefers-color-scheme: dark) { :root { --bg:#14161a; --fg:#e6e8eb; --muted:#9aa3ad; --card:#1d2026; --line:#2e333b; --accent:#6db3f2; } }
* { box-sizing: border-box; }
body { margin:0; background:var(--bg); color:var(--fg); font:15px/1.55 system-ui,-apple-system,Segoe UI,sans-serif; }
main { max-width:1100px; margin:0 auto; padding:24px 16px 64px; }
a { color:var(--accent); text-decoration:none; } a:hover { text-decoration:underline; }
h1 { margin:.2em 0 .1em; font-size:1.7rem; } h2 { margin:2em 0 .6em; font-size:1.2rem; border-bottom:1px solid var(--line); padding-bottom:.25em; }
h3 { margin:1.4em 0 .4em; font-size:1rem; }
.meta, .muted { color:var(--muted); font-size:.85rem; }
.tag { display:inline-block; font-size:.75rem; padding:1px 8px; border:1px solid var(--line); border-radius:99px; margin-right:4px; color:var(--muted); background:var(--card); cursor:pointer; }
.tag.on { background:var(--accent); color:#fff; border-color:var(--accent); }
.grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(260px,1fr)); gap:16px; margin-top:16px; }
.card { background:var(--card); border:1px solid var(--line); border-radius:10px; overflow:hidden; color:inherit; display:block; }
.card:hover { border-color:var(--accent); text-decoration:none; }
.card img { width:100%; aspect-ratio:3/2; object-fit:contain; background:#fff; display:block; border-bottom:1px solid var(--line); }
.card div { padding:10px 12px; } .card strong { display:block; }
.viewer { width:100%; height:520px; border:1px solid var(--line); border-radius:10px; background:#1a1a2e; }
.drawings { display:grid; grid-template-columns:repeat(auto-fill,minmax(300px,1fr)); gap:12px; }
.drawings a { background:#fff; border:1px solid var(--line); border-radius:8px; overflow:hidden; display:block; }
.drawings img { width:100%; display:block; } .drawings span { display:block; padding:3px 10px; font-size:.8rem; background:var(--card); color:var(--muted); }
table { border-collapse:collapse; width:100%; font-size:.9rem; background:var(--card); border:1px solid var(--line); border-radius:8px; }
th, td { text-align:left; padding:6px 10px; border-bottom:1px solid var(--line); } th { color:var(--muted); font-weight:600; font-size:.8rem; }
td.num { text-align:right; font-variant-numeric:tabular-nums; }
.dl a { display:inline-block; margin:0 6px 6px 0; padding:2px 10px; border:1px solid var(--line); border-radius:6px; background:var(--card); font-size:.85rem; }
.readme { background:var(--card); border:1px solid var(--line); border-radius:10px; padding:4px 20px 12px; }
.readme h1 { display:none; }
.sw { display:inline-block; width:10px; height:10px; border-radius:2px; border:1px solid #8884; margin-right:6px; }
code { background:#8882; padding:1px 4px; border-radius:4px; }
details summary { cursor:pointer; color:var(--muted); }
"""

PAGE = """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="icon" href="data:,"><title>{title}</title><style>{css}</style></head>
<body><main>{body}</main></body></html>
"""


def e(s) -> str:
    return html.escape(str(s))


def _ensure_built(project: Project, rebuild: bool) -> dict:
    manifest = project.build_dir / "manifest.json"
    if rebuild or not manifest.exists():
        result = build_project(project)
        print(info_text(project, result))
        if not result.ok:
            raise SystemExit(f"build failed for {project.slug}")
    return json.loads(manifest.read_text(encoding="utf-8"))


def _readme_html(project: Project) -> str:
    text = project.readme().strip()
    if not text:
        return ""
    body = markdown.markdown(text, extensions=["tables", "fenced_code", "sane_lists"])
    return f'<h2>About</h2><div class="readme">{body}</div>'


def _params_html(model: dict) -> str:
    if not model.get("params"):
        return ""
    rows = "".join(f"<tr><td><code>{e(k)}</code></td><td>{e(v)}</td></tr>"
                   for k, v in model["params"].items())
    return f"<details><summary>Parameters</summary><table><tr><th>Name</th><th>Default</th></tr>{rows}</table></details>"


def _parts_html(model: dict) -> str:
    parts = model.get("parts") or []
    if len(parts) < 2:
        return ""
    rows = []
    for p in parts:
        swatch = f'<span class="sw" style="background:{e(p["color"])}"></span>' if p.get("color") else ""
        rows.append(
            f'<tr><td>{swatch}{e(p["name"])}</td><td class="num">{p["qty"]}</td>'
            f'<td>{e(p["size"])}</td><td class="num">{p["volume_cm3"] or ""}</td></tr>'
        )
    return ("<h3>Parts</h3><table><tr><th>Part</th><th>Qty</th><th>Size (L × W × H)</th>"
            f"<th>Volume (cm³)</th></tr>{''.join(rows)}</table>")


def _bom_html(project: Project) -> str:
    bom = project.bom
    if not bom:
        return ""
    total = sum(float(r.get("qty", 1)) * float(r.get("price", 0)) for r in bom)
    rows = "".join(
        f'<tr><td>{e(r.get("item", ""))}</td><td class="num">{e(r.get("qty", 1))}</td>'
        f'<td>{e(r.get("unit", ""))}</td><td class="num">{float(r.get("price", 0)):.2f}</td>'
        f'<td class="num">{float(r.get("qty", 1)) * float(r.get("price", 0)):.2f}</td></tr>'
        for r in bom
    )
    return (f"<h2>Bill of materials</h2><table><tr><th>Item</th><th>Qty</th><th>Unit</th>"
            f'<th>Price</th><th>Total</th></tr>{rows}<tr><td colspan="4"><b>Total</b></td>'
            f'<td class="num"><b>{total:.2f}</b></td></tr></table>')


def _model_html(project: Project, manifest: dict, model: dict, multi: bool) -> str:
    slug = manifest["slug"]
    bg = manifest.get("background") or ""
    q = f"embed=1&model=../{slug}/{model['files']['glb']}"
    if bg:
        q += "&bg=" + bg.replace("#", "%23")
    heading = f"<h2>{e(model['name'])}</h2>" if multi else "<h2>3D model</h2>"
    drawings = "".join(
        f'<a href="{e(d["file"])}" target="_blank"><img loading="lazy" src="{e(d["file"])}" '
        f'alt="{e(d["label"])}"><span>{e(d["label"])}</span></a>'
        for d in model.get("drawings", [])
    )
    downloads = "".join(
        f'<a href="{e(f)}" download>{k.upper()}</a>' for k, f in model["files"].items()
    ) + "".join(
        f'<a href="{e(d["file"])}" download>SVG {e(d["label"])}</a>' for d in model.get("drawings", [])
    )
    info = (f'<p class="meta">{e(model["bbox_label"])} (X × Y × Z) · {model["solids"]} solid(s) · '
            f'{model["volume_cm3"]} cm³</p>')
    return (
        f'{heading}{info}<iframe class="viewer" loading="lazy" title="3D viewer: {e(model["name"])}" '
        f'src="../viewer/index.html?{q}"></iframe>'
        f'{_params_html(model)}{_parts_html(model)}'
        f'<h3>Drawings</h3><div class="drawings">{drawings}</div>'
        f'<h3>Downloads</h3><div class="dl">{downloads}</div>'
    )


def _project_page(project: Project, manifest: dict, generated: str) -> str:
    models = manifest["models"]
    multi = len(models) > 1
    tags = "".join(f'<span class="tag">{e(t)}</span>' for t in manifest.get("tags", []))
    desc = f"<p>{e(manifest['description'])}</p>" if manifest.get("description") else ""
    body = (
        f'<p class="meta"><a href="../">← All projects</a></p><h1>{e(manifest["title"])}</h1>'
        f'<div>{tags}</div>{desc}'
        + "".join(_model_html(project, manifest, m, multi) for m in models)
        + _bom_html(project) + _readme_html(project)
        + f'<p class="meta" style="margin-top:3em">Generated {generated} · units: {e(manifest["units"])}</p>'
    )
    return PAGE.format(title=f'{e(manifest["title"])} — {SITE_TITLE}', css=CSS, body=body)


def _index_page(entries: list[dict], generated: str) -> str:
    all_tags = sorted({t for p in entries for t in p["tags"]})
    tag_html = "".join(f'<span class="tag" data-tag="{e(t)}">{e(t)}</span>' for t in all_tags)
    cards = "".join(
        f'<a class="card" href="{e(p["slug"])}/" data-tags="{e(" ".join(p["tags"]))}">'
        f'<img loading="lazy" src="{e(p["slug"])}/{e(p["thumb"])}" alt="">'
        f'<div><strong>{e(p["title"])}</strong>'
        f'<span class="muted">{e(p["description"][:110])}</span></div></a>'
        for p in entries
    )
    script = """<script>
const on=new Set();document.querySelectorAll('[data-tag]').forEach(t=>t.onclick=()=>{
 on.has(t.dataset.tag)?on.delete(t.dataset.tag):on.add(t.dataset.tag);t.classList.toggle('on');
 document.querySelectorAll('.card').forEach(c=>{const ts=c.dataset.tags.split(' ');
  c.style.display=[...on].every(x=>ts.includes(x))?'':'none';});});</script>"""
    body = (f'<h1>{SITE_TITLE}</h1><p class="meta">{len(entries)} project(s) · generated {generated}</p>'
            f'<div>{tag_html}</div><div class="grid">{cards}</div>{script}')
    return PAGE.format(title=SITE_TITLE, css=CSS, body=body)


def build_site(out_dir: Path, only: str | None = None, rebuild: bool = False) -> list[dict]:
    projects = all_projects()
    if only:
        wanted = {s.strip() for s in only.split(",")}
        projects = [p for p in projects if p.slug in wanted]
    if not projects:
        raise SystemExit("no projects to publish")

    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)
    shutil.copytree(VIEWER_DIR, out_dir / "viewer")
    (out_dir / ".nojekyll").write_text("")
    generated = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")

    entries = []
    for project in projects:
        manifest = _ensure_built(project, rebuild)
        dst = out_dir / project.slug
        dst.mkdir()
        for f in project.build_dir.iterdir():
            if f.suffix in {".svg", ".glb", ".step", ".stl"}:
                shutil.copy2(f, dst / f.name)
        (dst / "index.html").write_text(_project_page(project, manifest, generated), encoding="utf-8")
        first = manifest["models"][0]
        thumb = next((d["file"] for d in first.get("drawings", []) if d["view"] == "iso"),
                     first["drawings"][0]["file"] if first.get("drawings") else "")
        entries.append({
            "slug": project.slug, "title": project.title, "description": project.description,
            "tags": project.tags, "thumb": thumb,
            "models": [m["name"] for m in manifest["models"]],
        })
    (out_dir / "index.html").write_text(_index_page(entries, generated), encoding="utf-8")
    (out_dir / "projects.json").write_text(json.dumps(entries, indent=2), encoding="utf-8")
    return entries
