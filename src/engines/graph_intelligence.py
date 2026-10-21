"""
Cross-Signal Graph Intelligence (#11).
Builds entity relationship graphs to detect systemic and second-order risk.
Tracks shared executives, lender relationships, board overlaps,
acquisition chains, and regulatory network effects across companies.
Uses NetworkX for graph operations. No LLM required.
"""
from __future__ import annotations

from src.utils.storage import load_json, save_json
import re
from typing import Any, Optional

import networkx as nx
from src.utils.clock import utcnow
from src.utils.paths import DATA_DIR

GRAPH_PATH = DATA_DIR / "entity_graph.json"


def _load_graph() -> nx.Graph:
    """Load persisted entity graph or create fresh."""
    data = load_json(GRAPH_PATH, lambda: None)
    if not data:
        return nx.Graph()
    # networkx < 3.4 wrote edges under "links"; 3.4+ writes "edges".
    return nx.node_link_graph(data, edges="links" if "links" in data else "edges")


def _save_graph(G: nx.Graph) -> None:
    save_json(GRAPH_PATH, nx.node_link_data(G, edges="edges"), indent=None)


class EntityGraphEngine:
    """
    Maintains a graph of financial entity relationships.
    Nodes: companies, executives, lenders, regulators.
    Edges: employment, lending, board membership, acquisition, regulatory link.
    """

    def __init__(self):
        self.G = _load_graph()

    def add_company(self, name: str, **attrs: Any) -> None:
        """Add or update a company node."""
        self.G.add_node(name, node_type="company", updated_at=utcnow().isoformat(), **attrs)

    def add_executive(self, name: str, company: str, role: str, person_id: Optional[str] = None) -> list[str]:
        """
        Link an executive (or director, or major holder) to a company. When the
        same person already sits at other companies, record board overlaps with
        each of them. person_id (e.g. an SEC CIK) disambiguates shared names.
        Returns the companies newly linked by overlap.
        """
        exec_node = f"exec:{person_id or name}"
        self.G.add_node(exec_node, node_type="executive", name=name, role=role)
        others = [n for n in self.G.neighbors(exec_node)
                  if n != company and self.G.nodes[n].get("node_type") == "company"] if exec_node in self.G else []
        self.G.add_edge(exec_node, company, edge_type="employed_by", role=role,
                        added_at=utcnow().isoformat())
        new = []
        for other in others:
            if not self.G.has_edge(company, other):
                self.add_board_overlap(name, company, other)
                new.append(other)
        return new

    def add_lender_relationship(self, lender: str, borrower: str, facility_type: str = "credit") -> None:
        """Link a lender to a borrower."""
        self.G.add_node(lender, node_type="lender")
        self.G.add_edge(lender, borrower, edge_type="lends_to", facility=facility_type,
                        added_at=utcnow().isoformat())

    def add_board_overlap(self, executive: str, company_a: str, company_b: str) -> None:
        """Record a shared board member between two companies."""
        self.G.add_edge(company_a, company_b, edge_type="board_overlap", executive=executive,
                        added_at=utcnow().isoformat())

    def add_acquisition(self, acquirer: str, target: str, status: str = "completed") -> None:
        """Link acquirer and target."""
        self.G.add_edge(acquirer, target, edge_type="acquired", status=status,
                        added_at=utcnow().isoformat())

    def add_regulatory_link(self, regulator: str, company: str, action_type: str) -> None:
        """Record a regulatory relationship."""
        self.G.add_node(regulator, node_type="regulator")
        self.G.add_edge(regulator, company, edge_type="regulates", action=action_type,
                        added_at=utcnow().isoformat())

    def save(self) -> None:
        _save_graph(self.G)

    # ── Analysis Methods ──────────────────────────────────────────────────────

    def get_connected_companies(self, company: str, depth: int = 2) -> list[str]:
        """Return companies within `depth` hops of the given company."""
        if company not in self.G:
            return []
        nodes = nx.single_source_shortest_path_length(self.G, company, cutoff=depth)
        return [
            n for n, _ in nodes.items()
            if n != company and self.G.nodes.get(n, {}).get("node_type") == "company"
        ]

    def get_shared_executives(self, company_a: str, company_b: str) -> list[str]:
        """Find executives shared between two companies."""
        neighbors_a = {n for n in self.G.neighbors(company_a)
                       if self.G.nodes.get(n, {}).get("node_type") == "executive"}
        neighbors_b = {n for n in self.G.neighbors(company_b)
                       if self.G.nodes.get(n, {}).get("node_type") == "executive"}
        return [n.replace("exec:", "") for n in neighbors_a & neighbors_b]

    def get_lender_exposure(self, lender: str) -> list[dict]:
        """Return all companies a lender is exposed to."""
        if lender not in self.G:
            return []
        return [
            {
                "company": n,
                "facility": self.G[lender][n].get("facility", "unknown"),
            }
            for n in self.G.neighbors(lender)
            if self.G[lender][n].get("edge_type") == "lends_to"
        ]

    def detect_contagion_risk(self, distressed_company: str) -> dict:
        """
        Given a distressed company, find entities at second-order risk.
        Returns lenders exposed, board-connected companies, and regulatory links.
        """
        if distressed_company not in self.G:
            return {
                "distressed_company": distressed_company,
                "risk_level": "unknown",
                "note": "Company not in entity graph"
            }

        neighbors = list(self.G.neighbors(distressed_company))
        lenders_at_risk = [
            n for n in neighbors
            if self.G[distressed_company][n].get("edge_type") == "lends_to" or
               self.G.nodes.get(n, {}).get("node_type") == "lender"
        ]
        board_connected = [
            n for n in self.G.neighbors(distressed_company)
            if self.G[distressed_company][n].get("edge_type") == "board_overlap"
        ]
        regulatory_watchers = [
            n for n in neighbors
            if self.G.nodes.get(n, {}).get("node_type") == "regulator"
        ]
        connected_companies = self.get_connected_companies(distressed_company, depth=2)

        risk_level = "isolated"
        if lenders_at_risk or board_connected:
            risk_level = "contained"
        if len(connected_companies) > 5 or len(lenders_at_risk) > 2:
            risk_level = "systemic"

        return {
            "distressed_company": distressed_company,
            "risk_level": risk_level,
            "lenders_at_risk": lenders_at_risk,
            "board_connected_companies": board_connected,
            "regulatory_watchers": regulatory_watchers,
            "total_connected_companies": len(connected_companies),
            "second_order_companies": connected_companies[:10],
        }

    def get_acquisition_chain(self, company: str) -> list[str]:
        """Return the acquisition history chain for a company."""
        if company not in self.G:
            return []
        chain = []
        for n in self.G.neighbors(company):
            edge = self.G[company][n]
            if edge.get("edge_type") == "acquired":
                chain.append(n)
        return chain

    def graph_summary(self) -> dict:
        """Return summary statistics of the entity graph."""
        node_types: dict[str, int] = {}
        for _, attrs in self.G.nodes(data=True):
            t = attrs.get("node_type", "unknown")
            node_types[t] = node_types.get(t, 0) + 1

        edge_types: dict[str, int] = {}
        for _, _, attrs in self.G.edges(data=True):
            t = attrs.get("edge_type", "unknown")
            edge_types[t] = edge_types.get(t, 0) + 1

        return {
            "total_nodes": self.G.number_of_nodes(),
            "total_edges": self.G.number_of_edges(),
            "node_types": node_types,
            "edge_types": edge_types,
            "is_connected": nx.is_connected(self.G) if self.G.number_of_nodes() > 0 else False,
        }


# ── Relationship extraction from a brief's own sources ───────────────────────
# Deterministic, conservative: a relationship is recorded only when one party is
# the analysed company and the other is a capitalised name in a fixed phrase.

_NAME = r"((?:[A-Z]|[a-z][A-Z])[\w&'.\-]*(?:\s+(?:[A-Z][\w&'.\-]*|of|and|&|de|du|la)){0,5})"   # eMAG, iHeart too
_STOP = {"The", "A", "An", "Its", "Their", "This", "That", "New", "Shares", "Stock", "Plans", "Deal"}

_ACQUIRER_FIRST = [
    re.compile(_NAME + r"\s+(?:to\s+)?(?:acquires?|acquired|buys|bought|agrees\s+to\s+(?:buy|acquire)|completes\s+(?:the\s+)?acquisition\s+of|takes\s+over)\s+" + _NAME),
]
_TARGET_FIRST = [
    re.compile(r"(?:acquisition|takeover|purchase)\s+of\s+" + _NAME + r"\s+by\s+" + _NAME),
]
_MERGER = re.compile(_NAME + r"\s+(?:to\s+)?merges?\s+with\s+" + _NAME)
_LENDER = [
    re.compile(r"(?:loan|facility|financing|credit\s+line|term\s+loan)\s+from\s+" + _NAME),
    re.compile(_NAME + r"\s+(?:lends|extends|provides|grants|arranges)\s+(?:a\s+)?(?:[$€£₦]?[\d.,]+\s*(?:m|bn|million|billion)?\s+)?(?:loan|facility|financing|credit)"),
]
_LENDS_TO = re.compile(r"(?:lends|extends|provides|grants|arranges)\s+(?:a\s+)?(?:[$€£₦]?[\d.,]+\s*(?:m|bn|million|billion)?\s+)?(?:loan|facility|financing|credit(?:\s+line)?)\s+to\s+" + _NAME)
_NGX_DEALING = re.compile(r"(?:share|director'?s?|insider)\s+dealings?\s*-\s*([A-Z][A-Za-z.'\-]+(?:\s+[A-Z][A-Za-z.'\-]+){1,3})\s*$", re.IGNORECASE)


def _clean(name: str) -> Optional[str]:
    words = name.strip(" .,-").split()
    while words and words[0] in _STOP:
        words.pop(0)
    while words and words[-1] in ("of", "and", "&", "de", "du", "la"):
        words.pop()
    name = " ".join(words)
    return name if len(name) >= 3 and name not in _STOP else None


def extract_relationships(text: str, company_matchers: list) -> list[tuple[str, str, str]]:
    """
    (kind, other_party, role_of_company) found in one headline or evidence line,
    where one side is the analysed company. kind: 'acquisition' | 'merger' | 'lender'.
    role_of_company: 'acquirer' | 'target' | 'party' | 'borrower'.
    """
    def is_company(name: str) -> bool:
        return any(m.search(name) for m in company_matchers)

    out: list[tuple[str, str, str]] = []
    for rx in _ACQUIRER_FIRST:
        for m in rx.finditer(text):
            a, t = _clean(m.group(1)), _clean(m.group(2))
            if a and t and is_company(a) and not is_company(t):
                out.append(("acquisition", t, "acquirer"))
            elif a and t and is_company(t) and not is_company(a):
                out.append(("acquisition", a, "target"))
    for rx in _TARGET_FIRST:
        for m in rx.finditer(text):
            t, a = _clean(m.group(1)), _clean(m.group(2))
            if a and t and is_company(a) and not is_company(t):
                out.append(("acquisition", t, "acquirer"))
            elif a and t and is_company(t) and not is_company(a):
                out.append(("acquisition", a, "target"))
    for m in _MERGER.finditer(text):
        x, y = _clean(m.group(1)), _clean(m.group(2))
        if x and y and is_company(x) != is_company(y):
            out.append(("merger", y if is_company(x) else x, "party"))
    for m in _LENDS_TO.finditer(text):
        borrower = _clean(m.group(1))
        lender_is_company = any(cm.search(text[: m.start()]) for cm in company_matchers)
        if borrower and lender_is_company and not is_company(borrower):
            out.append(("lender", borrower, "lender"))
    if any(m.search(text) for m in company_matchers):
        for rx in _LENDER:
            for m in rx.finditer(text):
                lender = _clean(m.group(1))
                if lender and not is_company(lender):
                    out.append(("lender", lender, "borrower"))
    return out


def ngx_dealing_insiders(filings: list) -> list[dict]:
    """Directors named in NGX dealing notices ('Notification of Share Dealing - Chima Nwuta')."""
    people = {}
    for f in filings:
        if getattr(f, "form_type", "") != "NGX Disclosure":
            continue
        title = (getattr(f, "description", "") or "").split(":")[-1].strip()
        m = _NGX_DEALING.search(title)
        if m:
            name = " ".join(m.group(1).split()).title()
            people[name.lower()] = {"name": name, "role": "Director / insider (NGX dealing notice)", "cik": ""}
    return list(people.values())


def update_graph_from_brief(brief: Any, insiders: Optional[list[dict]] = None) -> None:
    """
    Auto-update the entity graph from a completed analyst brief: the company
    node, plus its SEC Form 4 insiders (officers, directors, 10% holders). A
    person who appears at two analysed companies links them by board overlap,
    which contagion detection then follows.
    """
    engine = EntityGraphEngine()
    engine.add_company(
        brief.company_name,
        ticker=brief.ticker or "",
        last_severity=brief.overall_severity.value,
        last_alpha=brief.top_alpha_score or 0,
        last_analysed=utcnow().isoformat(),
    )
    people = list(insiders or []) + ngx_dealing_insiders(getattr(brief, "filings_reviewed", []) or [])
    for person in people:
        if person.get("name"):
            engine.add_executive(person["name"], brief.company_name, person.get("role", "Insider"),
                                 person_id=person.get("cik") or None)

    # Acquisition, merger and lender links named in the brief's own sources.
    from src.engines.deterministic_engine import _company_matchers
    matchers = _company_matchers(brief.company_name, ticker=getattr(brief, "ticker", None))
    texts = [n.title for n in getattr(brief, "news_reviewed", []) or []]
    texts += [line for s in getattr(brief, "detected_signals", []) or [] for line in [s.headline, *s.evidence]]
    for text in texts:
        for kind, other, role in extract_relationships(text, matchers):
            if other not in engine.G:
                engine.add_company(other, source="extracted")
            if kind == "acquisition":
                acquirer, target = (brief.company_name, other) if role == "acquirer" else (other, brief.company_name)
                engine.add_acquisition(acquirer, target, status="reported")
            elif kind == "merger":
                engine.G.add_edge(brief.company_name, other, edge_type="merger", added_at=utcnow().isoformat())
            elif kind == "lender" and role == "borrower":
                engine.add_lender_relationship(other, brief.company_name, facility_type="reported")
            elif kind == "lender":
                engine.add_lender_relationship(brief.company_name, other, facility_type="reported")
    engine.save()
