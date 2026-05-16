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


def _severity_color(s: Severity) -> str:
    return SEVERITY_COLORS[s]


def print_brief(brief: AnalystBrief) -> None:
    console.print()
    console.rule("[bold cyan]DEAL INTELLIGENCE BRIEF[/bold cyan]", style="cyan")

    # Header
    h = Table(box=None, padding=(0, 2))
    h.add_column("Field", style="dim", width=22)
    h.add_column("Value", style="bold white")
    h.add_row("Company",    brief.company_name)
    h.add_row("Ticker",     brief.ticker or "—")
    h.add_row("Date",       brief.brief_date.strftime("%B %d, %Y %H:%M UTC"))
    h.add_row("Sources",    str(brief.total_sources))
    h.add_row("Candidates", str(brief.signal_candidates_count))
    h.add_row("Signals",    str(len(brief.detected_signals)))
    if brief.top_alpha_score is not None:
        h.add_row("Top Alpha",  f"{brief.top_alpha_score:.1f}/100")
    if brief.liquidity_tier:
        h.add_row("Liquidity",  brief.liquidity_tier.value.replace("_", " ").title())
    h.add_row("Runtime",    f"{brief.processing_time_seconds:.1f}s" if brief.processing_time_seconds else "—")
    h.add_row("Model",      brief.analyst_model)
    console.print(h)
    console.print()

    # Compliance banner
    if brief.compliance_mode:
        flags = "\n".join(f"  ⚠ {f}" for f in brief.compliance_flags)
        console.print(Panel(
            f"[bold yellow]COMPLIANCE MODE ACTIVE[/bold yellow]\n{flags}",
            border_style="yellow", padding=(0, 2)
        ))
        console.print()

    # Human review banner
    if brief.requires_human_review:
        reasons = "\n".join(f"  • {r}" for r in brief.human_review_reasons)
        console.print(Panel(
            f"[bold red]⚑ HUMAN REVIEW REQUIRED BEFORE ACTING[/bold red]\n{reasons}",
            border_style="red", padding=(0, 2)
        ))
        console.print()

    # Executive summary
    sev_color = _severity_color(brief.overall_severity)
    conf_bar  = "█" * int(brief.confidence_score * 20) + "░" * (20 - int(brief.confidence_score * 20))
    console.print(Panel(
        f"[{sev_color}]{SEVERITY_ICONS[brief.overall_severity]} SEVERITY: {brief.overall_severity.value.upper()}[/{sev_color}]\n\n"
        f"[white]{brief.executive_summary}[/white]\n\n"
        f"[bold]Recommendation:[/bold] {brief.recommendation}\n\n"
        f"[dim]Confidence [{conf_bar}] {brief.confidence_score:.0%}[/dim]",
        title="[bold]EXECUTIVE SUMMARY[/bold]",
        border_style=sev_color, padding=(1, 2)
    ))
    console.print()

    # Signal count
    counts = brief.signal_count_by_severity()
    parts  = [f"[{_severity_color(sev)}]{counts[sev.value]} {sev.value}[/{_severity_color(sev)}]"
              for sev in Severity if counts[sev.value] > 0]
    console.print(f"[bold]Signals:[/bold] {len(brief.detected_signals)} confirmed from "
                  f"{brief.signal_candidates_count} deterministic candidates  ({' | '.join(parts)})")
    console.print()

    # Signals
    if brief.detected_signals:
        console.rule("[bold]CONFIRMED SIGNALS[/bold]", style="dim")
        for i, sig in enumerate(brief.top_signals(n=len(brief.detected_signals)), 1):
            icon  = SIGNAL_ICONS.get(sig.signal_type, "•")
            color = _severity_color(sig.severity)

            alpha_line = ""
            if sig.alpha_score:
                a = sig.alpha_score
                alpha_line = (
                    f"\n[bold]Alpha Score:[/bold] [cyan]{a.score:.1f}/100[/cyan]  "
                    f"[dim]Credibility:{a.source_credibility:.2f}  "
                    f"Corroboration:{a.corroboration_weight:.2f}  "
                    f"Recency:{a.recency_weight:.2f}[/dim]"
                )
                if a.expected_direction and a.expected_direction != "neutral":
                    arrow = "↑" if a.expected_direction == "positive" else "↓"
                    alpha_line += (
                        f"\n[bold]Expected Move:[/bold] [{color}]{arrow} "
                        f"{a.expected_magnitude_pct_low:.0f}–{a.expected_magnitude_pct_high:.0f}%[/{color}]"
                        f"  [dim](n={a.comparable_events_n}, confidence={a.move_confidence})[/dim]"
                    )
                if a.requires_human_review:
                    alpha_line += f"\n[bold red]⚑ HUMAN REVIEW: {a.review_reason}[/bold red]"

            patterns_line = ""
            if sig.candidate_patterns:
                patterns_line = f"\n[dim]Patterns: {', '.join(sig.candidate_patterns[:3])}[/dim]"

            console.print(Panel(
                f"[{color}]{SEVERITY_ICONS[sig.severity]} {sig.severity.value.upper()}[/{color}]  "
                f"[dim]{sig.signal_type.value.replace('_', ' ').title()}[/dim]  "
                f"[dim]Confidence: {sig.confidence:.0%}  Corroboration: {sig.corroboration_count}x[/dim]\n\n"
                f"[white]{sig.headline}[/white]\n\n"
                + "\n".join(f"  [dim]• {e}[/dim]" for e in sig.evidence[:4])
                + (f"\n\n[dim italic]{sig.reasoning[:300]}{'...' if len(sig.reasoning) > 300 else ''}[/dim italic]"
                   if sig.reasoning else "")
                + alpha_line + patterns_line,
                title=f"[bold]{icon} Signal #{i}[/bold]",
                border_style=color, padding=(0, 2)
            ))
        console.print()

    # Key metrics
    if brief.key_metrics:
        console.rule("[bold]KEY METRICS[/bold]", style="dim")
        t = Table(box=box.SIMPLE_HEAD, header_style="bold cyan")
        t.add_column("Metric"); t.add_column("Value", style="bold white")
        t.add_column("Period", style="dim"); t.add_column("Interpretation")
        for m in brief.key_metrics:
            t.add_row(m.name, m.value, m.period, m.interpretation)
        console.print(t); console.print()

    # Risk factors
    if brief.risk_factors:
        console.rule("[bold]RISK FACTORS[/bold]", style="dim")
        t = Table(box=box.SIMPLE_HEAD, header_style="bold cyan")
        t.add_column("Risk"); t.add_column("Likelihood", justify="center")
        t.add_column("Impact"); t.add_column("Mitigation", style="dim")
        for rf in brief.risk_factors:
            c = _severity_color(rf.likelihood)
            t.add_row(rf.factor, Text(rf.likelihood.value.upper(), style=c), rf.impact, rf.mitigation or "—")
        console.print(t); console.print()

    # Recent developments
    if brief.recent_developments:
        console.rule("[bold]RECENT DEVELOPMENTS[/bold]", style="dim")
        for dev in brief.recent_developments:
            console.print(f"  [dim]▸[/dim] {dev}")
        console.print()

    # Reasoning trace (abbreviated)
    if brief.reasoning_trace:
        console.rule("[bold]PIPELINE TRACE[/bold]", style="dim")
        t = Table(box=box.SIMPLE, header_style="bold cyan")
        t.add_column("Step", style="cyan"); t.add_column("Detail")
        for entry in brief.reasoning_trace[-8:]:
            t.add_row(entry.get("step",""), str(entry.get("detail",""))[:100])
        console.print(t); console.print()

    # Sources
    console.rule("[bold]SOURCES REVIEWED[/bold]", style="dim")
    t = Table(box=box.SIMPLE, header_style="bold cyan")
    t.add_column("Type", width=14); t.add_column("Form", width=22)
    t.add_column("Date", width=12); t.add_column("Company / Title")
    for f in brief.filings_reviewed[:8]:
        t.add_row("SEC/Exchange", f.form_type, f.filing_date, f.company_name)
    for n in sorted(brief.news_reviewed, key=lambda x: x.relevance_score, reverse=True)[:6]:
        t.add_row("News", n.source, n.published_date,
                  n.title[:60] + ("…" if len(n.title) > 60 else ""))
    console.print(t)
    console.print()
    console.rule(style="dim")


def brief_to_json(brief: AnalystBrief, indent: int = 2) -> str:
    return brief.model_dump_json(indent=indent)


def brief_to_markdown(brief: AnalystBrief) -> str:
    lines = [
        f"# Deal Intelligence Brief: {brief.company_name}",
        f"**Date:** {brief.brief_date.strftime('%B %d, %Y')}  ",
        f"**Ticker:** {brief.ticker or '—'}  ",
        f"**Severity:** {brief.overall_severity.value.upper()}  ",
        f"**Confidence:** {brief.confidence_score:.0%}  ",
        f"**Sources Reviewed:** {brief.total_sources}  ",
        f"**Deterministic Candidates:** {brief.signal_candidates_count}  ",
        f"**Confirmed Signals:** {len(brief.detected_signals)}  ",
    ]
    if brief.top_alpha_score is not None:
        lines.append(f"**Top Alpha Score:** {brief.top_alpha_score:.1f}/100  ")
    if brief.compliance_mode:
        lines.append(f"**Compliance Mode:** ON  ")
        for f in brief.compliance_flags:
            lines.append(f"⚠ {f}  ")
    if brief.requires_human_review:
        lines.append(f"\n> ⚑ **HUMAN REVIEW REQUIRED BEFORE ACTING**")
        for r in brief.human_review_reasons:
            lines.append(f"> {r}")

    lines += ["", "---", "", "## Executive Summary", brief.executive_summary, "",
              f"**Recommendation:** {brief.recommendation}", "", "---", "", "## Confirmed Signals"]

    for i, sig in enumerate(brief.top_signals(n=len(brief.detected_signals)), 1):
        icon = SIGNAL_ICONS.get(sig.signal_type, "•")
        lines += [
            f"### {icon} Signal {i}: {sig.headline}",
            f"**Type:** {sig.signal_type.value.replace('_', ' ').title()}  ",
            f"**Severity:** {sig.severity.value.upper()}  ",
            f"**Confidence:** {sig.confidence:.0%}  ",
            f"**Corroboration:** {sig.corroboration_count} source(s)  ",
        ]
        if sig.alpha_score:
            a = sig.alpha_score
            lines.append(f"**Alpha Score:** {a.score:.1f}/100  ")
            if a.expected_direction and a.expected_direction != "neutral":
                arrow = "↑" if a.expected_direction == "positive" else "↓"
                lines.append(f"**Expected Move:** {arrow} {a.expected_magnitude_pct_low:.0f}–"
                              f"{a.expected_magnitude_pct_high:.0f}% "
                              f"(n={a.comparable_events_n}, {a.move_confidence} confidence)  ")
            if a.requires_human_review:
                lines.append(f"\n> ⚑ **Human Review Required:** {a.review_reason}")
        if sig.candidate_patterns:
            lines.append(f"**Patterns Fired:** `{'`, `'.join(sig.candidate_patterns[:3])}`  ")
        lines += ["", "**Evidence:**"]
        for e in sig.evidence:
            lines.append(f"- {e}")
        lines += ["", f"*{sig.reasoning}*", ""]

    if brief.key_metrics:
        lines += ["---", "", "## Key Metrics", "",
                  "| Metric | Value | Period | Interpretation |",
                  "|--------|-------|--------|----------------|"]
        for m in brief.key_metrics:
            lines.append(f"| {m.name} | {m.value} | {m.period} | {m.interpretation} |")
        lines.append("")

    if brief.risk_factors:
        lines += ["---", "", "## Risk Factors", "",
                  "| Risk | Likelihood | Impact | Mitigation |",
                  "|------|-----------|--------|------------|"]
        for rf in brief.risk_factors:
            lines.append(f"| {rf.factor} | {rf.likelihood.value.upper()} | {rf.impact} | {rf.mitigation or '—'} |")
        lines.append("")

    if brief.recent_developments:
        lines += ["---", "", "## Recent Developments"]
        for dev in brief.recent_developments:
            lines.append(f"- {dev}")
        lines.append("")

    if brief.reasoning_trace:
        lines += ["---", "", "## Pipeline Trace", "", "| Step | Detail |", "|------|--------|"]
        for entry in brief.reasoning_trace:
            lines.append(f"| {entry.get('step','')} | {str(entry.get('detail',''))[:120]} |")
        lines.append("")

    lines += [
        "---", "",
        f"*Generated by Deal Intelligence Agent | Model: {brief.analyst_model}*",
        f"*Processing time: {brief.processing_time_seconds:.1f}s*" if brief.processing_time_seconds else "",
        "*Output is AI-generated, unverified, not investment advice.*"
    ]
    return "\n".join(lines)
