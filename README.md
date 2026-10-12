# CadQuery Projects

Parametric CAD projects written in [CadQuery](https://cadquery.readthedocs.io/), with shared tooling
for building, drawing, previewing and publishing them. Projects can be anything: house and garden
planning, small bike parts, brackets, jigs.

**Site:** https://christiaanjs.github.io/cadquery-projects/ (3D viewer, dimensioned drawings, STEP/STL/GLB downloads)
Pull requests get their own preview at `…/cadquery-projects/pr-<n>/`, linked in a PR comment.

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

Python 3.11+. On Linux, CairoSVG needs `libcairo2` (`apt install libcairo2`).

## Workflow

```bash
cqp new "Bike Bottle Cage" --units mm --tag bike   # scaffold projects/bike-bottle-cage/
cqp build bike-bottle-cage                          # run models → build/<slug>/ (STEP, STL, GLB, SVG)
cqp render bike-bottle-cage --view iso --view front # PNG previews → projects/<slug>/preview*.png
cqp serve bike-bottle-cage                          # live 3D viewer at http://localhost:5001, reloads on save
cqp site --out _site                                # the full static site (open _site/index.html via any web server)
cqp check                                           # build every project; what CI runs
```

## Project layout

```
projects/<slug>/
├── project.toml     # title, description, units, tags, views, background, optional BOM
├── README.md        # shown on the project page
├── models/*.py      # one file per model; all of them are built and published
└── scripts/         # optional project-specific helpers (not run by cqp)
```

`build/` and `_site/` are generated and git-ignored.

### Model files

A model provides geometry in any one of these ways (so files also run unchanged in CQ-editor):

```python
import cadquery as cq

PARAMS = {"length": 100, "width": 40}          # documented defaults (shown on the site)

def build(length, width):                      # 1. build(**PARAMS)
    return cq.Workplane().box(length, width, 10)

# result = build(**PARAMS)                     # 2. a module-level `result`
# show_object(obj, name="plate",               # 3. show_object (one or many parts)
#             options={"color": "#8a9ba8", "alpha": 0.5})
```

- Several `show_object` calls form an assembly; names become part names in the viewer and parts table.
- Solids are drawn with hidden lines removed. **Faces, edges and wires are reference geometry**
  (planes, boundaries, axes): shown dashed blue in drawings and never hide anything.
- Files starting with `_` are helpers, not models. Models can import siblings in `models/`.
- Set `units` in `project.toml` (`mm`, `cm`, `m`, `in`, `ft`). Model coordinates stay in those units;
  everything exported is converted to millimetres and drawing labels use your units.
- Z is up. Views: `iso front back side left top bottom` (`front` looks along +Y, `top` has +Y up).

### project.toml

```toml
title = "Recession plane check"
description = "One line for the index card."
units = "cm"
tags = ["planning", "home"]
views = ["iso", "front", "side", "top"]   # drawings to produce
background = "#ffffff"                      # 3D viewer background

[models.my_model]                           # per-model overrides
views = ["iso", "top"]
exploded = false                            # skip the exploded view for assemblies

[[bom]]                                     # optional bill of materials
item = "M5 x 12 screw"
qty = 4
price = 0.25

[[variants]]                                # optional: publish several parameter sets
slug = "wide"                               # URL segment: <project>/wide/
title = "Wide version"
description = "Shown on the variant's card and page."
params = { width = 60 }                     # overrides for every model whose PARAMS has the key
```

### Variants

With `[[variants]]`, every model is built once per variant into `build/<slug>/<variant>/`. The
project page shows a card per variant, and each variant gets its own page with viewer, drawings
and downloads. Overrides need a `build()` function: the file runs as usual, then the loader calls
`build(**{**PARAMS, **overrides})` and keeps only that geometry and output. `build()` may call
`show_object` itself for named or coloured parts. A key that no model has in `PARAMS` fails the
build, so typos are caught. `cqp build <slug> --variant <v>` and `cqp render <slug> --variant <v>`
work on one variant; `cqp render` and `cqp serve` otherwise use the `PARAMS` defaults.

## Publishing

CI (`.github/workflows`):

| Workflow | When | Does |
|---|---|---|
| `ci.yml` | PRs, pushes to `main` | ruff, pytest, `cqp check` (every model must build) |
| `site.yml` | push to `main` | builds the site → `gh-pages` root |
| `site.yml` | PR opened/updated | builds the site → `gh-pages/pr-<n>/`, comments links on the PR |
| `site.yml` | PR closed | deletes `pr-<n>/` |

One-time setup: **Settings → Pages → Source: Deploy from a branch → `gh-pages` / root.**
PRs from forks are checked by CI but not deployed (no write token).
Removing a project leaves its old directory on `gh-pages` until deleted by hand (deploys keep existing files so PR previews survive).

## Tests

```bash
pytest -q && ruff check .
```

The Three.js viewer is vendored in `viewer/vendor/` (r160, MIT) so the site has no CDN dependency.
