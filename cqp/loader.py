"""Model loading.

A model file provides its geometry in any of these ways (checked in order):

1. calls ``show_object(obj, name=..., options={"color": ..., "alpha": ...})``
   (also works unchanged in CQ-editor / ocp_vscode, which provide their own);
2. defines a module-level ``result`` / ``show_object`` variable
   (Workplane | Shape | Assembly);
3. defines ``build(**PARAMS)`` returning one of the above.

``PARAMS = {...}`` at module level documents the parametric inputs.
Several shown objects are combined into one ``cq.Assembly``.

Parameter overrides (project variants) need ``build()``: the file runs as usual, then its
geometry and output are discarded and ``build(**{**PARAMS, **overrides})`` is called instead.
``build`` may call ``show_object`` itself (for named / coloured parts) or return the geometry.
Only override keys that appear in the model's PARAMS are applied.
"""

from __future__ import annotations

import io
import runpy
import sys
from contextlib import redirect_stdout
from dataclasses import dataclass, field
from pathlib import Path

import cadquery as cq


class ModelError(Exception):
    pass


@dataclass
class Model:
    name: str
    path: Path
    assembly: cq.Assembly
    params: dict = field(default_factory=dict)
    log: str = ""
    overrides: dict = field(default_factory=dict)   # the variant overrides applied to params

    def compound(self) -> cq.Compound:
        return self.assembly.toCompound()

    def parts(self) -> list[tuple[str, cq.Shape, cq.Color | None]]:
        """Leaf parts as (name, world-space shape, colour)."""
        out = []
        for child in _leaves(self.assembly):
            if child.obj is None:
                continue
            for i, shape in enumerate(child.shapes):
                world = shape.located(child.loc) if child.loc is not None else shape
                name = child.name if len(child.shapes) == 1 else f"{child.name}_{i}"
                out.append((name, world, child.color))
        return out


def _leaves(assy: cq.Assembly):
    """Leaf nodes with *world* locations (cq.Assembly.traverse resolves parents)."""
    for child, loc in _walk(assy, cq.Location()):
        if not child.children:
            leaf = _Leaf(child.name, child.color, child.obj, child.shapes, loc)
            yield leaf


@dataclass
class _Leaf:
    name: str
    color: cq.Color | None
    obj: object
    shapes: list
    loc: cq.Location


def _walk(node: cq.Assembly, parent_loc: cq.Location):
    loc = parent_loc * node.loc
    yield node, loc
    for c in node.children:
        yield from _walk(c, loc)


def _as_shape(obj) -> cq.Shape:
    if isinstance(obj, cq.Workplane):
        vals = obj.vals()
        if len(vals) == 1:
            return vals[0]
        return cq.Compound.makeCompound(
            [v for v in vals if isinstance(v, cq.Shape)]
        )
    if isinstance(obj, cq.Shape):
        return obj
    raise ModelError(f"unsupported object type for display: {type(obj).__name__}")


def _color(options: dict | None) -> cq.Color | None:
    if not options:
        return None
    c = options.get("color")
    alpha = options.get("alpha", 1.0)
    if c is None and alpha == 1.0:
        return None
    if isinstance(c, str):
        c = _parse_color(c, alpha)
        return c
    if isinstance(c, (tuple, list)):
        return cq.Color(*c, alpha) if len(c) == 3 else cq.Color(*c)
    return cq.Color(0.7, 0.7, 0.7, alpha)


def _parse_color(s: str, alpha: float) -> cq.Color:
    if s.startswith("#") and len(s) == 7:
        r, g, b = (int(s[i : i + 2], 16) / 255 for i in (1, 3, 5))
        return cq.Color(r, g, b, alpha)
    return cq.Color(s)


def _assemble(shown: list[tuple[object, str | None, dict | None]], fallback: str) -> cq.Assembly:
    if len(shown) == 1 and isinstance(shown[0][0], cq.Assembly):
        return shown[0][0]
    root = cq.Assembly(name="root")
    used: dict[str, int] = {}
    for i, (obj, name, options) in enumerate(shown):
        if isinstance(obj, cq.Assembly):
            root.add(obj, name=name or f"assembly_{i}")
            continue
        base = name or (f"part_{i}" if len(shown) > 1 else fallback)
        n = used.get(base, 0)
        used[base] = n + 1
        root.add(_as_shape(obj), name=base if n == 0 else f"{base}_{n}", color=_color(options))
    return root


def load_model(path: Path, scale: float = 1.0, overrides: dict | None = None) -> Model:
    """Run a model file and return its assembly.

    ``scale`` converts model units to mm; it is applied to the geometry so that
    every downstream export (STEP, STL, GLB, drawings) is in millimetres.
    ``overrides`` replaces PARAMS values (keys the model doesn't have are ignored).
    """
    shown: list[tuple[object, str | None, dict | None]] = []

    def capture(obj, name=None, options=None, **_):
        shown.append((obj, name, options))
        return obj

    buf = io.StringIO()
    # Let models import sibling helper modules (e.g. `from bracket import build`).
    sys.path.insert(0, str(path.parent))
    try:
        with redirect_stdout(buf):
            ns = runpy.run_path(
                str(path), init_globals={"show_object": capture}, run_name="__cqp_model__"
            )
            params = dict(ns.get("PARAMS", {}))
            applied = {k: v for k, v in (overrides or {}).items() if k in params}
            if applied:
                if not callable(ns.get("build")):
                    raise ModelError(
                        f"{path.name}: parameter overrides {sorted(applied)} need a build() function"
                    )
                params.update(applied)
                shown.clear()
                buf.seek(0)
                buf.truncate()
                value = ns["build"](**params)
                if value is not None and not shown:
                    shown.append((value, None, None))
            elif not shown:
                value = ns.get("result")
                if value is None:
                    so = ns.get("show_object")
                    value = None if so is capture else so
                if value is None and callable(ns.get("build")):
                    value = ns["build"](**params)
                if value is not None:
                    shown.append((value, None, None))
    except ModelError:
        raise
    except Exception as e:  # surfaces as a build failure with the model name
        raise ModelError(f"{path.name}: {type(e).__name__}: {e}") from e
    finally:
        sys.path.remove(str(path.parent))

    if not shown:
        raise ModelError(
            f"{path.name}: no geometry found. Call show_object(...), set `result`, "
            "or define build()."
        )
    try:
        assy = _assemble(shown, path.stem)
        if scale != 1.0:
            assy = _scaled(assy, scale)
    except ModelError:
        raise
    except Exception as e:
        raise ModelError(f"{path.name}: could not assemble result: {e}") from e
    return Model(name=path.stem, path=path, assembly=assy, params=params, log=buf.getvalue(),
                 overrides=applied)


def _scaled(assy: cq.Assembly, scale: float) -> cq.Assembly:
    out = cq.Assembly(name="root")
    for child, loc in _walk(assy, cq.Location()):
        if child.children or child.obj is None:
            continue
        for i, shape in enumerate(child.shapes):
            world = shape.located(loc) if loc is not None else shape
            name = child.name if len(child.shapes) == 1 else f"{child.name}_{i}"
            out.add(world.scale(scale), name=name, color=child.color)
    return out
