"""
Cross-Signal Graph Intelligence (#11).
Builds entity relationship graphs to detect systemic and second-order risk.
Tracks shared executives, lender relationships, board overlaps,
acquisition chains, and regulatory network effects across companies.
Uses NetworkX for graph operations. No LLM required.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import networkx as nx

GRAPH_PATH = Path(__file__).resolve().parents[2] / "data" / "entity_graph.json"


def _load_graph() -> nx.Graph:
    """Load persisted entity graph or create fresh."""
    GRAPH_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not GRAPH_PATH.exists():
        return nx.Graph()
    try:
        data = json.loads(GRAPH_PATH.read_text())
        G = nx.node_link_graph(data)
        return G
    except Exception:
        return nx.Graph()


def _save_graph(G: nx.Graph) -> None:
    GRAPH_PATH.parent.mkdir(parents=True, exist_ok=True)
    GRAPH_PATH.write_text(json.dumps(nx.node_link_data(G), default=str))


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
        self.G.add_node(name, node_type="company", updated_at=datetime.utcnow().isoformat(), **attrs)

    def add_executive(self, name: str, company: str, role: str) -> None:
        """Link an executive to a company."""
        exec_node = f"exec:{name}"
        self.G.add_node(exec_node, node_type="executive", name=name, role=role)
        self.G.add_edge(exec_node, company, edge_type="employed_by", role=role,
                        added_at=datetime.utcnow().isoformat())

    def add_lender_relationship(self, lender: str, borrower: str, facility_type: str = "credit") -> None:
        """Link a lender to a borrower."""
        self.G.add_node(lender, node_type="lender")
        self.G.add_edge(lender, borrower, edge_type="lends_to", facility=facility_type,
                        added_at=datetime.utcnow().isoformat())

    def add_board_overlap(self, executive: str, company_a: str, company_b: str) -> None:
        """Record a shared board member between two companies."""
        self.G.add_edge(company_a, company_b, edge_type="board_overlap", executive=executive,
                        added_at=datetime.utcnow().isoformat())

    def add_acquisition(self, acquirer: str, target: str, status: str = "completed") -> None:
        """Link acquirer and target."""
        self.G.add_edge(acquirer, target, edge_type="acquired", status=status,
                        added_at=datetime.utcnow().isoformat())

    def add_regulatory_link(self, regulator: str, company: str, action_type: str) -> None:
        """Record a regulatory relationship."""
        self.G.add_node(regulator, node_type="regulator")
        self.G.add_edge(regulator, company, edge_type="regulates", action=action_type,
                        added_at=datetime.utcnow().isoformat())

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


def update_graph_from_brief(brief: Any) -> None:
    """
    Auto-update the entity graph from a completed analyst brief.
    Adds company node and links from detected signal context.
    """
    engine = EntityGraphEngine()
    engine.add_company(
        brief.company_name,
        ticker=brief.ticker or "",
        last_severity=brief.overall_severity.value,
        last_alpha=brief.top_alpha_score or 0,
        last_analysed=datetime.utcnow().isoformat(),
    )
    engine.save()
