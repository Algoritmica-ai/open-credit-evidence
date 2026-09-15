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
from open_credit_evidence.platform_controls import (
    PlatformEvidenceError,
    fetch_steel_thread_report,
    load_steel_thread_report,
)
from open_credit_evidence.regulations import evaluate_case_regulations
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


@app.command()
def process(
    case_dir: Annotated[Path, typer.Argument(help="Path to case directory")],
    output: Annotated[
        Path | None, typer.Option("--output", "-o", help="Output report path")
    ] = None,
    skip_api: Annotated[
        bool, typer.Option("--skip-api", help="Skip API call, use stub summary")
    ] = False,
    steel_thread_url: Annotated[
        str | None,
        typer.Option(help="AI Steel Thread base URL, for example http://localhost:8080"),
    ] = None,
    steel_thread_instance: Annotated[
        str | None,
        typer.Option(help="Steel Thread process instance linked to this case"),
    ] = None,
    steel_thread_report: Annotated[
        Path | None,
        typer.Option(help="Previously exported Steel Thread compliance-report JSON"),
    ] = None,
) -> None:
    """Process a loan application case through the full pipeline.

    Loads the case, generates a summary, checks for omissions,
    and creates an evidence report.
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

    regulatory = evaluate_case_regulations(case)
    regulatory_color = "green" if regulatory.status == "pass" else "red"
    console.print(
        f"  Regulatory rules: [{regulatory_color}]"
        f"{regulatory.status.upper()}[/{regulatory_color}]"
    )
    if regulatory.ruleset_id:
        console.print(
            f"    {regulatory.ruleset_id} v{regulatory.ruleset_version}: "
            f"{regulatory.passed_rules} pass, {regulatory.failed_rules} fail, "
            f"{regulatory.advisory_rules} advisory"
        )
    else:
        console.print(f"    {regulatory.note}")

    if steel_thread_report is not None and (
        steel_thread_url is not None or steel_thread_instance is not None
    ):
        console.print(
            "[red]Choose either --steel-thread-report or the URL/instance options, not both[/red]"
        )
        raise typer.Exit(4)
    if (steel_thread_url is None) != (steel_thread_instance is None):
        console.print("[red]--steel-thread-url and --steel-thread-instance are required together[/red]")
        raise typer.Exit(4)

    platform_controls = None
    try:
        if steel_thread_report is not None:
            platform_controls = load_steel_thread_report(
                steel_thread_report, case.metadata.case_id
            )
        elif steel_thread_url is not None and steel_thread_instance is not None:
            platform_controls = fetch_steel_thread_report(
                steel_thread_url,
                steel_thread_instance,
                case.metadata.case_id,
            )
    except PlatformEvidenceError as exc:
        console.print(f"[red]Steel Thread evidence error:[/red] {exc}")
        raise typer.Exit(4) from None

    if platform_controls is None:
        console.print("  Platform controls: [yellow]NOT LINKED[/yellow]")
    else:
        platform_color = "green" if platform_controls.claim_status == "verified" else "yellow"
        console.print(
            f"  Platform controls: [{platform_color}]"
            f"{platform_controls.claim_status.upper()}[/{platform_color}]"
        )
        console.print(
            f"    {platform_controls.llm_call_count} LLM calls, "
            f"{platform_controls.total_tokens} tokens, "
            f"${platform_controls.estimated_cost_usd:.6f} estimated cost"
        )
        for issue in platform_controls.issues:
            console.print(f"    [yellow]• {issue}[/yellow]")

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
    report = create_evidence_report(
        case,
        summary,
        marking,
        regulatory_assessment=regulatory,
        platform_controls=platform_controls,
    )
    console.print(f"  Report ID: {report.report_id}")
    console.print(f"  Chain fingerprint: {report.chain_fingerprint[:16]}...")

    if output:
        save_evidence_report(report, output)
        console.print(f"\n✓ Report saved to [bold]{output}[/bold]")


@app.command("check-rules")
def check_rules(
    case_dir: Annotated[Path, typer.Argument(help="Path to case directory")],
    output: Annotated[
        Path | None, typer.Option("--output", "-o", help="Write assessment JSON")
    ] = None,
) -> None:
    """Evaluate every jurisdiction rule against a case's evidence map."""
    try:
        case = load_case(case_dir)
    except CaseLoadError as exc:
        console.print(f"[red]Error loading case:[/red] {exc}")
        raise typer.Exit(1) from None

    assessment = evaluate_case_regulations(case)
    table = Table(title=f"Regulatory rules — {case.metadata.case_id}")
    table.add_column("Rule")
    table.add_column("Status")
    table.add_column("Owner")
    table.add_column("Missing evidence")
    for finding in assessment.findings:
        table.add_row(
            finding.rule_id,
            finding.status.upper(),
            finding.obligation_owner,
            ", ".join(finding.missing_evidence) or "—",
        )
    console.print(table)
    console.print(
        f"Coverage: {len(assessment.evaluated_rule_ids)}/{assessment.total_rules}; "
        f"result: {assessment.status.upper()}"
    )
    console.print(f"{assessment.note}")

    if output is not None:
        output.write_text(
            json.dumps(assessment.model_dump(mode="json"), indent=2),
            encoding="utf-8",
        )
        console.print(f"✓ Assessment saved to [bold]{output}[/bold]")

    if assessment.status != "pass":
        raise typer.Exit(5)


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
