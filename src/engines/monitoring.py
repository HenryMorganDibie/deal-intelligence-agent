"""
Real-Time Monitoring & Alerting Engine (#13).
Continuously polls data sources for monitored companies,
generates incremental signals, and delivers alerts.
Delivery channels: terminal, webhook, Slack (via webhook), email stub.
Run: python main.py monitor --companies GTBank Shoprite --interval 60
"""
from __future__ import annotations

from src.utils.storage import load_json, save_json
import asyncio
import os
from typing import Optional

import httpx

from src.schemas.models import AnalysisRequest, AnalystBrief, Severity
from src.utils.clock import utcnow
from src.utils.paths import DATA_DIR

WATCHLIST_PATH = DATA_DIR / "watchlist.json"
ALERTS_PATH    = DATA_DIR / "alerts.json"

# Alert thresholds
ALERT_SEVERITY_THRESHOLD = Severity.MEDIUM      # alert on MEDIUM and above
ALERT_ALPHA_THRESHOLD    = 50.0                 # alert when alpha score >= 50


def _load_watchlist() -> list[dict]:
    return load_json(WATCHLIST_PATH, lambda: [])


def _save_watchlist(data: list) -> None:
    save_json(WATCHLIST_PATH, data)


def _load_alerts() -> list[dict]:
    return load_json(ALERTS_PATH, lambda: [])


def _save_alert(alert: dict) -> None:
    alerts = _load_alerts()
    alerts.append(alert)
    alerts = alerts[-500:]  # keep last 500
    save_json(ALERTS_PATH, alerts)


def add_to_watchlist(
    company_name: str,
    ticker: Optional[str] = None,
    lookback_days: int = 30,
    alert_severity: str = "medium",
    alert_alpha: float = 50.0,
    webhook_url: Optional[str] = None,
) -> dict:
    """Add a company to the monitoring watchlist."""
    watchlist = _load_watchlist()
    entry = {
        "company_name": company_name,
        "ticker": ticker,
        "lookback_days": lookback_days,
        "alert_severity": alert_severity,
        "alert_alpha": alert_alpha,
        "webhook_url": webhook_url,
        "added_at": utcnow().isoformat(),
        "last_checked": None,
        "last_signal_severity": None,
        "check_count": 0,
    }
    # Update if exists
    existing = next((i for i, w in enumerate(watchlist) if w["company_name"] == company_name), None)
    if existing is not None:
        watchlist[existing] = entry
    else:
        watchlist.append(entry)
    _save_watchlist(watchlist)
    return entry


def remove_from_watchlist(company_name: str) -> bool:
    """Remove a company from the watchlist."""
    watchlist = _load_watchlist()
    filtered = [w for w in watchlist if w["company_name"] != company_name]
    if len(filtered) < len(watchlist):
        _save_watchlist(filtered)
        return True
    return False


def get_watchlist() -> list[dict]:
    return _load_watchlist()


def get_recent_alerts(limit: int = 50) -> list[dict]:
    return list(reversed(_load_alerts()[-limit:]))


_SEVERITY_ORDER = {Severity.LOW: 0, Severity.MEDIUM: 1, Severity.HIGH: 2, Severity.CRITICAL: 3}


def _parse_severity(value: Optional[str]) -> Optional[Severity]:
    try:
        return Severity(value) if value else None
    except ValueError:
        return None


def _should_alert(brief: AnalystBrief, entry: dict) -> bool:
    """Determine if a brief warrants an alert for this watchlist entry."""
    severity_order = {
        Severity.LOW: 0, Severity.MEDIUM: 1,
        Severity.HIGH: 2, Severity.CRITICAL: 3
    }
    threshold_order = severity_order.get(
        Severity(entry.get("alert_severity", "medium")), 1
    )
    brief_order = severity_order.get(brief.overall_severity, 0)
    alpha_trigger = brief.top_alpha_score and brief.top_alpha_score >= entry.get("alert_alpha", 50.0)
    return brief_order >= threshold_order or bool(alpha_trigger)


async def _deliver_webhook(url: str, payload: dict) -> bool:
    """POST alert payload to a webhook URL."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post(url, json=payload)
            return r.status_code < 300
    except Exception:
        return False


async def _deliver_slack(webhook_url: str, brief: AnalystBrief, company: str) -> bool:
    """Send Slack-formatted alert via incoming webhook."""
    severity_emoji = {
        Severity.LOW: "🟢", Severity.MEDIUM: "🟡",
        Severity.HIGH: "🟠", Severity.CRITICAL: "🔴"
    }
    emoji = severity_emoji.get(brief.overall_severity, "⚪")
    signals_text = "\n".join(
        f"• *{s.signal_type.value.replace('_',' ').title()}* — {s.headline}"
        for s in brief.top_signals(3)
    )
    payload = {
        "blocks": [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": f"{emoji} Deal Intel Alert: {company}"}
            },
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*Severity:* {brief.overall_severity.value.upper()}\n*Alpha:* {brief.top_alpha_score:.1f}/100" if brief.top_alpha_score else f"*Severity:* {brief.overall_severity.value.upper()}"}
            },
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*Summary:*\n{brief.executive_summary}"}
            },
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*Top Signals:*\n{signals_text}"}
            },
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*Recommendation:* {brief.recommendation}"}
            },
        ]
    }
    return await _deliver_webhook(webhook_url, payload)


async def _check_company(entry: dict) -> Optional[dict]:
    """Run one analysis for a watchlist company and return alert if triggered."""
    from src.agents.graph import run_analysis

    company = entry["company_name"]
    ticker  = entry.get("ticker")

    request = AnalysisRequest(
        company_name=company,
        ticker=ticker,
        lookback_days=entry.get("lookback_days", 30),
    )

    try:
        brief = await run_analysis(request)
    except Exception as e:
        return {"company": company, "error": str(e), "checked_at": utcnow().isoformat()}

    if not _should_alert(brief, entry):
        return {"company": company, "checked_at": utcnow().isoformat(), "alert_keys": []}

    # Alert on change, not on every cycle: only new events or a severity escalation.
    from src.engines.company_memory import _signal_key
    keys = sorted({_signal_key(sig) for sig in brief.detected_signals})
    previous = set(entry.get("alerted_signal_keys") or [])
    escalated = _SEVERITY_ORDER[brief.overall_severity] > _SEVERITY_ORDER.get(
        _parse_severity(entry.get("last_alert_severity")), -1)
    if previous and set(keys) <= previous and not escalated:
        return {"company": company, "checked_at": utcnow().isoformat(),
                "alert_keys": sorted(previous), "suppressed_repeat": True}

    alert = {
        "alert_id": f"alert_{utcnow().strftime('%Y%m%d_%H%M%S')}_{company[:8]}",
        "company": company,
        "ticker": ticker,
        "severity": brief.overall_severity.value,
        "alpha_score": brief.top_alpha_score,
        "signal_count": len(brief.detected_signals),
        "headline": brief.executive_summary[:200],
        "recommendation": brief.recommendation,
        "requires_human_review": brief.requires_human_review,
        "triggered_at": utcnow().isoformat(),
        "signals": [
            {"type": s.signal_type.value, "severity": s.severity.value, "headline": s.headline}
            for s in brief.top_signals(3)
        ]
    }

    # Deliver to webhook if configured, and record whether delivery worked.
    webhook = entry.get("webhook_url") or os.getenv("DEAL_INTEL_WEBHOOK_URL")
    alert["delivered"] = None
    if webhook:
        if "hooks.slack.com" in webhook:
            alert["delivered"] = await _deliver_slack(webhook, brief, company)
        else:
            alert["delivered"] = await _deliver_webhook(webhook, dict(alert))
    alert["alert_keys"] = keys
    _save_alert(alert)
    return alert


class MonitoringEngine:
    """
    Continuous monitoring loop for the watchlist.
    Polls all companies on the configured interval.
    """

    def __init__(self, interval_seconds: int = 3600):
        self.interval = interval_seconds
        self._running = False

    async def run_once(self) -> list[dict]:
        """Run one check cycle across all watchlist companies. Returns triggered alerts."""
        watchlist = _load_watchlist()
        if not watchlist:
            return []

        tasks   = [_check_company(entry) for entry in watchlist]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        alerts  = []
        # Match results back by company, not position: the watchlist may have
        # changed while this cycle was running.
        updated = _load_watchlist()
        by_name = {w["company_name"]: w for w in updated}
        for entry, result in zip(watchlist, results):
            current = by_name.get(entry["company_name"])
            if current is not None:
                current["last_checked"] = utcnow().isoformat()
                current["check_count"]  = current.get("check_count", 0) + 1
                if isinstance(result, dict) and result.get("alert_id"):
                    current["last_signal_severity"] = result.get("severity")
                    current["last_alert_severity"]  = result.get("severity")
                    current["alerted_signal_keys"]  = result.get("alert_keys", [])
            if isinstance(result, dict) and result.get("alert_id"):
                alerts.append(result)
        _save_watchlist(updated)
        return alerts

    async def run_continuous(self, console_output: bool = True) -> None:
        """Run continuous monitoring loop until stopped."""
        self._running = True
        if console_output:
            print(f"[Monitor] Starting continuous monitoring. Interval: {self.interval}s")
            print(f"[Monitor] Watching {len(_load_watchlist())} companies")

        while self._running:
            if console_output:
                print(f"[Monitor] {utcnow().strftime('%Y-%m-%d %H:%M:%S')} — Running check cycle...")
            alerts = await self.run_once()
            if alerts and console_output:
                for a in alerts:
                    print(f"[ALERT] {a['company']} — {a['severity'].upper()} — {a['headline']}")
            await asyncio.sleep(self.interval)

    def stop(self) -> None:
        self._running = False
