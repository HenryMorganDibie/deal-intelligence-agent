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
from rich.markup import escape

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


def _e(value) -> str:
    """Escape untrusted text (LLM output, news titles) so Rich does not parse it as markup."""
    return escape(str(value)) if value is not None else ""


def _cell(value) -> str:
    """Make text safe for a single Markdown table cell."""
    text = str(value) if value is not None else ""
    return " ".join(text.split()).replace("|", "\\|")


def _expected_move(a) -> Optional[str]:
    """'↓ -2.8% to +1.3% (median -1.3%, n=53)': the measured range after this kind of flag, else None."""
    from src.engines.measured import describe_move, signed_range
    lo, hi = signed_range(a.expected_direction, a.expected_magnitude_pct_low, a.expected_magnitude_pct_high)
    text = describe_move(lo, hi, getattr(a, "expected_median_pct", None), a.comparable_events_n)
    if text is None:
        return None
    median = getattr(a, "expected_median_pct", None)
    # An arrow only when the stated direction agrees with what similar flags measured.
    agrees = median is None or (a.expected_direction == "positive" and median > 0) or \
        (a.expected_direction == "negative" and median < 0)
    arrow = {"positive": "↑ ", "negative": "↓ "}.get(a.expected_direction or "", "") if agrees else ""
    return arrow + text


def _evidence_quality(sig) -> Optional[str]:
    d = sig.confidence_decomposition
    if d is None:
        return None
    return (f"{d.final_confidence:.0%} (source {d.source_reliability_score:.2f}, "
            f"corroboration {d.corroboration_score:.2f}, filing {d.filing_strength_score:.2f}, "
            f"precision {d.historical_precision_score:.2f}, entities {d.entity_match_confidence:.2f}, "
            f"recency {d.temporal_relevance_score:.2f}, extraction {d.extraction_confidence:.2f})")


def _title(value: str) -> str:
    return value.replace("_", " ").title()


def print_brief(brief: AnalystBrief) -> None:
    console.print()
    console.rule("[bold cyan]DEAL INTELLIGENCE BRIEF[/bold cyan]", style="cyan")

    # Header
    h = Table(box=None, padding=(0, 2))
    h.add_column("Field", style="dim", width=22)
    h.add_column("Value", style="bold white")
    h.add_row("Company",    Text(brief.company_name))
    h.add_row("Ticker",     Text(brief.ticker or "—"))
    h.add_row("Date",       brief.brief_date.strftime("%B %d, %Y %H:%M UTC"))
    h.add_row("Sources",    str(brief.total_sources))
    h.add_row("Candidates", str(brief.signal_candidates_count))
    h.add_row("Signals",    str(len(brief.detected_signals)))
    if brief.top_alpha_score is not None:
        h.add_row("Top Alpha",  f"{brief.top_alpha_score:.1f}/100")
    if brief.liquidity_tier:
        h.add_row("Liquidity",  _title(brief.liquidity_tier.value))
    h.add_row("Systemic Risk", _title(brief.systemic_risk_level.value))
    h.add_row("Runtime",    f"{brief.processing_time_seconds:.1f}s" if brief.processing_time_seconds else "—")
    h.add_row("Model",      Text(brief.analyst_model))
    console.print(h)
    console.print()

    # Compliance banner
    if brief.compliance_mode:
        flags = "\n".join(f"  ⚠ {_e(f)}" for f in brief.compliance_flags)
        console.print(Panel(
            f"[bold yellow]COMPLIANCE MODE ACTIVE[/bold yellow]\n{flags}",
            border_style="yellow", padding=(0, 2)
        ))
        console.print()

    # Human review banner
    if brief.requires_human_review:
        reasons = "\n".join(f"  • {_e(r)}" for r in brief.human_review_reasons)
        console.print(Panel(
            f"[bold red]⚑ HUMAN REVIEW REQUIRED BEFORE ACTING[/bold red]\n{reasons}",
            border_style="red", padding=(0, 2)
        ))
        console.print()

    # Executive summary
    sev_color = _severity_color(brief.overall_severity)
    conf_bar  = "█" * int(brief.confidence_score * 20) + "░" * (20 - int(brief.confidence_score * 20))
    event_probability = (
        f"Mean signal event probability [{conf_bar}] {brief.confidence_score:.0%}"
        if brief.detected_signals else "No confirmed signals; event probability unavailable"
    )
    console.print(Panel(
        f"[{sev_color}]{SEVERITY_ICONS[brief.overall_severity]} SEVERITY: {brief.overall_severity.value.upper()}[/{sev_color}]\n\n"
        f"[white]{_e(brief.executive_summary)}[/white]\n\n"
        f"[bold]Recommendation:[/bold] {_e(brief.recommendation)}\n\n"
        f"[dim]{event_probability}[/dim]",
        title="[bold]EXECUTIVE SUMMARY[/bold]",
        border_style=sev_color, padding=(1, 2)
    ))
    console.print()

    # Signal count
    counts = brief.signal_count_by_severity()
    parts  = [f"[{_severity_color(sev)}]{counts[sev.value]} {sev.value}[/{_severity_color(sev)}]"
              for sev in Severity if counts[sev.value] > 0]
    console.print(f"[bold]Signals:[/bold] {len(brief.detected_signals)} confirmed from "
                  f"{brief.signal_candidates_count} deterministic candidates"
                  + (f"  ({' | '.join(parts)})" if parts else ""))
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
                if a.learned_confirmation_probability is not None:
                    alpha_line += (
                        f"\n[bold]Estimated event confirmation:[/bold] "
                        f"{a.learned_confirmation_probability:.1%} "
                        "[dim](experimental learned estimate; separate from alpha)[/dim]"
                    )
                move = _expected_move(a)
                if move:
                    alpha_line += (
                        f"\n[bold]Measured move after similar flags:[/bold] [{color}]{move}[/{color}]"
                        f"  [dim](historical reference only; market-adjusted over 10 calendar days; "
                        f"{a.move_confidence} confidence; not a validated return forecast)[/dim]"
                    )
                if a.requires_human_review:
                    alpha_line += f"\n[bold red]⚑ HUMAN REVIEW: {_e(a.review_reason)}[/bold red]"
            if sig.attribution_doubt:
                alpha_line += f"\n[bold red]⚑ ATTRIBUTION DOUBT: {_e(sig.attribution_doubt)}[/bold red]"

            quality = _evidence_quality(sig)
            if quality:
                alpha_line += f"\n[dim]Evidence quality: {_e(quality)}[/dim]"

            patterns_line = ""
            if sig.candidate_patterns:
                patterns_line = f"\n[dim]Patterns: {_e(', '.join(sig.candidate_patterns[:3]))}[/dim]"

            console.print(Panel(
                f"[{color}]{SEVERITY_ICONS[sig.severity]} {sig.severity.value.upper()}[/{color}]  "
                f"[dim]{sig.signal_type.value.replace('_', ' ').title()}[/dim]  "
                f"[dim]Event probability: {sig.confidence:.0%}  Corroboration: {sig.corroboration_count}x[/dim]\n\n"
                f"[white]{_e(sig.headline)}[/white]\n\n"
                + "\n".join(f"  [dim]• {_e(e)}[/dim]" for e in sig.evidence[:4])
                + (f"\n\n[dim italic]{_e(sig.reasoning[:300])}{'...' if len(sig.reasoning) > 300 else ''}[/dim italic]"
                   if sig.reasoning else "")
                + alpha_line + patterns_line,
                title=f"[bold]{icon} Signal #{i}[/bold]",
                border_style=color, padding=(0, 2)
            ))
        console.print()

    # Compound events
    if brief.compound_signals:
        console.rule("[bold]COMPOUND EVENTS[/bold]", style="dim")
        t = Table(box=box.SIMPLE_HEAD, header_style="bold cyan")
        t.add_column("Signals"); t.add_column("Interaction")
        t.add_column("Escalation", justify="right"); t.add_column("Confidence", justify="right")
        t.add_column("Systemic"); t.add_column("Reasoning", style="dim")
        for c in brief.compound_signals:
            t.add_row(
                " + ".join(_title(st.value) for st in c.component_signal_types),
                _title(c.interaction_type.value),
                f"{c.escalation_score:.2f}", f"{c.compounded_confidence:.0%}",
                _title(c.systemic_risk_level.value), Text(c.reasoning_chain),
            )
        console.print(t); console.print()

    # Competitive context
    if brief.competitive_context:
        console.rule("[bold]COMPETITIVE CONTEXT[/bold]", style="dim")
        console.print(Text(brief.competitive_context)); console.print()

    # Key metrics
    if brief.key_metrics:
        console.rule("[bold]KEY METRICS[/bold]", style="dim")
        t = Table(box=box.SIMPLE_HEAD, header_style="bold cyan")
        t.add_column("Metric"); t.add_column("Value", style="bold white")
        t.add_column("Period", style="dim"); t.add_column("Interpretation")
        for m in brief.key_metrics:
            t.add_row(Text(m.name), Text(m.value), Text(m.period), Text(m.interpretation))
        console.print(t); console.print()

    # Risk factors
    if brief.risk_factors:
        console.rule("[bold]RISK FACTORS[/bold]", style="dim")
        t = Table(box=box.SIMPLE_HEAD, header_style="bold cyan")
        t.add_column("Risk"); t.add_column("Likelihood", justify="center")
        t.add_column("Impact"); t.add_column("Mitigation", style="dim")
        for rf in brief.risk_factors:
            c = _severity_color(rf.likelihood)
            t.add_row(Text(rf.factor), Text(rf.likelihood.value.upper(), style=c),
                      Text(rf.impact), Text(rf.mitigation or "—"))
        console.print(t); console.print()

    # Recent developments
    if brief.recent_developments:
        console.rule("[bold]RECENT DEVELOPMENTS[/bold]", style="dim")
        for dev in brief.recent_developments:
            console.print(f"  [dim]▸[/dim] {_e(dev)}")
        console.print()

    # Reasoning trace (abbreviated)
    if brief.reasoning_trace:
        console.rule("[bold]PIPELINE TRACE[/bold]", style="dim")
        t = Table(box=box.SIMPLE, header_style="bold cyan")
        t.add_column("Step", style="cyan"); t.add_column("Detail")
        for entry in brief.reasoning_trace[-8:]:
            t.add_row(Text(str(entry.get("step", ""))), Text(str(entry.get("detail", ""))[:100]))
        console.print(t); console.print()

    # Sources
    console.rule("[bold]SOURCES REVIEWED[/bold]", style="dim")
    t = Table(box=box.SIMPLE, header_style="bold cyan")
    t.add_column("Type", width=14); t.add_column("Form", width=22)
    t.add_column("Date", width=12); t.add_column("Company / Title")
    for f in brief.filings_reviewed[:8]:
        t.add_row("SEC/Exchange", Text(f.form_type), Text(f.filing_date), Text(f.company_name))
    for n in sorted(brief.news_reviewed, key=lambda x: x.relevance_score, reverse=True)[:6]:
        t.add_row("News", Text(n.source), Text(n.published_date),
                  Text(n.title[:60] + ("…" if len(n.title) > 60 else "")))
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
        (f"**Mean signal event probability:** {brief.confidence_score:.0%}  "
         if brief.detected_signals else "**Mean signal event probability:** — (no confirmed signals)  "),
        f"**Sources Reviewed:** {brief.total_sources}  ",
        f"**Deterministic Candidates:** {brief.signal_candidates_count}  ",
        f"**Confirmed Signals:** {len(brief.detected_signals)}  ",
    ]
    if brief.top_alpha_score is not None:
        lines.append(f"**Top Alpha Score:** {brief.top_alpha_score:.1f}/100  ")
    if brief.liquidity_tier:
        lines.append(f"**Liquidity:** {_title(brief.liquidity_tier.value)}  ")
    lines.append(f"**Systemic Risk:** {_title(brief.systemic_risk_level.value)}  ")
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
            f"**Event Probability:** {sig.confidence:.0%}  ",
            f"**Corroboration:** {sig.corroboration_count} source(s)  ",
        ]
        if sig.alpha_score:
            a = sig.alpha_score
            compound = (f" (compound-adjusted {a.compound_adjusted_score:.1f}, untested)"
                        if getattr(a, "compound_adjusted_score", None) is not None else "")
            lines.append(f"**Alpha Score:** {a.score:.1f}/100{compound}  ")
            if a.learned_confirmation_probability is not None:
                lines.append(
                    f"**Estimated event confirmation:** {a.learned_confirmation_probability:.1%} "
                    "(experimental learned estimate; separate from alpha)  "
                )
            move = _expected_move(a)
            if move:
                lines.append(f"**Measured move after similar flags:** {move}, market-adjusted over 10 trading "
                             f"days ({a.move_confidence} confidence; historical reference only, not a validated "
                             f"return forecast)  ")
            if a.requires_human_review:
                lines.append(f"\n> ⚑ **Human Review Required:** {a.review_reason}")
        if sig.attribution_doubt:
            lines.append(f"\n> ⚑ **Attribution Doubt:** {' '.join(sig.attribution_doubt.split())}\n")
        quality = _evidence_quality(sig)
        if quality:
            lines.append(f"**Evidence Quality:** {quality}  ")
            lines.append(f"*{sig.confidence_decomposition.reasoning}*  ")
        if sig.candidate_patterns:
            lines.append(f"**Patterns Fired:** `{'`, `'.join(sig.candidate_patterns[:3])}`  ")
        lines += ["", "**Evidence:**"]
        for e in sig.evidence:
            lines.append(f"- {e}")
        if sig.reasoning.strip():
            lines += ["", f"*{' '.join(sig.reasoning.split())}*"]
        lines.append("")

    if brief.compound_signals:
        lines += ["---", "", "## Compound Events", "",
                  "| Signals | Interaction | Escalation | Confidence | Systemic | Reasoning |",
                  "|---------|-------------|-----------:|-----------:|----------|-----------|"]
        for c in brief.compound_signals:
            lines.append(
                f"| {' + '.join(_title(st.value) for st in c.component_signal_types)} "
                f"| {_title(c.interaction_type.value)} | {c.escalation_score:.2f} "
                f"| {c.compounded_confidence:.0%} | {_title(c.systemic_risk_level.value)} "
                f"| {_cell(c.reasoning_chain)} |"
            )
        lines.append("")

    if brief.competitive_context:
        lines += ["---", "", "## Competitive Context", "", brief.competitive_context, ""]

    if brief.key_metrics:
        lines += ["---", "", "## Key Metrics", "",
                  "| Metric | Value | Period | Interpretation |",
                  "|--------|-------|--------|----------------|"]
        for m in brief.key_metrics:
            lines.append(f"| {_cell(m.name)} | {_cell(m.value)} | {_cell(m.period)} | {_cell(m.interpretation)} |")
        lines.append("")

    if brief.risk_factors:
        lines += ["---", "", "## Risk Factors", "",
                  "| Risk | Likelihood | Impact | Mitigation |",
                  "|------|-----------|--------|------------|"]
        for rf in brief.risk_factors:
            lines.append(f"| {_cell(rf.factor)} | {rf.likelihood.value.upper()} | {_cell(rf.impact)} "
                         f"| {_cell(rf.mitigation or '—')} |")
        lines.append("")

    if brief.recent_developments:
        lines += ["---", "", "## Recent Developments"]
        for dev in brief.recent_developments:
            lines.append(f"- {dev}")
        lines.append("")

    if brief.reasoning_trace:
        lines += ["---", "", "## Pipeline Trace", "", "| Step | Detail |", "|------|--------|"]
        for entry in brief.reasoning_trace:
            lines.append(f"| {_cell(entry.get('step', ''))} | {_cell(str(entry.get('detail', ''))[:120])} |")
        lines.append("")

    lines += [
        "---", "",
        f"*Generated by Deal Intelligence Agent | Model: {brief.analyst_model}*  ",
    ]
    if brief.processing_time_seconds:
        lines.append(f"*Processing time: {brief.processing_time_seconds:.1f}s*  ")
    lines.append("*AI-generated analysis. Inspect linked source evidence and review any flagged attribution or low-confidence signals before acting. Not investment advice.*")
    return "\n".join(lines)
