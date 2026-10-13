"""Project discovery and configuration (projects/<slug>/project.toml)."""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PROJECTS_DIR = REPO_ROOT / "projects"
BUILD_DIR = REPO_ROOT / "build"

# Millimetres per model unit.
UNIT_TO_MM = {"mm": 1.0, "cm": 10.0, "m": 1000.0, "in": 25.4, "ft": 304.8}
DEFAULT_VIEWS = ["iso", "front", "side", "top"]


class ProjectError(Exception):
    pass


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


@dataclass
class Variant:
    """A named set of parameter overrides; the project is built and published once per variant.

    Configured in project.toml as ``[[variants]]`` tables with ``slug``, ``title``, optional
    ``description`` and ``params`` (overrides applied to every model that has those PARAMS).
    """

    slug: str
    title: str
    description: str = ""
    params: dict = field(default_factory=dict)


@dataclass
class Project:
    slug: str
    path: Path
    config: dict = field(default_factory=dict)

    @property
    def title(self) -> str:
        return self.config.get("title") or self.slug.replace("-", " ").title()

    @property
    def description(self) -> str:
        return self.config.get("description", "")

    @property
    def tags(self) -> list[str]:
        return list(self.config.get("tags", []))

    @property
    def units(self) -> str:
        return self.config.get("units", "mm")

    @property
    def scale_to_mm(self) -> float:
        try:
            return UNIT_TO_MM[self.units]
        except KeyError:
            raise ProjectError(
                f"{self.slug}: unknown units '{self.units}' (use one of {', '.join(UNIT_TO_MM)})"
            ) from None

    @property
    def views(self) -> list[str]:
        return list(self.config.get("views", DEFAULT_VIEWS))

    @property
    def background(self) -> str | None:
        return self.config.get("background")

    @property
    def bom(self) -> list[dict]:
        return list(self.config.get("bom", []))

    @property
    def variants(self) -> list[Variant]:
        out = []
        for i, v in enumerate(self.config.get("variants", [])):
            title = v.get("title") or v.get("slug") or f"Variant {i + 1}"
            slug = v.get("slug") or slugify(title)
            if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", slug):
                raise ProjectError(f"{self.slug}: variant slug '{slug}' must be lower-case a-z, 0-9, -")
            if slug in {x.slug for x in out}:
                raise ProjectError(f"{self.slug}: duplicate variant slug '{slug}'")
            params = v.get("params", {})
            if not isinstance(params, dict):
                raise ProjectError(f"{self.slug}: variant '{slug}' params must be a table")
            out.append(Variant(slug, title, v.get("description", ""), dict(params)))
        return out

    def variant(self, slug: str) -> Variant:
        for v in self.variants:
            if v.slug == slug:
                return v
        names = ", ".join(v.slug for v in self.variants) or "none configured"
        raise ProjectError(f"{self.slug}: no variant '{slug}' (variants: {names})")

    @property
    def models_dir(self) -> Path:
        return self.path / "models"

    @property
    def build_dir(self) -> Path:
        return BUILD_DIR / self.slug

    def model_files(self) -> list[Path]:
        """All model scripts, sorted by name. Files starting with '_' are helpers."""
        if not self.models_dir.is_dir():
            return []
        return sorted(p for p in self.models_dir.glob("*.py") if not p.name.startswith("_"))

    def model_options(self, stem: str) -> dict:
        return dict(self.config.get("models", {}).get(stem, {}))

    def readme(self) -> str:
        p = self.path / "README.md"
        return p.read_text(encoding="utf-8") if p.exists() else ""


def load_project(slug: str, projects_dir: Path | None = None) -> Project:
    path = (projects_dir or PROJECTS_DIR) / slug
    if not path.is_dir():
        raise ProjectError(f"project '{slug}' not found in {path.parent}")
    cfg_path = path / "project.toml"
    config = {}
    if cfg_path.exists():
        with cfg_path.open("rb") as f:
            config = tomllib.load(f)
    return Project(slug=slug, path=path, config=config)


def all_projects(projects_dir: Path | None = None) -> list[Project]:
    root = projects_dir or PROJECTS_DIR
    if not root.is_dir():
        return []
    return [
        load_project(p.name, root)
        for p in sorted(root.iterdir())
        if p.is_dir() and not p.name.startswith(("_", ".")) and (p / "models").is_dir()
    ]
