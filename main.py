#!/usr/bin/env python3
"""
Deal Intelligence Agent — CLI
Commands:
  analyse   — run deal intelligence analysis
  feedback  — view/submit analyst feedback
  audit     — audit log operations
  monitor   — real-time monitoring watchlist
  memory    — company risk profiles
  replay    — deterministic historical replay
  outcomes  — market outcome tracking
  graph     — entity relationship graph
  registry  — signal type registry
  calibration — adaptive calibration report
"""
from __future__ import annotations
import argparse, asyncio, json, sys
from pathlib import Path
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.panel import Panel
from rich.table import Table
from rich import box

console = Console()


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Autonomous Deal Intelligence Agent — US & African markets",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = p.add_subparsers(dest="command")

    # ── analyse ──────────────────────────────────────────────────────────────
    a = sub.add_parser("analyse", aliases=["analyze"], help="Run deal intelligence analysis")
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
    a.add_argument("--compliance", action="store_true")

    # ── feedback ─────────────────────────────────────────────────────────────
    f = sub.add_parser("feedback", help="Analyst feedback and signal precision stats")
    f.add_argument("--list",   action="store_true")
    f.add_argument("--stats",  action="store_true")
    f.add_argument("--submit", nargs="+", metavar="KEY=VALUE")

    # ── audit ─────────────────────────────────────────────────────────────────
    au = sub.add_parser("audit", help="Audit log operations")
    au.add_argument("--verify", action="store_true")
    au.add_argument("--tail",   type=int, default=20)

    # ── monitor ───────────────────────────────────────────────────────────────
    mo = sub.add_parser("monitor", help="Real-time monitoring watchlist")
    mo.add_argument("--add",      nargs="+", metavar="COMPANY")
    mo.add_argument("--remove",   default=None)
    mo.add_argument("--list",     action="store_true")
    mo.add_argument("--run-once", action="store_true")
    mo.add_argument("--run",      action="store_true", help="Start continuous monitoring loop")
    mo.add_argument("--interval", type=int, default=3600)
    mo.add_argument("--ticker",   default=None)
    mo.add_argument("--alerts",   action="store_true")
    mo.add_argument("--webhook",  default=None)

    # ── memory ────────────────────────────────────────────────────────────────
    me = sub.add_parser("memory", help="Company longitudinal risk profiles")
    me.add_argument("--company", default=None)
    me.add_argument("--list",    action="store_true")
    me.add_argument("--watchlist-alerts", action="store_true")

    # ── replay ────────────────────────────────────────────────────────────────
    re_p = sub.add_parser("replay", help="Deterministic historical replay")
    re_p.add_argument("--company", required=True)
    re_p.add_argument("--date",    required=True, help="As-of date YYYY-MM-DD")
    re_p.add_argument("--run-id",  default=None)

    # ── outcomes ──────────────────────────────────────────────────────────────
    oc = sub.add_parser("outcomes", help="Market outcome tracking")
    oc.add_argument("--stats",   action="store_true")
    oc.add_argument("--signal",  default=None, help="Filter by signal type")
    oc.add_argument("--record",  nargs="+", metavar="KEY=VALUE")

    # ── graph ─────────────────────────────────────────────────────────────────
    gr = sub.add_parser("graph", help="Entity relationship graph")
    gr.add_argument("--summary",   action="store_true")
    gr.add_argument("--contagion", default=None, metavar="COMPANY")
    gr.add_argument("--connected", default=None, metavar="COMPANY")
    gr.add_argument("--add-lender", nargs=2, metavar=("LENDER","BORROWER"))

    # ── registry ──────────────────────────────────────────────────────────────
    rg = sub.add_parser("registry", help="Signal type registry")
    rg.add_argument("--list", action="store_true")
    rg.add_argument("--show", default=None, metavar="SIGNAL_TYPE")

    # ── calibration ───────────────────────────────────────────────────────────
    ca = sub.add_parser("calibration", help="Adaptive calibration report")
    ca.add_argument("--report", action="store_true")

    # Root-level bare flags for convenience (backwards compat)
    p.add_argument("--company",    default=None)
    p.add_argument("--ticker",     default=None)
    p.add_argument("--cik",        default=None)
    p.add_argument("--lookback",   type=int, default=90)
    p.add_argument("--depth",      choices=["quick","standard","deep"], default="standard")
    p.add_argument("--signals",    nargs="*", default=[])
    p.add_argument("--output",     choices=["terminal","json","markdown"], default="terminal")
    p.add_argument("--out-file",   default=None)
    p.add_argument("--compliance", action="store_true")
    return p


# ─── analyse ──────────────────────────────────────────────────────────────────

async def _run_analysis(args: argparse.Namespace) -> None:
    from src.schemas.models import AnalysisRequest, SignalType
    from src.agents.graph import run_analysis
    from src.utils.formatter import print_brief, brief_to_json, brief_to_markdown

    company = args.company
    if not company:
        console.print("[red]--company is required[/red]"); sys.exit(1)

    focus   = [SignalType(s) for s in (args.signals or [])]
    request = AnalysisRequest(
        company_name=company, ticker=args.ticker, cik=args.cik,
        lookback_days=args.lookback, depth=args.depth, focus_signals=focus,
    )
    compliance = getattr(args, "compliance", False)

    console.print()
    console.print(Panel(
        f"[bold cyan]Deal Intelligence Agent[/bold cyan]\n\n"
        f"[white]Target:[/white] {company}"
        + (f" ([dim]{args.ticker}[/dim])" if args.ticker else "")
        + f"\n[white]Lookback:[/white] {args.lookback} days  [white]Depth:[/white] {args.depth}"
        + (f"\n[yellow]Compliance Mode: ON[/yellow]" if compliance else ""),
        border_style="cyan", padding=(0,2)
    ))
    console.print()

    steps = [
        "Resolving company…",
        "Collecting EDGAR + African exchanges + news (concurrent)…",
        "Running deterministic signal engine…",
        "LLM explaining confirmed candidates…",
        "Computing alpha scores…",
        "Detecting compound signal interactions…",
        "Synthesising analyst brief…",
        "Storing to warehouse + updating memory…",
    ]

    import src.agents.collection_agent as ca
    import src.agents.signal_agent as sa

    _orig = {
        'collect':  ca.DataCollectionAgent.run,
        'det':      sa.DeterministicDetectionNode.run,
        'explain':  sa.LLMExplanationNode.run,
        'alpha':    sa.AlphaScoringNode.run,
        'synth':    sa.BriefSynthesisAgent.run,
    }

    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"),
                  TimeElapsedColumn(), console=console, transient=True) as progress:
        task = progress.add_task(steps[0], total=None)

        async def _c(self, state):
            progress.update(task, description=steps[1]); return await _orig['collect'](self, state)
        def _d(self, state):
            progress.update(task, description=steps[2]); return _orig['det'](self, state)
        async def _e(self, state):
            progress.update(task, description=steps[3]); return await _orig['explain'](self, state)
        def _a(self, state):
            progress.update(task, description=steps[4]); return _orig['alpha'](self, state)
        async def _s(self, state):
            progress.update(task, description=steps[6]); return await _orig['synth'](self, state)

        ca.DataCollectionAgent.run    = _c
        sa.DeterministicDetectionNode.run = _d
        sa.LLMExplanationNode.run     = _e
        sa.AlphaScoringNode.run       = _a
        sa.BriefSynthesisAgent.run    = _s

        try:
            brief = await run_analysis(request, compliance_mode=compliance)
        finally:
            ca.DataCollectionAgent.run        = _orig['collect']
            sa.DeterministicDetectionNode.run = _orig['det']
            sa.LLMExplanationNode.run         = _orig['explain']
            sa.AlphaScoringNode.run           = _orig['alpha']
            sa.BriefSynthesisAgent.run        = _orig['synth']

    if args.output == "terminal":
        print_brief(brief); return

    out = brief_to_json(brief) if args.output == "json" else brief_to_markdown(brief)
    if getattr(args, 'out_file', None):
        Path(args.out_file).write_text(out, encoding="utf-8")
        console.print(f"\n[green]✓[/green] Brief written to [bold]{args.out_file}[/bold]")
    else:
        console.print_json(out) if args.output == "json" else console.print(out)


# ─── feedback ─────────────────────────────────────────────────────────────────

def _run_feedback(args: argparse.Namespace) -> None:
    from src.engines.feedback import get_recent_feedback, get_signal_stats, submit_feedback
    from src.schemas.models import FeedbackType, SignalType, Severity

    if getattr(args, 'stats', False):
        stats = get_signal_stats()
        if not stats:
            console.print("[dim]No feedback data yet.[/dim]"); return
        t = Table(title="Signal Precision/Recall", box=box.SIMPLE_HEAD, header_style="bold cyan")
        for col in ["Signal Type","Total","Confirmed","False +ve","Precision","Recall"]:
            t.add_column(col)
        for sig, s in stats.items():
            t.add_row(sig, str(s["total"]), str(s["confirmed"]), str(s["false_positive"]),
                      f"{s['precision']:.0%}", f"{s['recall_proxy']:.0%}")
        console.print(t); return

    if getattr(args, 'submit', None):
        kv = dict(item.split("=",1) for item in args.submit if "=" in item)
        try:
            e = submit_feedback(
                company_name=kv.get("company","unknown"),
                signal_type=SignalType(kv.get("signal_type","credit_risk")),
                feedback_type=FeedbackType(kv.get("feedback_type","false_positive")),
                original_severity=Severity(kv.get("original_severity","medium")),
                analyst_note=kv.get("note",""),
            )
            console.print(f"[green]✓[/green] Feedback submitted: {e.feedback_id}")
        except Exception as e:
            console.print(f"[red]Error:[/red] {e}")
        return

    entries = get_recent_feedback(20)
    if not entries:
        console.print("[dim]No feedback entries yet.[/dim]"); return
    t = Table(title="Recent Feedback", box=box.SIMPLE_HEAD, header_style="bold cyan")
    for col in ["Date","Company","Signal","Type","Severity","Note"]:
        t.add_column(col)
    for e in entries:
        t.add_row(str(e.submitted_at)[:10], e.company_name, e.signal_type.value,
                  e.feedback_type.value, e.original_severity.value, e.analyst_note[:40])
    console.print(t)


# ─── audit ────────────────────────────────────────────────────────────────────

def _run_audit(args: argparse.Namespace) -> None:
    from src.engines.audit_log import verify_chain, read_log

    if getattr(args, 'verify', False):
        valid, msg = verify_chain()
        console.print(f"[green]✓[/green] {msg}" if valid else f"[red]✗ {msg}[/red]"); return

    entries = read_log(getattr(args, 'tail', 20))
    if not entries:
        console.print("[dim]No audit entries yet.[/dim]"); return
    t = Table(title="Audit Log", box=box.SIMPLE_HEAD, header_style="bold cyan")
    for col in ["Timestamp","Step","Company","Action","Hash"]:
        t.add_column(col)
    for e in entries:
        t.add_row(str(e.timestamp)[:19], e.pipeline_step, e.company_name,
                  e.action, e.data_hash[:12]+"…")
    console.print(t)


# ─── monitor ──────────────────────────────────────────────────────────────────

async def _run_monitor(args: argparse.Namespace) -> None:
    from src.engines.monitoring import (
        add_to_watchlist, remove_from_watchlist, get_watchlist,
        get_recent_alerts, MonitoringEngine
    )

    if getattr(args, 'add', None):
        for company in args.add:
            entry = add_to_watchlist(
                company, ticker=getattr(args,'ticker',None),
                webhook_url=getattr(args,'webhook',None)
            )
            console.print(f"[green]✓[/green] Added {company} to watchlist")
        return

    if getattr(args, 'remove', None):
        ok = remove_from_watchlist(args.remove)
        console.print(f"[green]✓[/green] Removed {args.remove}" if ok else f"[yellow]Not found: {args.remove}[/yellow]")
        return

    if getattr(args, 'alerts', False):
        alerts = get_recent_alerts(20)
        if not alerts:
            console.print("[dim]No alerts yet.[/dim]"); return
        t = Table(title="Recent Alerts", box=box.SIMPLE_HEAD, header_style="bold cyan")
        for col in ["Triggered","Company","Severity","Alpha","Signals","Headline"]:
            t.add_column(col)
        for a in alerts:
            t.add_row(str(a.get("triggered_at",""))[:16], a.get("company",""),
                      a.get("severity","").upper(), str(a.get("alpha_score") or "—"),
                      str(a.get("signal_count",0)), str(a.get("headline",""))[:60])
        console.print(t); return

    if getattr(args, 'run_once', False):
        console.print("[cyan]Running one monitoring cycle…[/cyan]")
        engine = MonitoringEngine()
        alerts = await engine.run_once()
        if alerts:
            console.print(f"[yellow]{len(alerts)} alert(s) triggered:[/yellow]")
            for a in alerts:
                console.print(f"  [bold]{a['company']}[/bold] — {a['severity'].upper()} — {a['headline'][:80]}")
        else:
            console.print("[green]No alerts triggered.[/green]")
        return

    if getattr(args, 'run', False):
        engine = MonitoringEngine(interval_seconds=args.interval)
        console.print(f"[cyan]Starting continuous monitoring (interval: {args.interval}s)…[/cyan]")
        console.print("[dim]Press Ctrl+C to stop.[/dim]")
        await engine.run_continuous()
        return

    # Default: list watchlist
    watchlist = get_watchlist()
    if not watchlist:
        console.print("[dim]Watchlist is empty. Use --add COMPANY to add.[/dim]"); return
    t = Table(title="Monitoring Watchlist", box=box.SIMPLE_HEAD, header_style="bold cyan")
    for col in ["Company","Ticker","Lookback","Alert Severity","Last Checked","Checks"]:
        t.add_column(col)
    for w in watchlist:
        t.add_row(w["company_name"], w.get("ticker") or "—",
                  str(w.get("lookback_days",30))+"d",
                  w.get("alert_severity","medium").upper(),
                  str(w.get("last_checked") or "never")[:16],
                  str(w.get("check_count",0)))
    console.print(t)


# ─── memory ───────────────────────────────────────────────────────────────────

def _run_memory(args: argparse.Namespace) -> None:
    from src.engines.company_memory import get_profile, list_profiles, get_watchlist_alerts

    if getattr(args, 'watchlist_alerts', False):
        profiles = get_watchlist_alerts(threshold=60.0)
        if not profiles:
            console.print("[green]No companies above alert threshold (60).[/green]"); return
        console.print(f"[yellow]{len(profiles)} company/companies above risk threshold:[/yellow]")
        for p in profiles:
            console.print(f"  [bold]{p.company_name}[/bold] — Risk: {p.rolling_risk_score:.1f} — Trend: {p.risk_trend}")
        return

    if getattr(args, 'company', None):
        profile = get_profile(args.company)
        if not profile:
            console.print(f"[dim]No profile found for {args.company}[/dim]"); return
        t = Table(title=f"Risk Profile: {profile.company_name}", box=box.SIMPLE_HEAD)
        t.add_column("Metric"); t.add_column("Value", style="bold white")
        t.add_row("Rolling Risk Score",    f"{profile.rolling_risk_score:.1f}/100")
        t.add_row("Governance Score",      f"{profile.governance_score:.1f}/100")
        t.add_row("Credit Risk Score",     f"{profile.credit_risk_score:.1f}/100")
        t.add_row("Regulatory Risk",       f"{profile.regulatory_risk_score:.1f}/100")
        t.add_row("Risk Trend",            profile.risk_trend)
        t.add_row("30d Delta",             f"{profile.risk_delta_30d:+.1f}")
        t.add_row("Event Velocity",        f"{profile.event_velocity:.1f} signals/30d")
        t.add_row("Total Signals",         str(profile.total_signals_detected))
        t.add_row("Analyses Run",          str(profile.total_analyses_run))
        t.add_row("Leadership Changes",    str(profile.leadership_change_count))
        t.add_row("Debt Restructures",     str(profile.debt_restructure_count))
        t.add_row("Regulatory Actions",    str(profile.regulatory_action_count))
        t.add_row("Analyst Attention",     f"{profile.analyst_attention_score:.1f}/100")
        t.add_row("Repeated Patterns",     ", ".join(profile.repeated_patterns) or "none")
        t.add_row("Last Updated",          str(profile.last_updated)[:19])
        console.print(t); return

    # List all profiles
    profiles = list_profiles(50)
    if not profiles:
        console.print("[dim]No company profiles yet. Run analyses to build memory.[/dim]"); return
    t = Table(title="Company Risk Profiles", box=box.SIMPLE_HEAD, header_style="bold cyan")
    for col in ["Company","Risk","Governance","Credit","Trend","Signals","Attention"]:
        t.add_column(col)
    for p in profiles:
        color = "red" if p.rolling_risk_score >= 70 else "yellow" if p.rolling_risk_score >= 40 else "green"
        t.add_row(p.company_name,
                  f"[{color}]{p.rolling_risk_score:.1f}[/{color}]",
                  f"{p.governance_score:.1f}", f"{p.credit_risk_score:.1f}",
                  p.risk_trend, str(p.total_signals_detected),
                  f"{p.analyst_attention_score:.1f}")
    console.print(t)


# ─── replay ───────────────────────────────────────────────────────────────────

async def _run_replay(args: argparse.Namespace) -> None:
    from src.engines.replay import ReplayEngine
    console.print(f"[cyan]Replaying {args.company} as-of {args.date}…[/cyan]")
    engine = ReplayEngine()
    result = await engine.replay(args.company, args.date, getattr(args,'run_id',None))
    console.print_json(json.dumps(result, indent=2, default=str))


# ─── outcomes ─────────────────────────────────────────────────────────────────

def _run_outcomes(args: argparse.Namespace) -> None:
    from src.engines.market_impact import get_accuracy_metrics, get_signal_accuracy, record_outcome
    from src.schemas.models import SignalType, Severity

    if getattr(args, 'stats', False):
        metrics = get_accuracy_metrics()
        console.print_json(json.dumps(metrics, indent=2))
        return

    if getattr(args, 'signal', None):
        try:
            metrics = get_signal_accuracy(SignalType(args.signal))
            console.print_json(json.dumps(metrics, indent=2))
        except ValueError:
            console.print(f"[red]Unknown signal type: {args.signal}[/red]")
        return

    if getattr(args, 'record', None):
        kv = dict(item.split("=",1) for item in args.record if "=" in item)
        try:
            outcome = record_outcome(
                company_name=kv.get("company","unknown"),
                signal_type=SignalType(kv.get("signal_type","credit_risk")),
                severity_at_detection=Severity(kv.get("severity","medium")),
                detection_date=kv.get("detection_date",""),
                price_change_10d_pct=float(kv["price_10d"]) if "price_10d" in kv else None,
                event_confirmed=kv.get("confirmed","").lower() == "true" if "confirmed" in kv else None,
                expected_direction=kv.get("expected_direction"),
            )
            console.print(f"[green]✓[/green] Outcome recorded: {outcome.outcome_id}")
        except Exception as e:
            console.print(f"[red]Error:[/red] {e}")


# ─── graph ────────────────────────────────────────────────────────────────────

def _run_graph(args: argparse.Namespace) -> None:
    from src.engines.graph_intelligence import EntityGraphEngine

    engine = EntityGraphEngine()

    if getattr(args, 'summary', False):
        console.print_json(json.dumps(engine.graph_summary(), indent=2)); return

    if getattr(args, 'contagion', None):
        result = engine.detect_contagion_risk(args.contagion)
        console.print_json(json.dumps(result, indent=2)); return

    if getattr(args, 'connected', None):
        companies = engine.get_connected_companies(args.connected, depth=2)
        console.print(f"Companies connected to {args.connected}: {companies}"); return

    if getattr(args, 'add_lender', None):
        lender, borrower = args.add_lender
        engine.add_lender_relationship(lender, borrower)
        engine.save()
        console.print(f"[green]✓[/green] Lender relationship added: {lender} → {borrower}")
        return

    console.print_json(json.dumps(engine.graph_summary(), indent=2))


# ─── registry ─────────────────────────────────────────────────────────────────

def _run_registry(args: argparse.Namespace) -> None:
    from src.engines.signal_registry import list_all_signals, get_signal_spec, SIGNAL_REGISTRY
    from src.schemas.models import SignalType

    if getattr(args, 'show', None):
        try:
            spec = get_signal_spec(SignalType(args.show))
            if not spec:
                console.print(f"[red]Not found: {args.show}[/red]"); return
            t = Table(title=f"Signal Spec: {spec.display_name}", box=box.SIMPLE_HEAD)
            t.add_column("Field"); t.add_column("Value")
            t.add_row("Description",    spec.description)
            t.add_row("Version",        spec.version)
            t.add_row("High patterns",  str(len(spec.trigger_patterns_high)))
            t.add_row("Medium patterns",str(len(spec.trigger_patterns_medium)))
            t.add_row("Low patterns",   str(len(spec.trigger_patterns_low)))
            t.add_row("Semantic types", ", ".join(spec.semantic_evidence_types) or "none")
            t.add_row("Escalates with", ", ".join(s.value for s in spec.escalates_with) or "none")
            t.add_row("Contradicts",    ", ".join(s.value for s in spec.contradicts) or "none")
            t.add_row("Base precision", f"{spec.historical_precision:.0%}")
            console.print(t)
        except ValueError:
            console.print(f"[red]Unknown signal type: {args.show}[/red]")
        return

    signals = list_all_signals()
    t = Table(title="Signal Registry", box=box.SIMPLE_HEAD, header_style="bold cyan")
    for col in ["Signal Type","Display Name","Patterns","Escalates With","Precision"]:
        t.add_column(col)
    for s in signals:
        t.add_row(s["signal_type"], s["display_name"], str(s["total_patterns"]),
                  ", ".join(s["escalates_with"][:2]) or "—", f"{s['historical_precision']:.0%}")
    console.print(t)


# ─── calibration ──────────────────────────────────────────────────────────────

def _run_calibration(args: argparse.Namespace) -> None:
    from src.engines.adaptive_calibration import get_calibration_report
    report = get_calibration_report()
    t = Table(title="Adaptive Calibration Report", box=box.SIMPLE_HEAD, header_style="bold cyan")
    for col in ["Signal","Samples","Adaptive?","Precision Adj","FP Penalty","Net Adj","FP Rate"]:
        t.add_column(col)
    for sig, r in report.items():
        active_color = "green" if r["adaptive_active"] else "dim"
        t.add_row(
            sig, str(r["feedback_samples"]),
            f"[{active_color}]{'YES' if r['adaptive_active'] else 'NO'}[/{active_color}]",
            str(r["precision_adjustment"]), str(r["fp_penalty"]),
            str(r["net_adjustment"]),
            str(r["false_positive_rate"])
        )
    console.print(t)


# ─── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    args = build_parser().parse_args()
    cmd  = args.command

    try:
        if cmd in ("analyse", "analyze", None):
            asyncio.run(_run_analysis(args))
        elif cmd == "feedback":
            _run_feedback(args)
        elif cmd == "audit":
            _run_audit(args)
        elif cmd == "monitor":
            asyncio.run(_run_monitor(args))
        elif cmd == "memory":
            _run_memory(args)
        elif cmd == "replay":
            asyncio.run(_run_replay(args))
        elif cmd == "outcomes":
            _run_outcomes(args)
        elif cmd == "graph":
            _run_graph(args)
        elif cmd == "registry":
            _run_registry(args)
        elif cmd == "calibration":
            _run_calibration(args)
        else:
            console.print("[red]Unknown command. Run with --help.[/red]")
    except KeyboardInterrupt:
        console.print("\n[dim]Interrupted.[/dim]"); sys.exit(0)
    except RuntimeError as e:
        console.print(f"\n[bold red]Error:[/bold red] {e}"); sys.exit(1)
    except Exception as e:
        console.print(f"\n[bold red]Unexpected error:[/bold red] {e}"); raise


if __name__ == "__main__":
    main()
