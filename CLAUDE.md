# cadquery-projects — Claude Code brief

Parametric CAD projects in CadQuery (OCCT). Domain-neutral: house/garden planning, bike parts,
mechanical parts, furniture. Tooling lives in `cqp/`; projects in `projects/<slug>/`.
See `README.md` for the full model/project format.

## Workflow

1. `cqp new "Name" --units mm|cm|m|in|ft --tag x` creates `projects/<slug>/` (project.toml, README, starter model).
2. Edit `projects/<slug>/models/*.py`. Keep dimensions as parameters at the top (`PARAMS` + `build(**PARAMS)`).
3. `cqp build <slug>` — runs every model, prints bbox / solid count / volume plus anything the model prints,
   and writes STEP/STL/GLB/SVG to `build/<slug>/` (`build/<slug>/<variant>/` per `[[variants]]` entry
   in project.toml — named parameter sets, each published as its own page). Exits non-zero on failure.
4. **Look at it before handing off:** `cqp render <slug> --view iso` (and `--view front|top|side`,
   `--variant <v>` for a variant's parameters), then
   Read `projects/<slug>/preview*.png`. Check dimensions/labels as well as the shape.
5. `cqp serve <slug> [--variant <v>]` for the interactive viewer (user-facing; needs a browser; has a variant picker).
6. Keep `projects/<slug>/README.md` current (status, dimensions, materials, notes) when models change meaningfully.
7. Before committing: `ruff check . && pytest -q && cqp check`.

## Conventions

- Pick `units` in project.toml to match how the source measurements were given (cm for a site sketch,
  mm for parts). Model in those units; `cqp` converts to mm on export. Don't scale manually.
- Z up. Plan view is `top` (+Y up). Name every part (`show_object(obj, name="rail")`) and give colours
  via `options={"color": "#rrggbb", "alpha": 0.4}`.
- Use faces/edges for reference geometry (planes, boundary lines); solids for real things.
- Identical parts: name them `part_0`, `part_1` — the parts table groups them with a quantity.
- Print useful numbers from the model (clearances, areas); they show in `cqp build` output.
- Only `models/*.py` not starting with `_` are built. Shared code goes in `models/_common.py` and is imported.
- Don't commit `build/`, `_site/`, or preview PNGs (git-ignored).
- Project-specific extras (e.g. a pyvista render) go in `projects/<slug>/scripts/` and are optional.

## Environment

`pip install -e ".[dev]"` in a venv. If a `pip install` stalls on the large OCP wheel, retry with
`pip install --default-timeout 30 --retries 5 …`.

## Publishing

GitHub Pages from the `gh-pages` branch: `main` at the site root, each PR at `/pr-<n>/` (see `.github/workflows/site.yml`).
Links in the site are relative — never use absolute `/…` URLs in generated HTML.
