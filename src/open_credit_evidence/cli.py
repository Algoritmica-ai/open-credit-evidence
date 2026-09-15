"""Command-line interface for OpenCredit Evidence.

Provides commands for processing cases, running omission checks,
and verifying evidence reports.
"""

import asyncio
import json
from pathlib import Path
from typing import Annotated

import structlog
import typer
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from open_credit_evidence import __version__
from open_credit_evidence.evidence import (
    create_evidence_report,
    load_evidence_report,
    save_evidence_report,
    verify_evidence_report,
)
from open_credit_evidence.loader import CaseLoadError, TamperDetectedError, load_case
from open_credit_evidence.omission_check import OmissionChecker
from open_credit_evidence.runner import (
    NemotronClientError,
    build_context,
    run_case,
)
from open_credit_evidence.schemas import Summary

load_dotenv()

structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.dev.ConsoleRenderer(),
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
)

app = typer.Typer(
    name="oce",
    help="OpenCredit Evidence - Credit Decision Verification System",
    add_completion=False,
)
console = Console()


@app.callback()
def callback() -> None:
    """OpenCredit Evidence CLI."""
    pass


@app.command()
def version() -> None:
    """Show version information."""
    console.print(f"[bold]OpenCredit Evidence[/bold] v{__version__}")


DEFAULT_REPORTS_DIR = Path("reports")


@app.command()
def process(
    case_dir: Annotated[Path, typer.Argument(help="Path to case directory")],
    output: Annotated[
        Path | None, typer.Option("--output", "-o", help="Output report path (overrides default)")
    ] = None,
    no_export: Annotated[
        bool, typer.Option("--no-export", help="Skip writing report to disk (print only)")
    ] = False,
    skip_api: Annotated[
        bool, typer.Option("--skip-api", help="Skip API call, use stub summary")
    ] = False,
) -> None:
    """Process a loan application case through the full pipeline.

    Loads the case, generates a summary, checks for omissions,
    and creates an evidence report.

    By default, the report is saved to reports/<case_id>.json.
    Use --no-export to skip file output, or --output/-o to specify a custom path.
    """
    console.print(Panel(f"Processing case: [bold]{case_dir}[/bold]"))

    try:
        case = load_case(case_dir)
        console.print(f"✓ Loaded case [green]{case.metadata.case_id}[/green]")
        console.print(f"  Documents: {len(case.documents)}")
        console.print(f"  Critical facts: {len(case.metadata.critical_facts)}")
        console.print(f"  Fingerprint: {case.fingerprint[:16]}...")
    except CaseLoadError as e:
        console.print(f"[red]Error loading case:[/red] {e}")
        raise typer.Exit(1) from None
    except TamperDetectedError as e:
        console.print(f"[red]TAMPER DETECTED:[/red] {e}")
        raise typer.Exit(2) from None

    context = build_context(case)
    console.print(f"  Whole-file context: {len(context)} chars")

    console.print("\nGenerating summary (hosted NVIDIA Build, whole-file)...")
    if skip_api:
        summary = Summary(
            case_id=case.metadata.case_id,
            text="[Skipped - use test fixtures for omission testing]",
            model="skipped",
        )
        console.print("  [yellow]Skipped API call (--skip-api)[/yellow]")
    else:
        try:
            summary = asyncio.run(run_case(case))
        except NemotronClientError as e:
            console.print(f"[red]NVIDIA Build error:[/red] {e}")
            raise typer.Exit(3) from None
        console.print(f"  Model: {summary.model}")
        console.print(f"  Length: {len(summary.text)} chars")

    console.print("\nChecking for omissions...")
    checker = OmissionChecker()
    marking = checker.check_summary(case, summary)

    table = Table(title="Omission Check Results")
    table.add_column("Fact ID")
    table.add_column("Category")
    table.add_column("Present")
    table.add_column("Confidence")

    for result in marking.results:
        status = "[green]✓[/green]" if result.is_present else "[red]✗[/red]"
        table.add_row(
            result.fact_id,
            result.fact.category.value,
            status,
            f"{result.confidence:.0%}",
        )

    console.print(table)

    status_color = "green" if marking.passed else "red"
    console.print(
        f"\nResult: [{status_color}]{'PASSED' if marking.passed else 'FAILED'}[/{status_color}]"
    )
    console.print(f"  Facts present: {marking.facts_present}/{marking.total_facts}")
    console.print(f"  Omission rate: {marking.omission_rate:.0%}")

    console.print("\nCreating evidence report...")
    report = create_evidence_report(case, summary, marking)
    console.print(f"  Report ID: {report.report_id}")
    console.print(f"  Chain fingerprint: {report.chain_fingerprint[:16]}...")

    if not no_export:
        if output:
            report_path = output
            report_path.parent.mkdir(parents=True, exist_ok=True)
        else:
            DEFAULT_REPORTS_DIR.mkdir(parents=True, exist_ok=True)
            report_path = DEFAULT_REPORTS_DIR / f"{case.metadata.case_id}.json"
        save_evidence_report(report, report_path)
        console.print(f"\n✓ Report saved to [bold]{report_path}[/bold]")
    else:
        console.print("\n[yellow]Report export skipped (--no-export)[/yellow]")


@app.command()
def verify(
    report_path: Annotated[Path, typer.Argument(help="Path to evidence report")],
    case_fingerprint: Annotated[
        str | None, typer.Option("--case-fingerprint", "-f", help="Expected case fingerprint")
    ] = None,
) -> None:
    """Verify an evidence report has not been tampered with."""
    console.print(Panel(f"Verifying report: [bold]{report_path}[/bold]"))

    try:
        report = load_evidence_report(report_path)
        console.print(f"  Report ID: {report.report_id}")
        console.print(f"  Case ID: {report.case_id}")
        console.print(f"  Created: {report.created_at}")
    except (json.JSONDecodeError, ValueError) as e:
        console.print(f"[red]Error loading report:[/red] {e}")
        raise typer.Exit(1) from None

    try:
        verify_evidence_report(report, case_fingerprint)
        console.print("\n[green]✓ Verification PASSED[/green]")
        console.print("  Chain fingerprint is valid")
        console.print("  No tampering detected")
    except Exception as e:
        console.print("\n[red]✗ Verification FAILED[/red]")
        console.print(f"  {e}")
        raise typer.Exit(2) from None


@app.command()
def load(
    case_dir: Annotated[Path, typer.Argument(help="Path to case directory")],
    show_content: Annotated[
        bool, typer.Option("--content", "-c", help="Show document content")
    ] = False,
) -> None:
    """Load and inspect a case without processing."""
    try:
        case = load_case(case_dir)
    except CaseLoadError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from None

    console.print(Panel(f"Case: [bold]{case.metadata.case_id}[/bold]"))
    console.print(f"Type: {case.metadata.case_type}")
    console.print(f"Created: {case.metadata.created_at}")
    console.print(f"Referral: {case.metadata.referral_reason}")
    console.print(f"Combined fingerprint: {case.fingerprint}")

    console.print("\n[bold]Documents:[/bold]")
    for name, doc in case.documents.items():
        console.print(f"  • {name} ({doc.type})")
        console.print(f"    Fingerprint: {doc.fingerprint}")
        if show_content and doc.content:
            console.print(f"    Content preview: {doc.content[:200]}...")

    console.print("\n[bold]Critical Facts:[/bold]")
    for fact in case.metadata.critical_facts:
        severity_color = {
            "critical": "red",
            "high": "yellow",
            "medium": "blue",
            "low": "white",
        }.get(fact.severity.value, "white")
        console.print(
            f"  [{fact.id}] [{severity_color}]{fact.severity.value.upper()}[/{severity_color}] {fact.category.value}"
        )
        console.print(f"    {fact.fact}")


if __name__ == "__main__":
    app()
