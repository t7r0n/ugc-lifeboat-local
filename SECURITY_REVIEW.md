# Security Review

## Scope

Local CLI, deterministic synthetic UGC fixtures, content-addressed archive bundling, Ed25519 bundle signatures, DuckDB run store, static dashboard, JSONL tool loop, and demo-pack export.

## Assessment

The application is offline and synthetic-only. It does not contact live APIs, load credentials, mutate global configuration, or execute shell commands at runtime.

## Controls

- Fixture and manifest data are parsed through Pydantic models.
- Archive paths are generated from validated fixture IDs rather than user-controlled archive member paths.
- Bundle manifests include SHA-256 hashes for every stored blob.
- Bundle signatures use Ed25519 public-key verification.
- DuckDB writes use parameterized inserts.
- Dashboard rendering uses Jinja autoescaping.
- Runtime state, outputs, caches, and virtual environments are ignored by git.

## Focused Scan Status

Completed 2026-05-18.

Threat model: local offline CLI and dashboard over synthetic UGC archive fixtures. Primary risks are accidental credential/data inclusion, archive path traversal, invalid signature verification, unsafe command execution, unsafe dashboard rendering, and run-store corruption under repeated local operations.

Finding discovery:

- Secret/public-hygiene scan found no credentials, private tokens, private creator data, or campaign artifacts in committed source candidates.
- Dangerous sink scan found no runtime shell execution, network clients, dynamic `eval`/`exec`, pickle, YAML loading, or socket use in `src/`.
- The only `subprocess` use is in tests to black-box validate the CLI JSONL tool loop.
- Bundle archive member paths are generated from content hashes and fixed names, not user-controlled filenames.
- Bundle manifests include SHA-256 hashes for every stored blob and Ed25519 signatures over the canonical unsigned manifest.
- DuckDB writes use parameterized statements and verification can rehydrate the run store from signed bundle manifests.
- Dashboard output is generated from local JSON through Jinja autoescaping.

Validation: no reportable findings.

Residual risk: this is a local reference implementation with synthetic fixtures, not a production export client. Production use would need platform authorization, privacy review, legal export policy, signed release builds, rate limits, and audited compatibility with real scene descriptors.
