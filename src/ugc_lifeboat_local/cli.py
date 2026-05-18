from __future__ import annotations

import json
import sys
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from ugc_lifeboat_local.archive import verify_bundle
from ugc_lifeboat_local.dashboard import build_dashboard
from ugc_lifeboat_local.runner import archive, benchmark, bulk_export, export_demo_pack, init_demo, verify_outputs


app = typer.Typer(help="Offline UGC archive bundler with signed portable bundles.")
console = Console()


@app.command("init-demo")
def init_demo_command(force: bool = typer.Option(False, "--force")) -> None:
    init_demo(force=force)
    console.print("[green]Initialized synthetic UGC archive store.[/green]")


@app.command("archive")
def archive_command(creator: str = typer.Option("creator-alba", "--creator")) -> None:
    summary = archive(creator)
    console.print_json(summary.model_dump_json(indent=2))
    if not summary.pass_gates:
        raise typer.Exit(1)


@app.command("verify-bundle")
def verify_bundle_command(path: Path) -> None:
    ok = verify_bundle(path)
    console.print("[green]valid[/green]" if ok else "[red]invalid[/red]")
    if not ok:
        raise typer.Exit(1)


@app.command("bulk-export")
def bulk_export_command() -> None:
    summary = bulk_export()
    console.print_json(summary.model_dump_json(indent=2))
    if not summary.pass_gates:
        raise typer.Exit(1)


@app.command("verify")
def verify_command() -> None:
    ok, checks = verify_outputs()
    table = Table(title="Verification")
    table.add_column("Gate")
    table.add_column("Status")
    for gate, status in checks.items():
        table.add_row(gate, "PASS" if status else "FAIL")
    console.print(table)
    if not ok:
        raise typer.Exit(1)


@app.command("dashboard")
def dashboard_command() -> None:
    path = build_dashboard()
    console.print(f"[green]Dashboard written:[/green] {path}")


@app.command("benchmark")
def benchmark_command(iterations: int = typer.Option(20, "--iterations", min=1)) -> None:
    summary = benchmark(iterations=iterations)
    table = Table(title="Benchmark")
    table.add_column("Metric")
    table.add_column("Value")
    table.add_row("creators", str(summary.creators))
    table.add_row("rooms", str(summary.rooms))
    table.add_row("raw bytes", str(summary.raw_bytes))
    table.add_row("stored bytes", str(summary.stored_bytes))
    table.add_row("dedup ratio", f"{summary.dedup_ratio}x")
    table.add_row("completeness", f"{summary.completeness:.0%}")
    table.add_row("pass gates", str(summary.pass_gates))
    console.print(table)
    if not summary.pass_gates:
        raise typer.Exit(1)


@app.command("export-demo-pack")
def export_demo_pack_command() -> None:
    path = export_demo_pack()
    console.print(f"[green]Demo pack exported:[/green] {path}")


@app.command("tool-loop")
def tool_loop_command() -> None:
    for line in sys.stdin:
        if not line.strip():
            continue
        payload = json.loads(line)
        tool = str(payload["tool"])
        args = dict(payload.get("arguments", {}))
        if tool == "archive":
            print(archive(str(args.get("creator", "creator-alba"))).model_dump_json())
        elif tool == "verify_bundle":
            print(json.dumps({"valid": verify_bundle(Path(str(args["path"])))}))
        elif tool == "bulk_export":
            print(bulk_export().model_dump_json())
        else:
            raise typer.BadParameter(f"unknown tool: {tool}")


def main() -> None:
    app()


if __name__ == "__main__":
    main()

