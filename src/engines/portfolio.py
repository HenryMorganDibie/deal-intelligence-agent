"""
Portfolio Intelligence Engine.
Aggregates company-level signals into portfolio-level risk views.
Funds think in portfolios, sectors, and contagion — this engine
translates individual company signals into institutional portfolio metrics.

Features:
  - Portfolio risk score (weighted by position size or equal-weight)
  - Sector concentration of risk
  - Contagion cluster detection
  - Exposure heat map data
  - Top-risk positions ranking
  - Portfolio-level compound event detection
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from src.schemas.models import Severity, SignalType, CompanyRiskProfile

PORTFOLIO_PATH = Path(__file__).resolve().parents[2] / "data" / "portfolios.json"

SEVERITY_WEIGHT = {
    Severity.LOW:      10.0,
    Severity.MEDIUM:   30.0,
    Severity.HIGH:     60.0,
    Severity.CRITICAL: 90.0,
}

SECTOR_SIGNAL_AFFINITY: dict[str, list[SignalType]] = {
    "fintech":      [SignalType.REGULATORY_ACTION, SignalType.CREDIT_RISK],
    "banking":      [SignalType.CREDIT_RISK, SignalType.DEBT_RESTRUCTURE, SignalType.REGULATORY_ACTION],
    "mining":       [SignalType.DISTRESSED_ASSET, SignalType.CREDIT_RISK],
    "telecom":      [SignalType.REGULATORY_ACTION, SignalType.MA_ACTIVITY],
    "real_estate":  [SignalType.CREDIT_RISK, SignalType.DEBT_RESTRUCTURE, SignalType.DISTRESSED_ASSET],
    "technology":   [SignalType.MA_ACTIVITY, SignalType.LEADERSHIP_CHANGE],
    "energy":       [SignalType.REGULATORY_ACTION, SignalType.CREDIT_RISK],
}


def _load_portfolios() -> dict:
    PORTFOLIO_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not PORTFOLIO_PATH.exists():
        return {}
    try:
        return json.loads(PORTFOLIO_PATH.read_text())
    except Exception:
        return {}


def _save_portfolios(data: dict) -> None:
    PORTFOLIO_PATH.write_text(json.dumps(data, indent=2, default=str))


class Portfolio:
    """
    A named collection of companies with optional position weights.
    Aggregates risk metrics across holdings.
    """

    def __init__(self, name: str):
        self.name = name
        portfolios = _load_portfolios()
        self._data = portfolios.get(name, {"name": name, "holdings": {}, "created_at": datetime.utcnow().isoformat()})

    def add_holding(
        self,
        company_name: str,
        ticker: Optional[str] = None,
        weight: float = 1.0,
        sector: Optional[str] = None,
        market: str = "US",
    ) -> None:
        """Add or update a holding. weight = position size as fraction of portfolio (0-1)."""
        self._data["holdings"][company_name] = {
            "ticker": ticker,
            "weight": weight,
            "sector": sector,
            "market": market,
            "added_at": datetime.utcnow().isoformat(),
        }
        self._save()

    def remove_holding(self, company_name: str) -> bool:
        if company_name in self._data["holdings"]:
            del self._data["holdings"][company_name]
            self._save()
            return True
        return False

    def _save(self) -> None:
        portfolios = _load_portfolios()
        portfolios[self.name] = self._data
        _save_portfolios(portfolios)

    def get_holdings(self) -> dict:
        return self._data.get("holdings", {})

    def aggregate_risk(self) -> dict:
        """
        Pull company memory profiles for all holdings and aggregate
        into portfolio-level risk metrics.
        """
        from src.engines.company_memory import get_profile

        holdings = self.get_holdings()
        if not holdings:
            return {"portfolio": self.name, "error": "No holdings"}

        profiles: list[tuple[str, dict, Optional[CompanyRiskProfile]]] = []
        for company, meta in holdings.items():
            profile = get_profile(company, meta.get("ticker"))
            profiles.append((company, meta, profile))

        # Weighted risk score
        total_weight = sum(m["weight"] for _, m, _ in profiles)
        weighted_risk = sum(
            (p.rolling_risk_score if p else 0.0) * m["weight"]
            for _, m, p in profiles
        ) / max(total_weight, 1.0)

        # Sector concentration
        sector_risk: dict[str, float] = {}
        for company, meta, profile in profiles:
            sector = meta.get("sector", "unknown")
            risk   = profile.rolling_risk_score if profile else 0.0
            sector_risk[sector] = sector_risk.get(sector, 0.0) + risk * meta["weight"]

        # Top risk positions
        ranked = sorted(
            [(company, meta, profile) for company, meta, profile in profiles],
            key=lambda x: x[2].rolling_risk_score if x[2] else 0.0,
            reverse=True,
        )

        top_risks = [
            {
                "company": company,
                "weight": meta["weight"],
                "risk_score": round(profile.rolling_risk_score, 1) if profile else None,
                "risk_trend": profile.risk_trend if profile else "unknown",
                "top_signals": list(profile.historical_signal_density.keys())[:3] if profile else [],
                "requires_attention": (profile.rolling_risk_score >= 60) if profile else False,
            }
            for company, meta, profile in ranked[:10]
        ]

        # Signal concentration across portfolio
        signal_counts: dict[str, int] = {}
        for _, _, profile in profiles:
            if profile:
                for sig_type, count in profile.historical_signal_density.items():
                    signal_counts[sig_type] = signal_counts.get(sig_type, 0) + count

        # High-risk position count
        high_risk_count = sum(
            1 for _, _, p in profiles
            if p and p.rolling_risk_score >= 60
        )

        # Contagion cluster detection: companies with shared risk signals
        contagion_pairs = []
        for i, (c1, _, p1) in enumerate(profiles):
            for c2, _, p2 in profiles[i+1:]:
                if not p1 or not p2:
                    continue
                shared = set(p1.historical_signal_density.keys()) & set(p2.historical_signal_density.keys())
                if len(shared) >= 2:
                    contagion_pairs.append({
                        "company_a": c1, "company_b": c2,
                        "shared_signal_types": list(shared),
                    })

        # Market exposure breakdown
        market_exposure: dict[str, float] = {}
        for _, meta, _ in profiles:
            m = meta.get("market", "unknown")
            market_exposure[m] = market_exposure.get(m, 0.0) + meta["weight"]
        total_w = sum(market_exposure.values())
        market_exposure = {k: round(v / max(total_w, 1), 3) for k, v in market_exposure.items()}

        return {
            "portfolio":               self.name,
            "computed_at":             datetime.utcnow().isoformat(),
            "total_holdings":          len(holdings),
            "holdings_with_profiles":  sum(1 for _, _, p in profiles if p),
            "weighted_portfolio_risk":  round(weighted_risk, 1),
            "portfolio_risk_level":    _risk_level(weighted_risk),
            "high_risk_positions":     high_risk_count,
            "sector_risk_concentration": {k: round(v / max(total_weight, 1), 1) for k, v in sector_risk.items()},
            "market_exposure":         market_exposure,
            "signal_concentration":    dict(sorted(signal_counts.items(), key=lambda x: x[1], reverse=True)[:5]),
            "contagion_pairs":         contagion_pairs[:5],
            "top_risk_positions":      top_risks,
        }


def _risk_level(score: float) -> str:
    if score >= 70:
        return "critical"
    if score >= 50:
        return "high"
    if score >= 30:
        return "medium"
    return "low"


def list_portfolios() -> list[str]:
    return list(_load_portfolios().keys())


def get_portfolio(name: str) -> Portfolio:
    return Portfolio(name)


def delete_portfolio(name: str) -> bool:
    portfolios = _load_portfolios()
    if name in portfolios:
        del portfolios[name]
        _save_portfolios(portfolios)
        return True
    return False
