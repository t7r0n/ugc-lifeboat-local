from __future__ import annotations

from pathlib import Path

from ugc_lifeboat_local.models import Catalog, project_root


def fixture_path() -> Path:
    return project_root() / "fixtures" / "catalog.json"


def load_catalog(path: Path | None = None) -> Catalog:
    return Catalog.model_validate_json((path or fixture_path()).read_text(encoding="utf-8"))

