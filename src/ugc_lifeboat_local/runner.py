from __future__ import annotations

import json
import shutil
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import duckdb

from ugc_lifeboat_local.archive import archive_creator, extract_manifest, verify_bundle
from ugc_lifeboat_local.fixtures import fixture_path, load_catalog
from ugc_lifeboat_local.models import ArchiveSummary, BulkExportSummary, project_root

try:
    import fcntl
except ImportError:  # pragma: no cover
    fcntl = None


def runs_dir() -> Path:
    return project_root() / "runs" / "latest"


def outputs_dir() -> Path:
    return project_root() / "outputs"


def init_demo(force: bool = False) -> None:
    with _workspace_lock():
        _init_demo_unlocked(force=force)


def _init_demo_unlocked(force: bool = False) -> None:
    if force:
        shutil.rmtree(runs_dir(), ignore_errors=True)
        shutil.rmtree(outputs_dir(), ignore_errors=True)
    runs_dir().mkdir(parents=True, exist_ok=True)
    outputs_dir().mkdir(parents=True, exist_ok=True)
    _connect().close()


def archive(creator_id: str) -> ArchiveSummary:
    with _workspace_lock():
        _init_demo_unlocked(force=False)
        summary = archive_creator(creator_id, outputs_dir() / f"{creator_id}.rrcustomroom")
        _write_archive_summary(summary)
        _write_db([summary])
        return summary


def bulk_export() -> BulkExportSummary:
    with _workspace_lock():
        return _bulk_export_unlocked()


def _bulk_export_unlocked() -> BulkExportSummary:
    _init_demo_unlocked(force=True)
    catalog = load_catalog()
    summaries = [
        archive_creator(creator.id, outputs_dir() / f"{creator.id}.rrcustomroom", catalog=catalog)
        for creator in catalog.creators
    ]
    raw_bytes = sum(item.raw_bytes for item in summaries)
    stored_bytes = sum(item.stored_bytes for item in summaries)
    summary = BulkExportSummary(
        run_id=summaries[0].run_id,
        creators=len(catalog.creators),
        rooms=sum(item.room_count for item in summaries),
        raw_bytes=raw_bytes,
        stored_bytes=stored_bytes,
        dedup_ratio=round(raw_bytes / stored_bytes, 4),
        completeness=round(min(item.completeness for item in summaries), 4),
        bundles=[item.bundle_path for item in summaries],
        pass_gates=all(item.pass_gates for item in summaries) and raw_bytes / stored_bytes >= 20,
    )
    (outputs_dir() / "bulk_manifest.json").write_text(summary.model_dump_json(indent=2), encoding="utf-8")
    _write_bundle_manifests(summary.bundles)
    _write_archive_summary(summaries[0])
    _write_db(summaries)
    return summary


def verify_outputs() -> tuple[bool, dict[str, Any]]:
    with _workspace_lock():
        bulk_path = outputs_dir() / "bulk_manifest.json"
        if not bulk_path.exists():
            return False, {"error": "bulk-export has not produced bulk_manifest.json"}
        bulk = BulkExportSummary.model_validate_json(bulk_path.read_text(encoding="utf-8"))
        bundle_paths = [Path(path) for path in bulk.bundles]
        manifests = [extract_manifest(path) for path in bundle_paths]
        _write_db_from_manifests(bulk.run_id, bundle_paths, manifests)
        con = _connect()
        try:
            bundle_rows = con.execute("select count(*) from bundles").fetchone()[0]
            room_rows = con.execute("select count(*) from rooms").fetchone()[0]
            blob_rows = con.execute("select count(*) from blobs").fetchone()[0]
        finally:
            con.close()
        checks = {
            "bundle_files_exist": all(path.exists() for path in bundle_paths),
            "bundle_signatures_valid": all(verify_bundle(path) for path in bundle_paths),
            "descriptor_included": all(manifest.descriptor_blob_id in {blob.blob_id for blob in manifest.blobs} for manifest in manifests),
            "completeness_gate": bulk.completeness == 1,
            "dedup_ratio_gate": bulk.dedup_ratio >= 20,
            "db_bundle_rows": bundle_rows == len(bundle_paths),
            "db_room_rows": room_rows == bulk.rooms,
            "db_blob_rows": blob_rows >= len(bundle_paths),
            "dashboard_or_core_outputs": (outputs_dir() / "bulk_manifest.json").exists()
            and (outputs_dir() / "archive_manifest.json").exists(),
            "overall_pass": bulk.pass_gates,
        }
        checks["overall_pass"] = all(checks.values())
        return checks["overall_pass"], checks


def benchmark(iterations: int = 50) -> BulkExportSummary:
    result: BulkExportSummary | None = None
    for _ in range(iterations):
        result = bulk_export()
    if result is None:
        raise ValueError("iterations must be positive")
    return result


def export_demo_pack() -> Path:
    with _workspace_lock():
        if not (outputs_dir() / "bulk_manifest.json").exists():
            _bulk_export_unlocked()
        pack = outputs_dir() / "demo_pack"
        shutil.rmtree(pack, ignore_errors=True)
        pack.mkdir(parents=True, exist_ok=True)
        for source in [
            fixture_path(),
            outputs_dir() / "archive_manifest.json",
            outputs_dir() / "bundle_manifests.json",
            outputs_dir() / "bulk_manifest.json",
        ]:
            shutil.copy2(source, pack / source.name)
        for bundle in sorted(outputs_dir().glob("*.rrcustomroom")):
            shutil.copy2(bundle, pack / bundle.name)
        (pack / "manifest.json").write_text(
            json.dumps(
                {
                    "artifact": "ugc-lifeboat-local demo pack",
                    "contents": sorted(path.name for path in pack.iterdir()),
                    "data": "synthetic only",
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        return pack


def _write_archive_summary(summary: ArchiveSummary) -> None:
    (outputs_dir() / "summary.json").write_text(summary.model_dump_json(indent=2), encoding="utf-8")
    if Path(summary.bundle_path).exists():
        manifest = extract_manifest(Path(summary.bundle_path))
        (outputs_dir() / "archive_manifest.json").write_text(manifest.model_dump_json(indent=2), encoding="utf-8")


def _write_bundle_manifests(bundle_paths: list[str]) -> None:
    manifests = [
        {
            "path": Path(bundle_path).name,
            "manifest": extract_manifest(Path(bundle_path)).model_dump(mode="json"),
        }
        for bundle_path in bundle_paths
    ]
    (outputs_dir() / "bundle_manifests.json").write_text(json.dumps(manifests, indent=2), encoding="utf-8")


def _write_db(summaries: list[ArchiveSummary]) -> None:
    manifests = [extract_manifest(Path(summary.bundle_path)) for summary in summaries]
    _write_db_from_manifests(summaries[0].run_id, [Path(summary.bundle_path) for summary in summaries], manifests)


def _write_db_from_manifests(run_id: str, bundle_paths: list[Path], manifests: list[Any]) -> None:
    con = _connect()
    try:
        con.execute("delete from bundles")
        con.execute("delete from rooms")
        con.execute("delete from blobs")
        for bundle_path, manifest in zip(bundle_paths, manifests, strict=True):
            con.execute(
                "insert into bundles values (?, ?, ?, ?, ?, ?, ?)",
                [
                    run_id,
                    manifest.creator_id,
                    str(bundle_path),
                    manifest.room_count,
                    manifest.raw_bytes,
                    manifest.stored_bytes,
                    manifest.dedup_ratio,
                ],
            )
            for room in manifest.rooms:
                con.execute(
                    "insert into rooms values (?, ?, ?, ?)",
                    [run_id, manifest.creator_id, room.room_id, len(room.missing_asset_ids) == 0],
                )
            for blob in manifest.blobs:
                con.execute(
                    "insert into blobs values (?, ?, ?, ?, ?, ?)",
                    [run_id, manifest.creator_id, blob.blob_id, blob.kind, blob.raw_bytes, blob.stored_bytes],
                )
    finally:
        con.close()


def _connect() -> duckdb.DuckDBPyConnection:
    runs_dir().mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(runs_dir() / "lifeboat.duckdb"))
    con.execute(
        """
        create table if not exists bundles (
            run_id varchar,
            creator_id varchar,
            bundle_path varchar,
            room_count integer,
            raw_bytes integer,
            stored_bytes integer,
            dedup_ratio double
        )
        """
    )
    con.execute(
        """
        create table if not exists rooms (
            run_id varchar,
            creator_id varchar,
            room_id varchar,
            complete boolean
        )
        """
    )
    con.execute(
        """
        create table if not exists blobs (
            run_id varchar,
            creator_id varchar,
            blob_id varchar,
            kind varchar,
            raw_bytes integer,
            stored_bytes integer
        )
        """
    )
    return con


@contextmanager
def _workspace_lock() -> Any:
    lock_path = project_root() / ".ugc-lifeboat.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+", encoding="utf-8") as handle:
        if fcntl is not None:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            if fcntl is not None:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
