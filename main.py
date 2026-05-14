#!/usr/bin/env python3
"""
Deal Intelligence Agent — CLI
Usage:
  python main.py --company "Apple Inc" --ticker AAPL
  python main.py --company "Bed Bath & Beyond" --lookback 180 --depth deep
  python main.py --company "Tesla" --ticker TSLA --output json
  python main.py --company "WeWork" --signals m_and_a_activity credit_risk --output markdown
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

console = Console()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Autonomous Deal Intelligence Agent — surfaces M&A, credit risk, and distressed signals from SEC filings + news.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py --company "Apple Inc" --ticker AAPL
  python main.py --company "Revlon" --lookback 180 --depth deep --output markdown
  python main.py --company "SVB Financial" --signals credit_risk debt_restructuring
        """
    )
    parser.add_argument("--company",  required=True, help="Company name to analyse")
    parser.add_argument("--ticker",   default=None,  help="Stock ticker (e.g. AAPL)")
    parser.add_argument("--cik",      default=None,  help="SEC CIK number if known")
    parser.add_argument(
        "--lookback", type=int, default=90,
        help="Days of history to scan (1-365, default: 90)"
    )
    parser.add_argument(
        "--depth", choices=["quick", "standard", "deep"], default="standard",
        help="Analysis depth (default: standard)"
    )
    parser.add_argument(
        "--signals", nargs="*",
        choices=[
            "m_and_a_activity", "credit_risk", "distressed_asset",
            "earnings_surprise", "leadership_change", "regulatory_action",
            "debt_restructuring", "insider_activity"
        ],
        default=[],
        help="Signal types to focus on (default: all)"
    )
    parser.add_argument(
        "--output", choices=["terminal", "json", "markdown"], default="terminal",
        help="Output format (default: terminal)"
    )
    parser.add_argument(
        "--out-file", default=None,
        help="Write output to file (e.g. brief.md or brief.json)"
    )
    return parser.parse_args()


async def _run(args: argparse.Namespace) -> None:
    from src.schemas.models import AnalysisRequest, SignalType
    from src.agents.graph import run_analysis
    from src.utils.formatter import print_brief, brief_to_json, brief_to_markdown

    # Build request
    focus = [SignalType(s) for s in (args.signals or [])]
    request = AnalysisRequest(
        company_name=args.company,
        ticker=args.ticker,
        cik=args.cik,
        lookback_days=args.lookback,
        depth=args.depth,
        focus_signals=focus,
    )

    console.print()
    console.print(Panel(
        f"[bold cyan]Deal Intelligence Agent[/bold cyan]\n\n"
        f"[white]Target:[/white] {args.company}"
        + (f" ([dim]{args.ticker}[/dim])" if args.ticker else "")
        + f"\n[white]Lookback:[/white] {args.lookback} days  "
        f"[white]Depth:[/white] {args.depth}",
        border_style="cyan",
        padding=(0, 2)
    ))
    console.print()

    steps = [
        "Resolving company via SEC EDGAR…",
        "Fetching filings + news concurrently…",
        "Running signal detection (Claude)…",
        "Synthesising analyst brief (Claude)…",
    ]

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        TimeElapsedColumn(),
        console=console,
        transient=True
    ) as progress:
        task = progress.add_task(steps[0], total=None)

        # Patch collection agent to update progress steps
        import src.agents.collection_agent as ca_mod
        import src.agents.signal_agent as sa_mod

        _orig_collect = ca_mod.DataCollectionAgent.run
        _orig_detect  = sa_mod.SignalDetectionAgent.run
        _orig_synth   = sa_mod.BriefSynthesisAgent.run

        async def _collect_with_progress(self, state):
            progress.update(task, description=steps[1])
            return await _orig_collect(self, state)

        async def _detect_with_progress(self, state):
            progress.update(task, description=steps[2])
            return await _orig_detect(self, state)

        async def _synth_with_progress(self, state):
            progress.update(task, description=steps[3])
            return await _orig_synth(self, state)

        ca_mod.DataCollectionAgent.run = _collect_with_progress
        sa_mod.SignalDetectionAgent.run = _detect_with_progress
        sa_mod.BriefSynthesisAgent.run  = _synth_with_progress

        try:
            brief = await run_analysis(request)
        finally:
            ca_mod.DataCollectionAgent.run = _orig_collect
            sa_mod.SignalDetectionAgent.run = _orig_detect
            sa_mod.BriefSynthesisAgent.run  = _orig_synth

    # Render output
    if args.output == "terminal":
        print_brief(brief)
        output_str = None
    elif args.output == "json":
        output_str = brief_to_json(brief)
        if not args.out_file:
            console.print_json(output_str)
    elif args.output == "markdown":
        output_str = brief_to_markdown(brief)
        if not args.out_file:
            console.print(output_str)

    # Write to file if requested
    if args.out_file and args.output != "terminal":
        Path(args.out_file).write_text(output_str, encoding="utf-8")
        console.print(f"\n[green]✓[/green] Brief written to [bold]{args.out_file}[/bold]")


def main() -> None:
    args = parse_args()
    try:
        asyncio.run(_run(args))
    except KeyboardInterrupt:
        console.print("\n[dim]Interrupted.[/dim]")
        sys.exit(0)
    except RuntimeError as e:
        console.print(f"\n[bold red]Error:[/bold red] {e}")
        sys.exit(1)
    except Exception as e:
        console.print(f"\n[bold red]Unexpected error:[/bold red] {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
