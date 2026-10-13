"""Live viewer: serves viewer/, builds GLBs on request (per variant) and reloads on changes."""

from __future__ import annotations

import json
import queue
import tempfile
import threading
from pathlib import Path

from flask import Flask, Response, jsonify, redirect, request, send_from_directory
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from .loader import ModelError, load_model
from .project import REPO_ROOT, Project, ProjectError, load_project

VIEWER_DIR = REPO_ROOT / "viewer"


def _glb_bytes(model) -> bytes:
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "m.glb"
        model.assembly.export(str(p), exportType="GLTF", binary=True)
        return p.read_bytes()


def create_app(project: Project) -> Flask:
    app = Flask(__name__, static_folder=None)
    # (variant slug or "" for the PARAMS defaults, model name) -> built GLB / last error.
    # Entries are built on request and marked dirty (not dropped) when sources change, so a
    # failed rebuild can still show the previous model.
    state: dict[tuple[str, str], dict] = {}
    build_lock = threading.Lock()      # load_model redirects stdout, so builds must not overlap
    clients: list[queue.Queue] = []
    lock = threading.Lock()

    def push(event: str, data: dict):
        msg = f"event: {event}\ndata: {json.dumps(data)}\n\n"
        with lock:
            for c in clients:
                c.put(msg)

    def variants_info() -> list[dict]:
        try:
            return [{"slug": v.slug, "title": v.title, "description": v.description,
                     "params": v.params} for v in project.variants]
        except ProjectError as e:
            print(f"  ✗ project.toml: {e}")
            return []

    def model_path(name: str) -> Path | None:
        return next((f for f in project.model_files() if f.stem == name), None)

    def ensure(variant: str, name: str) -> dict:
        """Build (variant, model) if it is missing or dirty; returns its state entry."""
        with build_lock:
            entry = state.setdefault((variant, name), {"glb": None, "error": None, "dirty": True})
            if not entry["dirty"]:
                return entry
            path = model_path(name)
            label = f"{name}[{variant}]" if variant else name
            try:
                if path is None:
                    raise ModelError(f"no model named '{name}'")
                overrides = project.variant(variant).params if variant else None
                entry["glb"] = _glb_bytes(load_model(path, project.scale_to_mm, overrides))
                entry["error"] = None
                print(f"  ✓ {label}")
            except Exception as e:
                entry["error"] = str(e) if isinstance(e, (ModelError, ProjectError)) \
                    else f"{type(e).__name__}: {e}"
                print(f"  ✗ {label}: {entry['error']}")
            entry["dirty"] = False
            return entry

    def mark_dirty(model: str | None = None):
        for (_, name), entry in state.items():
            if model is None or name == model:
                entry["dirty"] = True

    def reload_config() -> bool:
        try:
            project.config = load_project(project.slug, project.path.parent).config
            _ = project.variants   # validate
        except Exception as e:
            print(f"  ✗ project.toml: {e} (keeping the previous configuration)")
            return False
        return True

    class Handler(FileSystemEventHandler):
        def on_modified(self, event):
            p = Path(event.src_path)
            if p.name == "project.toml":
                if reload_config():
                    print("  project.toml reloaded")
                    mark_dirty()
                    push("reload", {})
            elif p.suffix == ".py" and p.parent == project.models_dir:
                # helper modules may be imported by several models: rebuild everything
                mark_dirty(None if p.name.startswith("_") else p.stem)
                push("changed", {"model": None if p.name.startswith("_") else p.stem})

        on_created = on_modified

    observer = Observer()
    observer.schedule(Handler(), str(project.models_dir), recursive=False)
    observer.schedule(Handler(), str(project.path), recursive=False)
    observer.daemon = True
    observer.start()

    @app.get("/")
    def index():
        if not request.args.get("live"):
            extra = f"&variant={request.args['variant']}" if request.args.get("variant") else ""
            return redirect(f"/?live=1{extra}")
        return send_from_directory(VIEWER_DIR, "index.html")

    @app.get("/vendor/<path:p>")
    def vendor(p):
        return send_from_directory(VIEWER_DIR / "vendor", p)

    @app.get("/status")
    def status():
        return jsonify(
            project=project.title,
            background=project.background,
            models=[f.stem for f in project.model_files()],
            variants=variants_info(),
        )

    @app.get("/model.glb")
    def model_glb():
        names = [f.stem for f in project.model_files()]
        name = request.args.get("model") or (names[0] if names else "")
        variant = request.args.get("variant", "")
        if variant and variant not in {v["slug"] for v in variants_info()}:
            return Response(f"no variant '{variant}'", status=404)
        entry = ensure(variant, name)
        if entry["error"]:
            return Response(entry["error"], status=500, mimetype="text/plain")
        return Response(entry["glb"], mimetype="model/gltf-binary")

    @app.get("/events")
    def events():
        q: queue.Queue = queue.Queue()
        with lock:
            clients.append(q)

        def stream():
            try:
                yield f"event: config\ndata: {json.dumps({'background': project.background})}\n\n"
                while True:
                    try:
                        yield q.get(timeout=15)
                    except queue.Empty:
                        yield ": keepalive\n\n"
            finally:
                with lock:
                    clients.remove(q)

        return Response(stream(), mimetype="text/event-stream",
                        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    return app


def serve(project: Project, port: int = 5001, variant: str | None = None):
    if variant:
        project.variant(variant)       # fail fast on a typo
    app = create_app(project)
    suffix = f"&variant={variant}" if variant else ""
    print(f"Serving '{project.slug}' at http://localhost:{port}/?live=1{suffix}  (Ctrl-C to stop)")
    if project.variants:
        print("  variants: " + ", ".join(v.slug for v in project.variants)
              + "  (switch in the viewer; models build when first shown)")
    app.run(host="127.0.0.1", port=port, threaded=True, debug=False)
