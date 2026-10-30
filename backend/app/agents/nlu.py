"""Lightweight deterministic NLU used by the rule-based agent path:
item/quantity extraction for orders and party-size/time extraction for bookings.
"""

import re
from datetime import date, datetime, timedelta

from app.agents.classify import _NUMBER_WORDS
from app.models.entities import MenuItem

_QTY = re.compile(r"\b(\d{1,2}|one|two|three|four|five|six|seven|eight|nine|ten|ek|do|teen|char|chaar|panch|paanch|chhe|che|saat|aath|nau|das)\b", re.I)

_CONFIRM_YES = re.compile(r"\b(yes|yeah|yep|confirm|confirmed|ok(ay)?|sure|haan|han|ji haan|theek|thik|confirm kar|kar do)\b", re.I)
_CONFIRM_NO = re.compile(r"\b(no|nahi|nahin|cancel|mana|reject)\b", re.I)

_TIME = re.compile(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm|baje|bajay|bajay?|at)?\b", re.I)
_TODAY = re.compile(r"\b(today|aaj|tonight)\b", re.I)
_TOMORROW = re.compile(r"\b(tomorrow|kal)\b", re.I)
_PARTY = re.compile(r"\b(?:for|ke?|liye|log|afraad|aadmi|people|persons?)\s*(\d{1,2})\b|\b(\d{1,2})\s*(?:log|afraad|aadmi|people|persons?)\b", re.I)


def _normalize(name: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", name.lower()).strip()


def _tokens(name: str) -> set[str]:
    return {t for t in _normalize(name).split() if len(t) > 2 and t not in {"and", "with", "the"}}


def parse_order_items(text: str, menu_items: list[MenuItem]) -> list[tuple[MenuItem, int]]:
    """Extract (menu_item, quantity) pairs from free text against the tenant menu.

    Matching is done on normalized token overlap between the message window
    after a quantity token and each menu item name; the best-scoring item wins.
    """
    results: list[tuple[MenuItem, int]] = []
    qty_matches = list(_QTY.finditer(text))
    for i, m in enumerate(qty_matches):
        qty_raw = m.group(1).lower()
        qty = int(qty_raw) if qty_raw.isdigit() else _NUMBER_WORDS.get(qty_raw, 1)
        window_start = m.end()
        window_end = qty_matches[i + 1].start() if i + 1 < len(qty_matches) else len(text)
        window = _tokens(text[window_start:window_end])
        if not window:
            window = _tokens(text[max(0, m.start() - 30):m.start()])
        if not window:
            continue
        best, best_score = None, 0.0
        for item in menu_items:
            item_tokens = _tokens(item.name) | _tokens(item.description or "")
            if not item_tokens:
                continue
            overlap = len(window & item_tokens)
            score = overlap / len(window)
            if score > best_score:
                best, best_score = item, score
        if best is not None and best_score >= 0.34:
            results.append((best, max(1, min(qty, 50))))
    # "order kar do" with no quantity: try to match remaining text once
    if not results:
        window = _tokens(text)
        best, best_score = None, 0.0
        for item in menu_items:
            item_tokens = _tokens(item.name)
            if not item_tokens:
                continue
            overlap = len(window & item_tokens)
            score = overlap / len(item_tokens)
            if score > best_score:
                best, best_score = item, score
        if best is not None and best_score >= 0.5:
            results.append((best, 1))
    # Deduplicate by item id keeping max quantity
    merged: dict[int, tuple[MenuItem, int]] = {}
    for item, qty in results:
        if item.id not in merged or qty > merged[item.id][1]:
            merged[item.id] = (item, qty)
    return list(merged.values())


def is_confirmation(text: str) -> str | None:
    """Return 'yes' | 'no' | None."""
    if _CONFIRM_NO.search(text):
        return "no"
    if _CONFIRM_YES.search(text):
        return "yes"
    return None


def parse_party_size(text: str) -> int | None:
    m = _PARTY.search(text)
    if m:
        val = m.group(1) or m.group(2)
        return int(val)
    m2 = _QTY.search(text)
    if m2 and re.search(r"\b(table|booking|reserve|seat)\b", text, re.I):
        raw = m2.group(1).lower()
        return int(raw) if raw.isdigit() else _NUMBER_WORDS.get(raw)
    return None


def parse_time(text: str) -> str | None:
    matches = list(_TIME.finditer(text))
    if not matches:
        return None
    # Prefer an explicit am/pm/baje match ("8pm"), fall back to the first
    # number ("at 8" / "8 baje").
    candidates = [m for m in matches if (m.group(3) or "").lower() in {"am", "pm", "baje", "bajay"}] or matches
    for m in candidates:
        hour = int(m.group(1))
        minute = int(m.group(2) or 0)
        suffix = (m.group(3) or "").lower()
        if hour > 23:
            continue
        if suffix == "pm" and hour < 12:
            hour += 12
        if suffix == "am" and hour == 12:
            hour = 0
        if not suffix and hour <= 7 and re.search(r"\b(dinner|raat|sham|evening)\b", text, re.I):
            hour += 12
        return f"{hour:02d}:{minute:02d}"
    return None


def parse_date(text: str, today: date | None = None) -> str:
    today = today or date.today()
    if _TOMORROW.search(text):
        return (today + timedelta(days=1)).isoformat()
    explicit = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", text)
    if explicit:
        return explicit.group(1)
    return today.isoformat()
