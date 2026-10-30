"""Intent classification & language detection.

The rule-based classifier is deterministic and doubles as (a) the router for
the offline mock agent and (b) Baseline 1 in the FYP evaluation. When an LLM
key is configured the agent node re-classifies with the LLM and only falls
back to this when the LLM fails.
"""

import re

INTENTS = [
    "greeting", "business_hours", "location", "menu", "menu_price", "item_availability",
    "offer", "delivery", "payment", "create_order", "modify_order", "cancel_order",
    "order_status", "booking", "cancel_booking", "complaint", "human_handoff", "unknown",
]

# Ordered by priority: first match wins. Human/complaint override everything.
_RULES: list[tuple[str, re.Pattern]] = [
    ("human_handoff", re.compile(r"\b(manager|human|agent|staff|representative|insan|band[a-e]|cc|customer care)\b", re.I)),
    ("complaint", re.compile(r"\b(complaint|complain|shikayat|shikayet|bekar|worst|bad experience|kharab|gussa|refund)\b", re.I)),
    ("cancel_booking", re.compile(r"\b(cancel|khatam)\b.*\b(booking|reservation|table)\b|\b(booking|reservation|table)\b.*\b(cancel|khatam)\b", re.I)),
    ("cancel_order", re.compile(r"\b(cancel|khatam|ronsak)\b.*\b(order)\b|\b(order)\b.*\b(cancel|khatam)\b", re.I)),
    ("order_status", re.compile(r"\b(order status|status of my order|where is my order|kahan? hai|kaha hai|kab tak|kab a[yi]e?ga|delivery kab|track)\b", re.I)),
    ("create_order", re.compile(r"\b(order|orderr|bhej|bhejdo|bhej do|le aa|le aao|chahiye|chahta|chahti|karna hai|krna hai|send|deliver|buy|purchase)\b", re.I)),
    ("modify_order", re.compile(r"\b(change|add|extra|badal|replace)\b.*\b(order|item|biryani|pizza|burger)\b", re.I)),
    ("booking", re.compile(r"\b(book|booking|reserve|reservation|table|tajweez)\b", re.I)),
    ("business_hours", re.compile(r"\b(open|close|closing|opening|timing|timings|hours|kab khul|kholte|band hote|khula hai|open hai)\b", re.I)),
    ("location", re.compile(r"\b(where|location|address|kahan|kahaan|pata|located)\b", re.I)),
    ("item_availability", re.compile(r"\b(available|availability|hai kya|mujood|milta hai|milti hai|stock)\b", re.I)),
    ("menu_price", re.compile(r"\b(price|cost|rate|kitn[ea]|kitne ki|qeemat|how much)\b", re.I)),
    ("offer", re.compile(r"\b(offer|offers|deal|discount|promotion|sasta|special)\b", re.I)),
    ("delivery", re.compile(r"\b(deliver|delivery|home delivery|ghar par|pohncha|poncha|charges|fee)\b", re.I)),
    ("payment", re.compile(r"\b(pay|payment|cash|card|jazzcash|easypaisa|online payment|bank)\b", re.I)),
    ("menu", re.compile(r"\b(menu|items|kya milta|kya hy|what do you have|show me|list|khana)\b", re.I)),
    ("greeting", re.compile(r"^(hi|hello|hey|salam|assalam[- ]?o[- ]?alaikum|asalam|aoa|salam alaikum|good (morning|evening|afternoon))\b", re.I)),
]

_URDU_SCRIPT = re.compile(r"[\u0600-\u06FF]")
_ROMAN_URDU = re.compile(
    r"\b(nahi|nahin|kya|kitna|kitne|hai|hain|kar|karna|kardo|kar do|bhej|bhejo|chahiye|mujhe|mein|main|acha|theek|yar|bhai|ka|ki|ke|kab|kahan|kaha|jaldi|abhi|haan|bohat|zara|wala|wali|biryani|karahi)\b",
    re.I,
)
_GREETING_ONLY = re.compile(r"^\s*(hi|hello|hey|salam|assalam[- ]?o[- ]?alaikum|asalam|aoa)[!.\s]*$", re.I)

_NUMBER_WORDS = {
    "one": 1, "ek": 1, "two": 2, "do": 2, "three": 3, "teen": 3, "char": 4, "chaar": 4,
    "four": 4, "five": 5, "panch": 5, "paanch": 5, "six": 6, "chhe": 6, "che": 6, "seven": 7,
    "saat": 7, "eight": 8, "aath": 8, "nine": 9, "nau": 9, "ten": 10, "das": 10,
}


def detect_language(text: str) -> str:
    if _URDU_SCRIPT.search(text):
        return "ur"
    roman_hits = len(_ROMAN_URDU.findall(text))
    words = len(re.findall(r"[A-Za-z]+", text))
    if words and roman_hits / max(words, 1) >= 0.25:
        return "roman_urdu"
    return "en"


def classify_intent(text: str) -> tuple[str, float]:
    """Return (intent, confidence)."""
    stripped = text.strip()
    if not stripped:
        return "unknown", 0.0
    if _GREETING_ONLY.match(stripped):
        return "greeting", 0.95
    for intent, pattern in _RULES:
        if pattern.search(stripped):
            # Rule matches are strong signals; ambiguity lowers confidence a bit.
            return intent, 0.8
    return "unknown", 0.3


def classify(text: str) -> dict:
    intent, confidence = classify_intent(text)
    return {
        "intent": intent,
        "language": detect_language(text),
        "confidence": confidence,
    }
