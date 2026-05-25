"""
Entity Resolution Engine.
Canonical entity registry with LEI support, CIK mapping,
alias deduplication, and ticker normalization.
Prevents duplicate company entries from aliases, subsidiaries,
and inconsistent naming across sources.
"""
from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path
from typing import Optional

ENTITY_REGISTRY_PATH = Path(__file__).resolve().parents[2] / "data" / "entity_registry.json"

# Common company suffix patterns to normalise
SUFFIX_PATTERNS = [
    r"\s+(corp(?:oration)?|inc(?:orporated)?|ltd|limited|plc|llc|llp|lp|gmbh|ag|sa|nv|bv|holdings?|group|co\.?)\.?$",
    r"\s+(bank|financial|capital|fund|ventures?|partners?|management|asset management)$",
]


def _normalise_name(name: str) -> str:
    """Produce a canonical key from a company name for deduplication."""
    # Unicode normalise
    name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    name = name.lower().strip()
    # Remove suffixes
    for pattern in SUFFIX_PATTERNS:
        name = re.sub(pattern, "", name, flags=re.IGNORECASE).strip()
    # Remove punctuation
    name = re.sub(r"[^\w\s]", "", name)
    # Collapse whitespace
    name = re.sub(r"\s+", " ", name).strip()
    return name


def _load() -> dict:
    ENTITY_REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not ENTITY_REGISTRY_PATH.exists():
        return {"entities": {}, "alias_map": {}, "cik_map": {}, "lei_map": {}, "ticker_map": {}}
    try:
        return json.loads(ENTITY_REGISTRY_PATH.read_text())
    except Exception:
        return {"entities": {}, "alias_map": {}, "cik_map": {}, "lei_map": {}, "ticker_map": {}}


def _save(data: dict) -> None:
    ENTITY_REGISTRY_PATH.write_text(json.dumps(data, indent=2))


class EntityResolver:
    """
    Resolves company names, tickers, CIKs, and LEIs to canonical entity IDs.
    Prevents the graph intelligence and warehouse from accumulating duplicate nodes.
    """

    def __init__(self):
        self._data = _load()

    def register(
        self,
        canonical_name: str,
        aliases: Optional[list[str]] = None,
        ticker: Optional[str] = None,
        cik: Optional[str] = None,
        lei: Optional[str] = None,
        exchange: Optional[str] = None,
        sector: Optional[str] = None,
        country: Optional[str] = None,
    ) -> str:
        """
        Register a company entity. Returns the canonical entity ID.
        Automatically deduplicates via name normalisation.
        """
        entity_id = _normalise_name(canonical_name)

        entity = self._data["entities"].get(entity_id, {
            "entity_id":     entity_id,
            "canonical_name": canonical_name,
            "aliases":       [],
            "ticker":        None,
            "cik":           None,
            "lei":           None,
            "exchange":      None,
            "sector":        None,
            "country":       None,
        })

        # Update fields
        if ticker:
            entity["ticker"] = ticker.upper()
            self._data["ticker_map"][ticker.upper()] = entity_id
        if cik:
            entity["cik"] = cik
            self._data["cik_map"][cik] = entity_id
        if lei:
            entity["lei"] = lei
            self._data["lei_map"][lei] = entity_id
        if exchange:
            entity["exchange"] = exchange
        if sector:
            entity["sector"] = sector
        if country:
            entity["country"] = country

        # Register aliases
        all_aliases = list(set(entity.get("aliases", []) + (aliases or [])))
        entity["aliases"] = all_aliases
        self._data["alias_map"][_normalise_name(canonical_name)] = entity_id
        for alias in all_aliases:
            self._data["alias_map"][_normalise_name(alias)] = entity_id

        self._data["entities"][entity_id] = entity
        _save(self._data)
        return entity_id

    def resolve(self, name_or_ticker_or_cik: str) -> Optional[dict]:
        """
        Resolve any identifier to a canonical entity.
        Returns entity dict or None if not found.
        """
        q = name_or_ticker_or_cik.strip()

        # Check ticker map
        upper = q.upper()
        if upper in self._data.get("ticker_map", {}):
            eid = self._data["ticker_map"][upper]
            return self._data["entities"].get(eid)

        # Check CIK map
        if q in self._data.get("cik_map", {}):
            eid = self._data["cik_map"][q]
            return self._data["entities"].get(eid)

        # Check LEI map
        if q in self._data.get("lei_map", {}):
            eid = self._data["lei_map"][q]
            return self._data["entities"].get(eid)

        # Check alias map (normalised name)
        normalised = _normalise_name(q)
        if normalised in self._data.get("alias_map", {}):
            eid = self._data["alias_map"][normalised]
            return self._data["entities"].get(eid)

        # Fuzzy: check if normalised name is substring of any known entity
        for eid, entity in self._data["entities"].items():
            if normalised in eid or eid in normalised:
                return entity

        return None

    def get_canonical_name(self, name: str) -> str:
        """Return canonical name for a company, or the input if not registered."""
        entity = self.resolve(name)
        return entity["canonical_name"] if entity else name

    def get_canonical_id(self, name: str) -> str:
        """Return canonical entity_id for deduplication keys."""
        entity = self.resolve(name)
        return entity["entity_id"] if entity else _normalise_name(name)

    def list_all(self) -> list[dict]:
        """Return all registered entities."""
        return list(self._data["entities"].values())

    def merge_duplicates(self, primary: str, duplicate: str) -> bool:
        """
        Merge a duplicate entity into the primary.
        All aliases and mappings from duplicate are transferred to primary.
        """
        primary_entity = self.resolve(primary)
        dup_entity     = self.resolve(duplicate)

        if not primary_entity or not dup_entity:
            return False

        primary_id = primary_entity["entity_id"]
        dup_id     = dup_entity["entity_id"]

        if primary_id == dup_id:
            return True  # already same entity

        # Transfer aliases
        merged_aliases = list(set(
            primary_entity.get("aliases", []) +
            dup_entity.get("aliases", []) +
            [dup_entity["canonical_name"]]
        ))
        primary_entity["aliases"] = merged_aliases

        # Update alias map
        for alias in merged_aliases + [dup_entity["canonical_name"]]:
            self._data["alias_map"][_normalise_name(alias)] = primary_id

        # Transfer mappings
        if dup_entity.get("ticker") and not primary_entity.get("ticker"):
            primary_entity["ticker"] = dup_entity["ticker"]
        if dup_entity.get("cik") and not primary_entity.get("cik"):
            primary_entity["cik"] = dup_entity["cik"]
            self._data["cik_map"][dup_entity["cik"]] = primary_id
        if dup_entity.get("lei") and not primary_entity.get("lei"):
            primary_entity["lei"] = dup_entity["lei"]
            self._data["lei_map"][dup_entity["lei"]] = primary_id

        # Remove duplicate entity
        self._data["entities"].pop(dup_id, None)
        self._data["alias_map"][dup_id] = primary_id

        self._data["entities"][primary_id] = primary_entity
        _save(self._data)
        return True

    def stats(self) -> dict:
        return {
            "total_entities":   len(self._data["entities"]),
            "total_aliases":    len(self._data["alias_map"]),
            "with_ticker":      sum(1 for e in self._data["entities"].values() if e.get("ticker")),
            "with_cik":         sum(1 for e in self._data["entities"].values() if e.get("cik")),
            "with_lei":         sum(1 for e in self._data["entities"].values() if e.get("lei")),
        }


# Module-level convenience functions
_resolver: Optional[EntityResolver] = None

def get_resolver() -> EntityResolver:
    global _resolver
    if _resolver is None:
        _resolver = EntityResolver()
    return _resolver

def resolve_entity(name: str) -> Optional[dict]:
    return get_resolver().resolve(name)

def get_canonical_name(name: str) -> str:
    return get_resolver().get_canonical_name(name)
