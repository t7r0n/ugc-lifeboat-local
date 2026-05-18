from __future__ import annotations

import json
import subprocess
import zipfile

from ugc_lifeboat_local.archive import extract_manifest, verify_bundle
from ugc_lifeboat_local.dashboard import build_dashboard
from ugc_lifeboat_local.runner import archive, bulk_export, export_demo_pack, outputs_dir, verify_outputs


def test_archive_bundle_is_signed_complete_and_deduplicated() -> None:
    summary = archive("creator-alba")
    assert summary.pass_gates
    assert summary.dedup_ratio >= 20
    assert summary.completeness == 1
    assert verify_bundle(outputs_dir() / "creator-alba.rrcustomroom")


def test_bundle_contains_descriptor_viewer_and_hashed_blobs() -> None:
    archive("creator-alba")
    path = outputs_dir() / "creator-alba.rrcustomroom"
    manifest = extract_manifest(path)
    with zipfile.ZipFile(path) as bundle:
        names = set(bundle.namelist())
    assert "descriptor_set.binpb" in names
    assert "viewer.html" in names
    assert all(f"blobs/{blob.blob_id}.bin" in names for blob in manifest.blobs)


def test_bulk_export_verify_dashboard_and_demo_pack() -> None:
    summary = bulk_export()
    assert summary.pass_gates
    ok, checks = verify_outputs()
    assert ok, checks
    dashboard = build_dashboard()
    assert "UGC Lifeboat Dashboard" in dashboard.read_text(encoding="utf-8")
    pack = export_demo_pack()
    assert (pack / "manifest.json").exists()


def test_verify_detects_tampered_bundle() -> None:
    archive("creator-alba")
    path = outputs_dir() / "creator-alba.rrcustomroom"
    tampered = outputs_dir() / "tampered.rrcustomroom"
    assert verify_bundle(path)
    with zipfile.ZipFile(path) as source, zipfile.ZipFile(tampered, mode="w") as target:
        for name in source.namelist():
            if name != "manifest.json":
                target.writestr(name, source.read(name))
        target.writestr("manifest.json", "{}")
    assert not verify_bundle(tampered)


def test_jsonl_tool_loop() -> None:
    payload = {"tool": "archive", "arguments": {"creator": "creator-alba"}}
    completed = subprocess.run(
        ["uv", "run", "--project", "elite_projects/ugc-lifeboat-local", "ugc-lifeboat", "tool-loop"],
        input=json.dumps(payload) + "\n",
        text=True,
        capture_output=True,
        check=True,
    )
    result = json.loads(completed.stdout)
    assert result["creator_id"] == "creator-alba"
    assert result["signature_valid"]
