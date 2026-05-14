"""
Report Formatter.
Renders an AnalystBrief as:
  - Rich terminal output (for CLI use)
  - Clean JSON (for API/integration use)
  - Markdown (for documentation/export)
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Optional

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich import box
from rich.rule import Rule
from rich.columns import Columns

from src.schemas.models import AnalystBrief, DetectedSignal, Severity, SignalType

console = Console()

SEVERITY_COLORS = {
    Severity.LOW:      "green",
    Severity.MEDIUM:   "yellow",
    Severity.HIGH:     "orange3",
    Severity.CRITICAL: "bold red",
}

SEVERITY_ICONS = {
    Severity.LOW:      "●",
    Severity.MEDIUM:   "◆",
    Severity.HIGH:     "▲",
    Severity.CRITICAL: "⬟",
}

SIGNAL_ICONS = {
    SignalType.MA_ACTIVITY:       "🤝",
    SignalType.CREDIT_RISK:       "💳",
    SignalType.DISTRESSED_ASSET:  "⚠️",
    SignalType.EARNINGS_SURPRISE: "📊",
    SignalType.LEADERSHIP_CHANGE: "👔",
    SignalType.REGULATORY_ACTION: "⚖️",
    SignalType.DEBT_RESTRUCTURE:  "🔄",
    SignalType.INSIDER_ACTIVITY:  "🔍",
}


def _severity_badge(severity: Severity) -> Text:
    color = SEVERITY_COLORS[severity]
    icon  = SEVERITY_ICONS[severity]
    return Text(f"{icon} {severity.value.upper()}", style=color)


def print_brief(brief: AnalystBrief) -> None:
    """Render a full AnalystBrief to the terminal using Rich."""
    console.print()
    console.rule(f"[bold cyan]DEAL INTELLIGENCE BRIEF[/bold cyan]", style="cyan")

    # ── Header ──
    header_table = Table(box=None, padding=(0, 2))
    header_table.add_column("Field", style="dim", width=20)
    header_table.add_column("Value", style="bold white")
    header_table.add_row("Company",    brief.company_name)
    header_table.add_row("Ticker",     brief.ticker or "—")
    header_table.add_row("Date",       brief.brief_date.strftime("%B %d, %Y %H:%M UTC"))
    header_table.add_row("Model",      brief.analyst_model)
    header_table.add_row("Sources",    str(brief.total_sources))
    header_table.add_row("Runtime",    f"{brief.processing_time_seconds:.1f}s" if brief.processing_time_seconds else "—")
    console.print(header_table)
    console.print()

    # ── Overall Status ──
    sev_color = SEVERITY_COLORS[brief.overall_severity]
    conf_bar  = "█" * int(brief.confidence_score * 20) + "░" * (20 - int(brief.confidence_score * 20))
    status_panel = Panel(
        f"[{sev_color}]{SEVERITY_ICONS[brief.overall_severity]} SEVERITY: {brief.overall_severity.value.upper()}[/{sev_color}]\n\n"
        f"[white]{brief.executive_summary}[/white]\n\n"
        f"[bold]Recommendation:[/bold] {brief.recommendation}\n\n"
        f"[dim]Confidence [{conf_bar}] {brief.confidence_score:.0%}[/dim]",
        title="[bold]EXECUTIVE SUMMARY[/bold]",
        border_style=sev_color,
        padding=(1, 2)
    )
    console.print(status_panel)
    console.print()

    # ── Signal Count Summary ──
    counts = brief.signal_count_by_severity()
    count_parts = []
    for sev in Severity:
        if counts[sev.value] > 0:
            color = SEVERITY_COLORS[sev]
            count_parts.append(f"[{color}]{counts[sev.value]} {sev.value}[/{color}]")
    console.print(f"[bold]Signals detected:[/bold] {len(brief.detected_signals)} total  ({' | '.join(count_parts)})")
    console.print()

    # ── Detected Signals ──
    if brief.detected_signals:
        console.rule("[bold]DETECTED SIGNALS[/bold]", style="dim")
        for i, sig in enumerate(brief.top_signals(n=len(brief.detected_signals)), 1):
            icon  = SIGNAL_ICONS.get(sig.signal_type, "•")
            color = SEVERITY_COLORS[sig.severity]
            sig_panel = Panel(
                f"[{color}]{SEVERITY_ICONS[sig.severity]} {sig.severity.value.upper()}[/{color}]  "
                f"[dim]{sig.signal_type.value.replace('_', ' ').title()}[/dim]  "
                f"[dim]Confidence: {sig.confidence:.0%}[/dim]\n\n"
                f"[white]{sig.headline}[/white]\n\n"
                + "\n".join(f"  [dim]• {e}[/dim]" for e in sig.evidence[:3])
                + (f"\n\n[dim italic]{sig.reasoning[:300]}...[/dim italic]" if len(sig.reasoning) > 50 else ""),
                title=f"[bold]{icon} Signal #{i}[/bold]",
                border_style=color,
                padding=(0, 2)
            )
            console.print(sig_panel)
        console.print()

    # ── Key Metrics ──
    if brief.key_metrics:
        console.rule("[bold]KEY METRICS[/bold]", style="dim")
        m_table = Table(box=box.SIMPLE_HEAD, header_style="bold cyan")
        m_table.add_column("Metric")
        m_table.add_column("Value", style="bold white")
        m_table.add_column("Period", style="dim")
        m_table.add_column("Interpretation")
        for m in brief.key_metrics:
            m_table.add_row(m.name, m.value, m.period, m.interpretation)
        console.print(m_table)
        console.print()

    # ── Risk Factors ──
    if brief.risk_factors:
        console.rule("[bold]RISK FACTORS[/bold]", style="dim")
        r_table = Table(box=box.SIMPLE_HEAD, header_style="bold cyan")
        r_table.add_column("Risk")
        r_table.add_column("Likelihood", justify="center")
        r_table.add_column("Impact")
        r_table.add_column("Mitigation", style="dim")
        for rf in brief.risk_factors:
            color = SEVERITY_COLORS[rf.likelihood]
            r_table.add_row(
                rf.factor,
                Text(rf.likelihood.value.upper(), style=color),
                rf.impact,
                rf.mitigation or "—"
            )
        console.print(r_table)
        console.print()

    # ── Recent Developments ──
    if brief.recent_developments:
        console.rule("[bold]RECENT DEVELOPMENTS[/bold]", style="dim")
        for dev in brief.recent_developments:
            console.print(f"  [dim]▸[/dim] {dev}")
        console.print()

    # ── Sources ──
    console.rule("[bold]SOURCES REVIEWED[/bold]", style="dim")
    src_table = Table(box=box.SIMPLE, header_style="bold cyan")
    src_table.add_column("Type", width=12)
    src_table.add_column("Form", width=10)
    src_table.add_column("Date", width=12)
    src_table.add_column("Company")
    for f in brief.filings_reviewed[:8]:
        src_table.add_row("SEC Filing", f.form_type, f.filing_date, f.company_name)
    for n in sorted(brief.news_reviewed, key=lambda x: x.relevance_score, reverse=True)[:5]:
        src_table.add_row("News", n.source, n.published_date, n.title[:60] + ("…" if len(n.title) > 60 else ""))
    console.print(src_table)

    console.print()
    console.rule(style="dim")


def brief_to_json(brief: AnalystBrief, indent: int = 2) -> str:
    """Serialise brief to JSON string."""
    return brief.model_dump_json(indent=indent)


def brief_to_markdown(brief: AnalystBrief) -> str:
    """Render brief as clean Markdown for export/documentation."""
    lines = [
        f"# Deal Intelligence Brief: {brief.company_name}",
        f"**Date:** {brief.brief_date.strftime('%B %d, %Y')}  ",
        f"**Ticker:** {brief.ticker or '—'}  ",
        f"**Severity:** {brief.overall_severity.value.upper()}  ",
        f"**Confidence:** {brief.confidence_score:.0%}  ",
        f"**Sources Reviewed:** {brief.total_sources}  ",
        "",
        "---",
        "",
        "## Executive Summary",
        brief.executive_summary,
        "",
        f"**Recommendation:** {brief.recommendation}",
        "",
        "---",
        "",
        "## Detected Signals",
    ]

    for i, sig in enumerate(brief.top_signals(n=len(brief.detected_signals)), 1):
        icon = SIGNAL_ICONS.get(sig.signal_type, "•")
        lines += [
            f"### {icon} Signal {i}: {sig.headline}",
            f"**Type:** {sig.signal_type.value.replace('_', ' ').title()}  ",
            f"**Severity:** {sig.severity.value.upper()}  ",
            f"**Confidence:** {sig.confidence:.0%}  ",
            "",
            "**Evidence:**",
        ]
        for e in sig.evidence:
            lines.append(f"- {e}")
        lines += ["", f"*{sig.reasoning}*", ""]

    if brief.key_metrics:
        lines += ["---", "", "## Key Metrics", "", "| Metric | Value | Period | Interpretation |", "|--------|-------|--------|----------------|"]
        for m in brief.key_metrics:
            lines.append(f"| {m.name} | {m.value} | {m.period} | {m.interpretation} |")
        lines.append("")

    if brief.risk_factors:
        lines += ["---", "", "## Risk Factors", "", "| Risk | Likelihood | Impact | Mitigation |", "|------|-----------|--------|------------|"]
        for rf in brief.risk_factors:
            lines.append(f"| {rf.factor} | {rf.likelihood.value.upper()} | {rf.impact} | {rf.mitigation or '—'} |")
        lines.append("")

    if brief.recent_developments:
        lines += ["---", "", "## Recent Developments"]
        for dev in brief.recent_developments:
            lines.append(f"- {dev}")
        lines.append("")

    lines += [
        "---",
        "",
        f"*Generated by Deal Intelligence Agent | Model: {brief.analyst_model}*",
        f"*Processing time: {brief.processing_time_seconds:.1f}s*" if brief.processing_time_seconds else ""
    ]

    return "\n".join(lines)
