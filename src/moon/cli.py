import json
import logging
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

from moon import config, logging_config
from moon.executor import execute_task as _execute_task
from moon.models import ResourceSelection, RunResult, Task

log = logging.getLogger(__name__)

app = typer.Typer(help="Moon — multi-agent security orchestration")
console = Console()


def run_task(task: Task, catalogs_path: Optional[Path] = None) -> RunResult:
    """Single-task execution with Rich progress display."""
    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), console=console) as progress:
        pid = progress.add_task("Running...", total=None)

        def on_step(msg: str) -> None:
            progress.update(pid, description=msg)

        # Patch log temporarily to drive progress text
        _orig = log.info

        def _info(fmt, *args):  # type: ignore[override]
            msg = fmt % args if args else fmt
            if "step" in msg and "started" in msg:
                progress.update(pid, description=msg.split("] ", 1)[-1])
            _orig(fmt, *args)

        log.info = _info  # type: ignore[method-assign]
        try:
            result = _execute_task(task, catalogs_path, on_event=None)
        finally:
            log.info = _orig  # type: ignore[method-assign]
            progress.update(pid, description="[green]Complete[/green]")

    return result


@app.command()
def run(
    task: str = typer.Argument(..., help="Natural language task description"),
    input_file: Optional[Path] = typer.Option(None, "--input", "-i", help="JSON file with input_data"),
    catalogs: Optional[Path] = typer.Option(None, "--catalogs", "-c", help="Path to catalogs directory"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Save run result as JSON"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show per-step detail"),
    debug: bool = typer.Option(False, "--debug", "-d", help="Enable debug logging to stderr"),
):
    """Execute a single security task."""
    logging_config.setup(debug=debug)
    input_data = json.loads(input_file.read_text()) if input_file else {}
    task_obj = Task(description=task, input_data=input_data)

    console.print(Panel(f"[bold blue]Moon[/bold blue]\n\n{task}", title="Task", border_style="blue"))

    t_total = time.monotonic()
    result = run_task(task_obj, catalogs)
    total_ms = int((time.monotonic() - t_total) * 1000)
    log.info("task completed in %dms", total_ms)

    console.print(f"\n[bold]Runbook:[/bold] {result.runbook_id} — {result.runbook_description}")
    console.print(f"[dim]Total: {total_ms}ms[/dim]")

    if verbose:
        for sr in result.step_results:
            table = Table(title=f"Step {sr.step_index + 1}: {sr.step_text}", show_header=False, border_style="dim")
            table.add_column("", style="bold cyan")
            table.add_column("")
            table.add_row("Tools", ", ".join(sr.resources_used.tool_names) or "none")
            table.add_row("Skills", ", ".join(sr.resources_used.skill_names) or "none")
            table.add_row("Guidelines", ", ".join(sr.resources_used.guideline_names) or "none")
            for tc in sr.tool_calls:
                table.add_row(f"↳ {tc.tool_name}", str(tc.input))
            console.print(table)
            console.print(Panel(sr.output, title="Output", border_style="dim"))

    console.print(Panel(result.final_output, title="[bold green]Final Output[/bold green]", border_style="green"))

    if output:
        output.write_text(result.model_dump_json(indent=2))
        console.print(f"[dim]Saved to {output}[/dim]")


@app.command()
def batch(
    tasks_file: Path = typer.Argument(..., help="JSON file with list of task objects"),
    catalogs: Optional[Path] = typer.Option(None, "--catalogs", "-c", help="Path to catalogs directory"),
    output_dir: Optional[Path] = typer.Option(None, "--output-dir", "-o", help="Directory to save per-task results"),
    workers: int = typer.Option(config.MAX_WORKERS, "--workers", "-w", help="Max parallel tasks"),
    debug: bool = typer.Option(False, "--debug", "-d", help="Enable debug logging to stderr"),
):
    """Execute multiple tasks in parallel."""
    logging_config.setup(debug=debug)

    raw = json.loads(tasks_file.read_text())
    tasks = [Task(**t) for t in raw]

    if output_dir:
        output_dir.mkdir(parents=True, exist_ok=True)

    console.print(Panel(
        f"[bold blue]Moon Batch[/bold blue]\n\n{len(tasks)} tasks  ·  {workers} workers",
        border_style="blue",
    ))

    results: dict[int, RunResult | Exception] = {}
    t_batch = time.monotonic()

    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), console=console) as progress:
        pids = {i: progress.add_task(f"[{i+1}] {t.description[:60]}", total=None) for i, t in enumerate(tasks)}

        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(_execute_task, t, catalogs): i for i, t in enumerate(tasks)}
            for future in as_completed(futures):
                i = futures[future]
                try:
                    result = future.result()
                    results[i] = result
                    progress.update(pids[i], description=f"[green]✓[/green] [{i+1}] {tasks[i].description[:55]}")
                    if output_dir:
                        (output_dir / f"task_{i+1}.json").write_text(result.model_dump_json(indent=2))
                except Exception as e:
                    results[i] = e
                    progress.update(pids[i], description=f"[red]✗[/red] [{i+1}] {tasks[i].description[:55]}")
                    log.error("[%s] failed: %s", tasks[i].description[:40], e)

    batch_ms = int((time.monotonic() - t_batch) * 1000)

    table = Table(title="Batch Results", border_style="dim")
    table.add_column("#", style="dim", width=3)
    table.add_column("Task")
    table.add_column("Runbook")
    table.add_column("Status")

    for i in sorted(results):
        r = results[i]
        if isinstance(r, Exception):
            table.add_row(str(i + 1), tasks[i].description[:60], "—", "[red]failed[/red]")
        else:
            table.add_row(str(i + 1), tasks[i].description[:60], r.runbook_id, "[green]done[/green]")

    console.print(table)
    console.print(f"[dim]Batch completed in {batch_ms}ms  ({len(tasks)} tasks, {workers} workers)[/dim]")


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", "--host", help="Bind address"),
    port: int = typer.Option(8000, "--port", "-p", help="Port"),
    catalogs: Optional[Path] = typer.Option(None, "--catalogs", "-c", help="Path to catalogs directory"),
    debug: bool = typer.Option(False, "--debug", "-d", help="Enable debug logging"),
):
    """Start the Moon web UI."""
    from moon.server import serve as _serve
    console.print(f"[bold blue]Moon[/bold blue] UI → [link]http://{host}:{port}[/link]")
    _serve(host=host, port=port, catalogs=catalogs, debug=debug)


if __name__ == "__main__":
    app()
