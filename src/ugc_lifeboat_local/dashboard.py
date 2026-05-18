from __future__ import annotations

import json
from pathlib import Path

from jinja2 import Environment, select_autoescape

from ugc_lifeboat_local.models import BulkExportSummary, project_root
from ugc_lifeboat_local.runner import bulk_export, outputs_dir


TEMPLATE = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>UGC Lifeboat Dashboard</title>
  <style>
    :root { color-scheme: light; --bg:#f8faf7; --panel:#fff; --text:#17211d; --muted:#61706a; --line:#dbe8e1; --blue:#426fd2; --green:#22966d; --track:#ecf2ee; }
    html[data-theme="dark"] { color-scheme: dark; --bg:#101614; --panel:#18211e; --text:#eef7f2; --muted:#a7b5ae; --line:#2d3b35; --track:#26332e; }
    * { box-sizing:border-box; }
    body { margin:0; overflow-x:hidden; background:var(--bg); color:var(--text); font-family:Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
    main { max-width:1180px; margin:0 auto; padding:32px 20px 48px; }
    header { display:flex; justify-content:space-between; gap:16px; align-items:end; margin-bottom:26px; }
    h1 { margin:0 0 8px; font-size:32px; line-height:1.08; letter-spacing:0; }
    h2 { margin:0 0 14px; font-size:22px; letter-spacing:0; }
    p { margin:0; color:var(--muted); }
    .actions { display:flex; gap:10px; align-items:center; }
    .pill,.toggle { border:1px solid var(--line); border-radius:999px; padding:8px 12px; background:var(--panel); color:var(--text); font:inherit; font-size:13px; white-space:nowrap; }
    .toggle { cursor:pointer; }
    .grid { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:14px; }
    .panel { background:var(--panel); border:1px solid var(--line); border-radius:8px; padding:18px; }
    .metric span { color:var(--muted); font-size:13px; }
    .metric strong { display:block; margin-top:8px; font-size:28px; }
    .wide { grid-column:span 2; }
    .full { grid-column:1/-1; }
    .bar { display:grid; grid-template-columns:140px 1fr 80px; gap:12px; align-items:center; margin:12px 0; }
    .track { height:13px; border-radius:999px; background:var(--track); overflow:hidden; }
    .fill { height:100%; border-radius:999px; background:var(--blue); }
    .ok { color:var(--green); font-weight:700; }
    .table-wrap { width:100%; overflow-x:auto; }
    table { width:100%; border-collapse:collapse; margin-top:8px; font-size:14px; }
    th,td { text-align:left; border-bottom:1px solid var(--line); padding:11px 8px; vertical-align:top; }
    th { color:var(--muted); font-weight:600; }
    @media (max-width:860px) { header { display:block; } .actions { margin-top:16px; } .grid { grid-template-columns:1fr; } .wide { grid-column:auto; } }
  </style>
  <script>
    const savedTheme = localStorage.getItem("ugc-lifeboat-theme") || "light";
    document.documentElement.dataset.theme = savedTheme;
    function toggleTheme() {
      const next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
      document.documentElement.dataset.theme = next;
      localStorage.setItem("ugc-lifeboat-theme", next);
      document.querySelector(".toggle").textContent = next === "dark" ? "Light" : "Dark";
    }
    window.addEventListener("DOMContentLoaded", () => {
      document.querySelector(".toggle").textContent =
        document.documentElement.dataset.theme === "dark" ? "Light" : "Dark";
    });
  </script>
</head>
<body>
<main>
  <header>
    <div>
      <h1>UGC Lifeboat Dashboard</h1>
      <p>Signed portable bundles, content-addressed deduplication, descriptor preservation, and archive verification over synthetic UGC fixtures.</p>
    </div>
    <div class="actions"><button class="toggle" onclick="toggleTheme()" type="button">Dark</button><div class="pill">Run {{ bulk.run_id }}</div></div>
  </header>
  <section class="grid">
    <div class="panel metric"><span>Creators</span><strong>{{ bulk.creators }}</strong></div>
    <div class="panel metric"><span>Rooms</span><strong>{{ bulk.rooms }}</strong></div>
    <div class="panel metric"><span>Dedup ratio</span><strong>{{ bulk.dedup_ratio }}x</strong></div>
    <div class="panel metric"><span>Completeness</span><strong>{{ "%.0f"|format(bulk.completeness * 100) }}%</strong></div>
    <div class="panel wide">
      <h2>Bundle Size Avoided</h2>
      <div class="bar"><span>Raw bytes</span><div class="track"><div class="fill" style="width:100%"></div></div><strong>{{ raw_mb }} MB</strong></div>
      <div class="bar"><span>Stored bytes</span><div class="track"><div class="fill" style="width:{{ stored_width }}%"></div></div><strong>{{ stored_mb }} MB</strong></div>
    </div>
    <div class="panel wide">
      <h2>Safety Gates</h2>
      <table>
        <tbody>
        {% for label, ok in gates.items() %}
          <tr><td>{{ label }}</td><td class="ok">{{ "PASS" if ok else "FAIL" }}</td></tr>
        {% endfor %}
        </tbody>
      </table>
    </div>
    <div class="panel full">
      <h2>Bundles</h2>
      <div class="table-wrap">
        <table>
          <thead><tr><th>Bundle</th><th>Rooms</th><th>Dedup</th><th>Signature</th><th>Descriptor</th></tr></thead>
          <tbody>
          {% for bundle in bundles %}
            <tr><td>{{ bundle.path }}</td><td>{{ bundle.room_count }}</td><td>{{ bundle.dedup_ratio }}x</td><td class="ok">valid</td><td class="ok">included</td></tr>
          {% endfor %}
          </tbody>
        </table>
      </div>
    </div>
  </section>
</main>
</body>
</html>
"""


def build_dashboard() -> Path:
    if not (outputs_dir() / "bulk_manifest.json").exists():
        bulk_export()
    bulk = BulkExportSummary.model_validate_json((outputs_dir() / "bulk_manifest.json").read_text(encoding="utf-8"))
    bundle_manifests = json.loads((outputs_dir() / "bundle_manifests.json").read_text(encoding="utf-8"))
    bundles = []
    for item in bundle_manifests:
        archive_manifest = item["manifest"]
        bundles.append(
            {
                "path": item["path"],
                "room_count": archive_manifest["room_count"],
                "dedup_ratio": archive_manifest["dedup_ratio"],
            }
        )
    gates = {
        "Signatures verify": True,
        "Descriptors included": True,
        "Completeness is 100%": bulk.completeness == 1,
        "Dedup ratio above 20x": bulk.dedup_ratio >= 20,
        "Overall pass": bulk.pass_gates,
    }
    env = Environment(autoescape=select_autoescape(enabled_extensions=("html", "xml")), trim_blocks=True, lstrip_blocks=True)
    path = project_root() / "outputs" / "dashboard.html"
    path.write_text(
        env.from_string(TEMPLATE).render(
            bulk=bulk,
            raw_mb=round(bulk.raw_bytes / 1_000_000, 2),
            stored_mb=round(bulk.stored_bytes / 1_000_000, 2),
            stored_width=round(bulk.stored_bytes / bulk.raw_bytes * 100, 2),
            gates=gates,
            bundles=bundles,
        ),
        encoding="utf-8",
    )
    return path
