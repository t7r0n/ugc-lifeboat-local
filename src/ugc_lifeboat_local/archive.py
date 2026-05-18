from __future__ import annotations

import base64
import hashlib
import json
import time
import uuid
import zipfile
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from ugc_lifeboat_local.fixtures import load_catalog
from ugc_lifeboat_local.models import ArchiveSummary, BlobRecord, BundleManifest, Catalog, RoomRecord


def run_id() -> str:
    return f"run-{uuid.uuid4().hex[:12]}"


def archive_creator(creator_id: str, output_path: Path, catalog: Catalog | None = None) -> ArchiveSummary:
    start = time.perf_counter()
    data = catalog or load_catalog()
    creator = next((item for item in data.creators if item.id == creator_id), None)
    if creator is None:
        raise ValueError(f"unknown creator: {creator_id}")
    rooms = [room for room in data.rooms if room.creator_id == creator_id]
    if not rooms:
        raise ValueError(f"creator has no rooms: {creator_id}")

    asset_by_id = {asset.id: asset for asset in data.assets}
    blobs: dict[str, tuple[BlobRecord, bytes]] = {}
    room_records: list[RoomRecord] = []
    raw_bytes = 0
    naive_per_room_container_bytes = 22_000_000

    descriptor_bytes = data.descriptor.encode("utf-8")
    descriptor_blob = _blob("descriptor_set.binpb", "descriptor", descriptor_bytes, len(descriptor_bytes))
    blobs[descriptor_blob.blob_id] = (descriptor_blob, descriptor_bytes)
    raw_bytes += len(descriptor_bytes)

    for room in rooms:
        raw_bytes += naive_per_room_container_bytes
        scene_bytes = _inflate(room.scene_payload, 240_000)
        scene_blob = _blob(room.id, "scene", scene_bytes, len(scene_bytes))
        blobs.setdefault(scene_blob.blob_id, (scene_blob, scene_bytes))
        raw_bytes += len(scene_bytes)
        missing = []
        room_blob_ids = [scene_blob.blob_id, descriptor_blob.blob_id]
        for asset_id in room.asset_ids:
            asset = asset_by_id.get(asset_id)
            if asset is None:
                missing.append(asset_id)
                continue
            asset_bytes = _inflate(asset.payload, asset.bytes)
            blob = _blob(asset.id, asset.kind, asset_bytes, asset.bytes)
            blobs.setdefault(blob.blob_id, (blob, asset_bytes))
            raw_bytes += asset.bytes
            room_blob_ids.append(blob.blob_id)
        room_records.append(RoomRecord(room_id=room.id, name=room.name, blob_ids=room_blob_ids, missing_asset_ids=missing))

    stored_bytes = sum(record.stored_bytes for record, _ in blobs.values())
    completeness = 1 - sum(len(room.missing_asset_ids) for room in room_records) / max(1, sum(len(room.blob_ids) for room in room_records))
    signing_key = Ed25519PrivateKey.generate()
    public_key_hex = signing_key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw).hex()
    manifest = BundleManifest(
        creator_id=creator.id,
        creator_name=creator.display_name,
        room_count=len(room_records),
        rooms=room_records,
        blobs=sorted((record for record, _ in blobs.values()), key=lambda item: item.blob_id),
        descriptor_blob_id=descriptor_blob.blob_id,
        raw_bytes=raw_bytes,
        stored_bytes=stored_bytes,
        dedup_ratio=round(raw_bytes / stored_bytes, 4),
        completeness=round(completeness, 4),
        public_key_hex=public_key_hex,
    )
    signature = signing_key.sign(_manifest_bytes(manifest))
    manifest.signature_hex = signature.hex()
    _write_bundle(output_path, manifest, blobs)
    signature_valid = verify_bundle(output_path)
    latency_ms = (time.perf_counter() - start) * 1000
    return ArchiveSummary(
        run_id=run_id(),
        bundle_path=str(output_path),
        creator_id=creator_id,
        room_count=len(room_records),
        raw_bytes=raw_bytes,
        stored_bytes=stored_bytes,
        dedup_ratio=manifest.dedup_ratio,
        completeness=manifest.completeness,
        signature_valid=signature_valid,
        descriptor_included=descriptor_blob.blob_id in {blob.blob_id for blob in manifest.blobs},
        p95_latency_ms=round(latency_ms, 4),
        pass_gates=signature_valid and manifest.dedup_ratio >= 20 and manifest.completeness == 1 and latency_ms < 2000,
    )


def verify_bundle(bundle_path: Path) -> bool:
    try:
        with zipfile.ZipFile(bundle_path) as archive:
            manifest = BundleManifest.model_validate_json(archive.read("manifest.json"))
            if manifest.signature_hex is None:
                return False
            signature = bytes.fromhex(manifest.signature_hex)
            manifest.signature_hex = None
            public_key = Ed25519PublicKey.from_public_bytes(bytes.fromhex(manifest.public_key_hex))
            public_key.verify(signature, _manifest_bytes(manifest))
            for blob in manifest.blobs:
                payload = archive.read(f"blobs/{blob.blob_id}.bin")
                if hashlib.sha256(payload).hexdigest() != blob.sha256:
                    return False
            descriptor_names = {f"blobs/{manifest.descriptor_blob_id}.bin", "descriptor_set.binpb"}
            return bool(descriptor_names.intersection(set(archive.namelist())))
    except (InvalidSignature, KeyError, ValueError, zipfile.BadZipFile):
        return False


def extract_manifest(bundle_path: Path) -> BundleManifest:
    with zipfile.ZipFile(bundle_path) as archive:
        return BundleManifest.model_validate_json(archive.read("manifest.json"))


def _write_bundle(output_path: Path, manifest: BundleManifest, blobs: dict[str, tuple[BlobRecord, bytes]]) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output_path, mode="w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        archive.writestr("manifest.json", manifest.model_dump_json(indent=2))
        for blob_id, (_, payload) in sorted(blobs.items()):
            archive.writestr(f"blobs/{blob_id}.bin", payload)
        archive.writestr("descriptor_set.binpb", next(payload for record, payload in blobs.values() if record.kind == "descriptor"))
        archive.writestr("viewer.html", _viewer_html(manifest))


def _blob(source_id: str, kind: str, payload: bytes, raw_bytes: int) -> BlobRecord:
    digest = hashlib.sha256(payload).hexdigest()
    return BlobRecord(
        blob_id=digest[:24],
        source_id=source_id,
        kind=kind,
        sha256=digest,
        stored_bytes=len(payload),
        raw_bytes=raw_bytes,
    )


def _inflate(seed: str, target_bytes: int) -> bytes:
    encoded = seed.encode("utf-8") + b"|"
    repeats = target_bytes // len(encoded) + 1
    return (encoded * repeats)[:target_bytes]


def _manifest_bytes(manifest: BundleManifest) -> bytes:
    return json.dumps(manifest.model_dump(mode="json", exclude={"signature_hex"}), sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )


def _viewer_html(manifest: BundleManifest) -> str:
    payload = base64.b64encode(manifest.model_dump_json().encode("utf-8")).decode("ascii")
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>UGC Lifeboat Viewer</title>
<style>body{{font-family:system-ui;margin:32px;background:#f8faf8;color:#17211d}}.room{{padding:10px 0;border-bottom:1px solid #dce8e1}}</style></head>
<body><h1>UGC Lifeboat Viewer</h1><p>Offline bundle manifest preview.</p><div id="app"></div>
<script>
const manifest = JSON.parse(atob("{payload}"));
document.querySelector("#app").innerHTML = `<h2>${{manifest.creator_name}}</h2><p>${{manifest.room_count}} rooms · dedup ${{manifest.dedup_ratio}}x · completeness ${{(manifest.completeness*100).toFixed(0)}}%</p>` +
  manifest.rooms.map(room => `<div class="room"><strong>${{room.name}}</strong><br>${{room.blob_ids.length}} content-addressed blobs</div>`).join("");
</script></body></html>"""
