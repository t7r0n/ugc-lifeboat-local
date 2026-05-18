# UGC Lifeboat Local

UGC Lifeboat Local is an offline reference implementation for preserving creator-owned user-generated worlds as portable, signed archive bundles.

The project uses deterministic synthetic fixtures. It does not call live platform APIs, does not require production object storage access, and contains no private creator data or credentials.

## Quick Start

```bash
uv sync
uv run ugc-lifeboat init-demo
uv run ugc-lifeboat archive --creator creator-alba
uv run ugc-lifeboat verify-bundle outputs/creator-alba.rrcustomroom
uv run ugc-lifeboat dashboard
```

Run the bulk export simulation:

```bash
uv run ugc-lifeboat bulk-export
uv run ugc-lifeboat verify
```

## What It Demonstrates

- Content-addressed packing for room scene blobs, descriptor sets, GLB geometry, prefabs, materials, and thumbnails.
- Cross-room asset deduplication with measured raw bytes vs unique stored bytes.
- Portable `.rrcustomroom` bundles with a detached Ed25519 signature and public verification key.
- Descriptor preservation so archived scene data remains decodable in the future.
- Static local viewer/dashboard with archive completeness, dedup ratio, and signature verification gates.

## Outputs

- `outputs/<creator>.rrcustomroom`
- `outputs/archive_manifest.json`
- `outputs/bulk_manifest.json`
- `outputs/summary.json`
- `outputs/dashboard.html`
- `outputs/demo_pack/`

