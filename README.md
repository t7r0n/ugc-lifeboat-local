# UGC Lifeboat Local

UGC Lifeboat Local is an offline reference implementation for preserving creator-owned user-generated worlds as portable, signed archive bundles.

The project uses deterministic synthetic fixtures. It does not call live platform APIs, does not require production object storage access, and contains no private creator data or credentials.

## Problem shape

Offline UGC archive bundler with content-addressed deduplication and signed portable bundles.

## What the harness exercises

- Models the `ugc-lifeboat-local` workflow with deterministic fixtures and seeded failure cases.
- Turns the core claim in `UGC Lifeboat Local` into explicit gates that can fail a local run.
- Stores enough `UGC Lifeboat Local` evidence for a reviewer to inspect the decision path.
- Keeps `ugc-lifeboat-local` offline, reproducible, and independent of hosted services.

## Local workflow

```bash
uv sync
uv run ugc-lifeboat init-demo
uv run ugc-lifeboat archive --creator creator-alba
uv run ugc-lifeboat verify-bundle outputs/creator-alba.rrcustomroom
uv run ugc-lifeboat dashboard
```

```bash
uv run ugc-lifeboat bulk-export
uv run ugc-lifeboat verify
```

## Review surfaces

- `outputs/<creator>.rrcustomroom`
- `outputs/archive_manifest.json`
- `outputs/bulk_manifest.json`
- `outputs/summary.json`
- `outputs/dashboard.html`
- `outputs/demo_pack/`

## Quality checks

```bash
uv run ruff check .
uv run pytest -q
uv run ugc-lifeboat verify
```

## Repository hygiene

`UGC Lifeboat Local` is built for local reproduction: deterministic inputs enter the run, deterministic evidence comes out, and private data stays outside the repo.
