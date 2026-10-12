"""`cqp` command line interface."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import scaffold
from .project import PROJECTS_DIR, ProjectError, all_projects, load_project


def _projects(args):
    if getattr(args, "all", False) or not getattr(args, "slug", None):
        return all_projects()
    return [load_project(args.slug)]


def cmd_new(args):
    path = scaffold.new_project(args.name, units=args.units, tags=args.tag)
    print(f"Created {path.relative_to(PROJECTS_DIR.parent)}")
    print(f"  edit models/ then run: cqp build {path.name} && cqp render {path.name}")


def cmd_build(args):
    from .build import build_project, info_text

    failed = 0
    for p in _projects(args):
        r = build_project(p, only=args.model, variant=getattr(args, "variant", None),
                          render=not args.no_render)
        print(info_text(p, r))
        failed += not r.ok
    if failed:
        print(f"\n{failed} project(s) failed", file=sys.stderr)
    return 1 if failed else 0


def cmd_render(args):
    from .build import write_preview_png

    p = load_project(args.slug)
    views = args.view or ["iso"]
    for v in views:
        path = write_preview_png(p, v, args.model, args.variant)
        print(f"wrote {path}")


def cmd_site(args):
    from .site import build_site

    base = args.out
    projects = build_site(Path(base), only=args.only, rebuild=args.rebuild)
    print(f"Site written to {base}/ ({len(projects)} project(s))")


def cmd_serve(args):
    from .server import serve

    serve(load_project(args.slug), port=args.port)


def cmd_check(args):
    args.all = True
    args.model = None
    args.no_render = False
    args.slug = None
    args.variant = None
    return cmd_build(args)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="cqp", description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("new", help="scaffold a project")
    s.add_argument("name")
    s.add_argument("--units", default="mm", choices=["mm", "cm", "m", "in", "ft"])
    s.add_argument("--tag", action="append", default=[])
    s.set_defaults(fn=cmd_new)

    s = sub.add_parser("build", help="run models, export STEP/STL/GLB, render drawings")
    s.add_argument("slug", nargs="?")
    s.add_argument("--all", action="store_true")
    s.add_argument("--model")
    s.add_argument("--no-render", action="store_true")
    s.add_argument("--variant", help="build only this variant (no manifest is written)")
    s.set_defaults(fn=cmd_build)

    s = sub.add_parser("render", help="write preview PNG(s) to projects/<slug>/")
    s.add_argument("slug")
    s.add_argument("--view", action="append", help="iso, front, back, side, left, top, bottom")
    s.add_argument("--model")
    s.add_argument("--variant", help="apply a variant's parameters (default: PARAMS defaults)")
    s.set_defaults(fn=cmd_render)

    s = sub.add_parser("serve", help="live 3D viewer that reloads on save")
    s.add_argument("slug")
    s.add_argument("--port", type=int, default=5001)
    s.set_defaults(fn=cmd_serve)

    s = sub.add_parser("site", help="build the static site (viewer + drawings)")
    s.add_argument("--out", default="_site")
    s.add_argument("--only", help="comma separated slugs")
    s.add_argument("--rebuild", action="store_true", help="ignore existing build/ outputs")
    s.set_defaults(fn=cmd_site)

    s = sub.add_parser("check", help="build everything (CI entrypoint)")
    s.set_defaults(fn=cmd_check)

    args = ap.parse_args(argv)
    try:
        return args.fn(args) or 0
    except ProjectError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
