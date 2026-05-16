#!/usr/bin/env python3
"""
Deal Intelligence Agent — CLI
Usage:
  python main.py --company "Apple Inc" --ticker AAPL
  python main.py --company "GTBank" --ticker GTCO --output markdown
  python main.py --company "WeWork" --signals credit_risk distressed_asset --compliance
  python main.py feedback --list
  python main.py audit --verify
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.panel import Panel
from rich.table import Table
from rich import box

console = Console()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Autonomous Deal Intelligence Agent — US & African markets",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command")

    # ── analyse (default) ──
    a = sub.add_parser("analyse", help="Run deal intelligence analysis")
    a.add_argument("--company",    required=True)
    a.add_argument("--ticker",     default=None)
    a.add_argument("--cik",        default=None)
    a.add_argument("--lookback",   type=int, default=90)
    a.add_argument("--depth",      choices=["quick","standard","deep"], default="standard")
    a.add_argument("--signals",    nargs="*", default=[], choices=[
        "m_and_a_activity","credit_risk","distressed_asset","earnings_surprise",
        "leadership_change","regulatory_action","debt_restructuring","insider_activity"])
    a.add_argument("--output",     choices=["terminal","json","markdown"], default="terminal")
    a.add_argument("--out-file",   default=None)
    a.add_argument("--compliance", action="store_true", help="Enable compliance mode")

    # ── feedback ──
    f = sub.add_parser("feedback", help="View or submit analyst feedback")
    f.add_argument("--list",   action="store_true")
    f.add_argument("--stats",  action="store_true")
    f.add_argument("--submit", nargs="+", metavar="KEY=VALUE",
                   help="company=X signal_type=Y feedback_type=Z original_severity=W")

    # ── audit ──
    au = sub.add_parser("audit", help="Audit log operations")
    au.add_argument("--verify", action="store_true")
    au.add_argument("--tail",   type=int, default=20)

    # Allow bare flags at root level for convenience
    parser.add_argument("--company",    default=None)
    parser.add_argument("--ticker",     default=None)
    parser.add_argument("--cik",        default=None)
    parser.add_argument("--lookback",   type=int, default=90)
    parser.add_argument("--depth",      choices=["quick","standard","deep"], default="standard")
    parser.add_argument("--signals",    nargs="*", default=[])
    parser.add_argument("--output",     choices=["terminal","json","markdown"], default="terminal")
    parser.add_argument("--out-file",   default=None)
    parser.add_argument("--compliance", action="store_true")

    return parser.parse_args()


async def _run_analysis(args: argparse.Namespace) -> None:
    from src.schemas.models import AnalysisRequest, SignalType
    from src.agents.graph import run_analysis
    from src.utils.formatter import print_brief, brief_to_json, brief_to_markdown

    company = args.company
    if not company:
        console.print("[red]--company is required[/red]")
        sys.exit(1)

    focus = [SignalType(s) for s in (args.signals or [])]
    request = AnalysisRequest(
        company_name=company,
        ticker=args.ticker,
        cik=args.cik,
        lookback_days=args.lookback,
        depth=args.depth,
        focus_signals=focus,
    )
    compliance = getattr(args, "compliance", False)

    console.print()
    console.print(Panel(
        f"[bold cyan]Deal Intelligence Agent[/bold cyan]\n\n"
        f"[white]Target:[/white] {company}"
        + (f" ([dim]{args.ticker}[/dim])" if args.ticker else "")
        + f"\n[white]Lookback:[/white] {args.lookback} days  "
        + f"[white]Depth:[/white] {args.depth}"
        + (f"\n[yellow]Compliance Mode: ON[/yellow]" if compliance else ""),
        border_style="cyan", padding=(0, 2)
    ))
    console.print()

    steps = [
        "Resolving company…",
        "Collecting SEC EDGAR + African exchanges + news…",
        "Running deterministic signal engine…",
        "LLM explaining confirmed candidates…",
        "Computing alpha scores…",
        "Synthesising analyst brief…",
    ]

    import src.agents.collection_agent as ca
    import src.agents.signal_agent     as sa

    _orig_collect  = ca.DataCollectionAgent.run
    _orig_det      = sa.DeterministicDetectionNode.run
    _orig_explain  = sa.LLMExplanationNode.run
    _orig_alpha    = sa.AlphaScoringNode.run
    _orig_synth    = sa.BriefSynthesisAgent.run

    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"),
                  TimeElapsedColumn(), console=console, transient=True) as progress:
        task = progress.add_task(steps[0], total=None)

        async def _c(self, state):
            progress.update(task, description=steps[1])
            return await _orig_collect(self, state)

        def _d(self, state):
            progress.update(task, description=steps[2])
            return _orig_det(self, state)

        async def _e(self, state):
            progress.update(task, description=steps[3])
            return await _orig_explain(self, state)

        def _a(self, state):
            progress.update(task, description=steps[4])
            return _orig_alpha(self, state)

        async def _s(self, state):
            progress.update(task, description=steps[5])
            return await _orig_synth(self, state)

        ca.DataCollectionAgent.run    = _c
        sa.DeterministicDetectionNode.run = _d
        sa.LLMExplanationNode.run     = _e
        sa.AlphaScoringNode.run       = _a
        sa.BriefSynthesisAgent.run    = _s

        try:
            brief = await run_analysis(request, compliance_mode=compliance)
        finally:
            ca.DataCollectionAgent.run        = _orig_collect
            sa.DeterministicDetectionNode.run = _orig_det
            sa.LLMExplanationNode.run         = _orig_explain
            sa.AlphaScoringNode.run           = _orig_alpha
            sa.BriefSynthesisAgent.run        = _orig_synth

    if args.output == "terminal":
        print_brief(brief)
        return

    output_str = brief_to_json(brief) if args.output == "json" else brief_to_markdown(brief)

    if args.out_file:
        Path(args.out_file).write_text(output_str, encoding="utf-8")
        console.print(f"\n[green]✓[/green] Brief written to [bold]{args.out_file}[/bold]")
    else:
        if args.output == "json":
            console.print_json(output_str)
        else:
            console.print(output_str)


def _run_feedback(args: argparse.Namespace) -> None:
    from src.engines.feedback import get_recent_feedback, get_signal_stats, submit_feedback
    from src.schemas.models import FeedbackType, SignalType, Severity

    if args.stats:
        stats = get_signal_stats()
        if not stats:
            console.print("[dim]No feedback data yet.[/dim]")
            return
        t = Table(title="Signal Precision/Recall", box=box.SIMPLE_HEAD, header_style="bold cyan")
        t.add_column("Signal Type"); t.add_column("Total", justify="right")
        t.add_column("Confirmed", justify="right"); t.add_column("False +ve", justify="right")
        t.add_column("Precision"); t.add_column("Recall Proxy")
        for sig, s in stats.items():
            t.add_row(sig, str(s["total"]), str(s["confirmed"]), str(s["false_positive"]),
                      f"{s['precision']:.0%}", f"{s['recall_proxy']:.0%}")
        console.print(t)
        return

    if args.submit:
        kv = dict(item.split("=", 1) for item in args.submit if "=" in item)
        try:
            entry = submit_feedback(
                company_name=kv.get("company", "unknown"),
                signal_type=SignalType(kv.get("signal_type", "credit_risk")),
                feedback_type=FeedbackType(kv.get("feedback_type", "false_positive")),
                original_severity=Severity(kv.get("original_severity", "medium")),
                analyst_note=kv.get("note", ""),
            )
            console.print(f"[green]✓[/green] Feedback submitted: {entry.feedback_id}")
        except Exception as e:
            console.print(f"[red]Error:[/red] {e}")
        return

    entries = get_recent_feedback(20)
    if not entries:
        console.print("[dim]No feedback entries yet.[/dim]")
        return
    t = Table(title="Recent Feedback", box=box.SIMPLE_HEAD, header_style="bold cyan")
    t.add_column("Date"); t.add_column("Company"); t.add_column("Signal")
    t.add_column("Type"); t.add_column("Severity"); t.add_column("Note")
    for e in entries:
        t.add_row(
            str(e.submitted_at)[:10], e.company_name, e.signal_type.value,
            e.feedback_type.value, e.original_severity.value, e.analyst_note[:40]
        )
    console.print(t)


def _run_audit(args: argparse.Namespace) -> None:
    from src.engines.audit_log import verify_chain, read_log

    if args.verify:
        valid, msg = verify_chain()
        if valid:
            console.print(f"[green]✓[/green] {msg}")
        else:
            console.print(f"[red]✗ Chain integrity failure:[/red] {msg}")
        return

    entries = read_log(args.tail)
    if not entries:
        console.print("[dim]No audit entries yet.[/dim]")
        return
    t = Table(title=f"Audit Log (last {len(entries)})", box=box.SIMPLE_HEAD, header_style="bold cyan")
    t.add_column("Timestamp"); t.add_column("Step"); t.add_column("Company")
    t.add_column("Action"); t.add_column("Hash (short)")
    for e in entries:
        t.add_row(str(e.timestamp)[:19], e.pipeline_step, e.company_name,
                  e.action, e.data_hash[:12] + "…")
    console.print(t)


def main() -> None:
    args = parse_args()
    try:
        if args.command == "feedback":
            _run_feedback(args)
        elif args.command == "audit":
            _run_audit(args)
        else:
            asyncio.run(_run_analysis(args))
    except KeyboardInterrupt:
        console.print("\n[dim]Interrupted.[/dim]")
        sys.exit(0)
    except RuntimeError as e:
        console.print(f"\n[bold red]Error:[/bold red] {e}")
        sys.exit(1)
    except Exception as e:
        console.print(f"\n[bold red]Unexpected error:[/bold red] {e}")
        raise


if __name__ == "__main__":
    main()
