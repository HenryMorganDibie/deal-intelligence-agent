"""
English renderings of Arabic-script event headlines.

The signal rules and the corporate-event filter read English; an Arabic headline matched only by its acquisition
word ("الاستحواذ") carried no check that a company was involved (an Iranian military "acquisition" of bomb
technology, a football club takeover). Each Arabic headline gets a headline_en, written by the language model in
one batched call per ingest, and the product judges and shows the event by it. The original stays the record.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Callable, Iterable, Optional

log = logging.getLogger(__name__)

_ARABIC = re.compile(r"[؀-ۿ]")
BATCH = 40

_SYSTEM = ("Translate each numbered news headline into English. Keep company and person names in their usual "
           "Latin spelling. Reply with a JSON array of strings, one translation per headline, in the same order, "
           "and nothing else.")


def is_arabic(text: Optional[str]) -> bool:
    return bool(_ARABIC.search(text or ""))


def needs_translation(event: dict) -> bool:
    return is_arabic(event.get("headline")) and not event.get("headline_en")


def _default_call(system: str, user: str) -> str:
    from src.agents.signal_agent import _call_llm, _get_llm_client
    client, provider = _get_llm_client()
    return _call_llm(client, provider, system, user, max_tokens=2500)


def translate(headlines: list[str], call: Optional[Callable[[str, str], str]] = None) -> list[Optional[str]]:
    """English for each headline, or None for all of them when the model's reply cannot be read."""
    if not headlines:
        return []
    user = "\n".join(f"{i}. {h}" for i, h in enumerate(headlines, 1))
    try:
        text = (call or _default_call)(_SYSTEM, user)
        start, end = text.find("["), text.rfind("]")
        out = json.loads(text[start:end + 1]) if start >= 0 and end > start else None
    except Exception as e:                              # no key, provider down, unreadable reply
        log.info("headline translation unavailable: %r", e)
        return [None] * len(headlines)
    if not isinstance(out, list) or len(out) != len(headlines):
        return [None] * len(headlines)
    return [s.strip() if isinstance(s, str) and s.strip() and not is_arabic(s) else None for s in out]


def add_translations(events: Iterable[dict], call: Optional[Callable[[str, str], str]] = None,
                     limit: int = BATCH) -> list[dict]:
    """The events (up to `limit`) that needed a translation and received one, with headline_en set."""
    pending = [e for e in events if needs_translation(e)][:limit]
    done = []
    for e, en in zip(pending, translate([e["headline"] for e in pending], call)):
        if en:
            done.append({**e, "headline_en": en, "headline_lang": "ar"})
    return done
