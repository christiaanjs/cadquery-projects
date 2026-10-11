"""Live viewer: serves viewer/ and rebuilds GLBs when a model file changes."""

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
from .project import REPO_ROOT, Project

VIEWER_DIR = REPO_ROOT / "viewer"


def _glb_bytes(model) -> bytes:
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "m.glb"
        model.assembly.export(str(p), exportType="GLTF", binary=True)
        return p.read_bytes()


def create_app(project: Project) -> Flask:
    app = Flask(__name__, static_folder=None)
    state: dict[str, dict] = {}      # model name -> {"glb": bytes|None, "error": str|None}
    clients: list[queue.Queue] = []
    lock = threading.Lock()

    def push(event: str, data: dict):
        msg = f"event: {event}\ndata: {json.dumps(data)}\n\n"
        with lock:
            for c in clients:
                c.put(msg)

    def rebuild(path: Path):
        stem = path.stem
        try:
            glb = _glb_bytes(load_model(path, project.scale_to_mm))
            state[stem] = {"glb": glb, "error": None}
            print(f"  ✓ {path.name}")
            push("model", {"model": stem, "error": None})
        except Exception as e:
            msg = str(e) if isinstance(e, ModelError) else f"{type(e).__name__}: {e}"
            state[stem] = {"glb": state.get(stem, {}).get("glb"), "error": msg}
            print(f"  ✗ {path.name}: {msg}")
            push("model", {"model": stem, "error": msg})

    def rebuild_all():
        for f in project.model_files():
            rebuild(f)

    class Handler(FileSystemEventHandler):
        def on_modified(self, event):
            p = Path(event.src_path)
            if p.suffix == ".py":
                # helper modules may be imported by several models: rebuild everything
                (rebuild(p) if not p.name.startswith("_") else rebuild_all())

        on_created = on_modified

    observer = Observer()
    observer.schedule(Handler(), str(project.models_dir), recursive=False)
    observer.daemon = True
    observer.start()
    threading.Thread(target=rebuild_all, daemon=True).start()

    @app.get("/")
    def index():
        if not request.args.get("live"):
            return redirect("/?live=1")
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
            errors={k: v["error"] for k, v in state.items() if v["error"]},
            built=sorted(k for k, v in state.items() if v["glb"]),
        )

    @app.get("/model.glb")
    def model_glb():
        names = [f.stem for f in project.model_files()]
        name = request.args.get("model") or (names[0] if names else "")
        entry = state.get(name)
        if not entry or not entry["glb"]:
            return Response("model not built yet", status=404)
        return Response(entry["glb"], mimetype="model/gltf-binary")

    @app.get("/events")
    def events():
        q: queue.Queue = queue.Queue()
        with lock:
            clients.append(q)

        def stream():
            try:
                yield f"event: config\ndata: {json.dumps({'background': project.background})}\n\n"
                for name, entry in list(state.items()):
                    if entry["glb"] or entry["error"]:
                        yield f"event: model\ndata: {json.dumps({'model': name, 'error': entry['error']})}\n\n"
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


def serve(project: Project, port: int = 5001):
    app = create_app(project)
    print(f"Serving '{project.slug}' at http://localhost:{port}/?live=1  (Ctrl-C to stop)")
    app.run(host="127.0.0.1", port=port, threaded=True, debug=False)
