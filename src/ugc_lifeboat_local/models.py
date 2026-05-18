from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


class Creator(BaseModel):
    id: str
    display_name: str


class Asset(BaseModel):
    id: str
    kind: Literal["prefab", "material", "glb", "thumbnail"]
    bytes: int = Field(gt=0)
    payload: str


class Room(BaseModel):
    id: str
    creator_id: str
    name: str
    scene_payload: str
    asset_ids: list[str]


class Catalog(BaseModel):
    descriptor: str
    creators: list[Creator]
    assets: list[Asset]
    rooms: list[Room]


class BlobRecord(BaseModel):
    blob_id: str
    source_id: str
    kind: str
    sha256: str
    stored_bytes: int
    raw_bytes: int


class RoomRecord(BaseModel):
    room_id: str
    name: str
    blob_ids: list[str]
    missing_asset_ids: list[str] = Field(default_factory=list)


class BundleManifest(BaseModel):
    bundle_format: str = "rrcustomroom.local.v1"
    creator_id: str
    creator_name: str
    room_count: int
    rooms: list[RoomRecord]
    blobs: list[BlobRecord]
    descriptor_blob_id: str
    raw_bytes: int
    stored_bytes: int
    dedup_ratio: float
    completeness: float
    signature_algorithm: str = "ed25519"
    public_key_hex: str
    signature_hex: str | None = None


class ArchiveSummary(BaseModel):
    run_id: str
    bundle_path: str
    creator_id: str
    room_count: int
    raw_bytes: int
    stored_bytes: int
    dedup_ratio: float
    completeness: float
    signature_valid: bool
    descriptor_included: bool
    p95_latency_ms: float
    pass_gates: bool


class BulkExportSummary(BaseModel):
    run_id: str
    creators: int
    rooms: int
    raw_bytes: int
    stored_bytes: int
    dedup_ratio: float
    completeness: float
    bundles: list[str]
    pass_gates: bool

