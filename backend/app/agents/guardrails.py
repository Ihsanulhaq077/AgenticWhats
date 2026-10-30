"""Response validation layer (spec §30 guardrails)."""

import re

from app.config.settings import get_settings

settings = get_settings()

_FORBIDDEN = [
    re.compile(p, re.I)
    for p in [
        r"system prompt", r"your instructions", r"tool schema", r"api[_ ]?key",
        r"jwt[_ ]?secret", r"access[_ ]?token", r"database password",
    ]
]

# Claims of completed transactions that must be backed by a successful tool call.
# Worded narrowly so factual status reports ("order #1 is pending") are not blocked.
_CLAIMS_ORDER = re.compile(
    r"(order (has been|is now|is successfully)? ?(successfully )?placed|placed (your )?order successfully|"
    r"order (has been|is) confirmed|confirmed your order|your order (has been|is) (created|placed))",
    re.I,
)
_CLAIMS_BOOKING = re.compile(
    r"(booking (has been|is) confirmed|table (has been|is) booked|reservation (has been|is) confirmed|"
    r"(booked|reserved) (a|your|the) table)",
    re.I,
)

MAX_RESPONSE_CHARS = 900


def validate_response(text: str, tool_calls_log: list[dict] | None = None) -> str:
    """Return a safe final response.

    - Blocks secret/system-prompt leakage.
    - Blocks unbacked transaction claims: "order confirmed" language is only
      allowed when a create_order tool call actually succeeded (same for
      bookings); otherwise the claim is replaced with a safe fallback.
    """
    tool_calls_log = tool_calls_log or []
    safe_text = (text or "").strip()

    if not safe_text:
        return "Sorry, I could not process that. Type \"human\" to talk to our team."

    if settings.jwt_secret and settings.jwt_secret in safe_text:
        safe_text = "Sorry, I cannot share internal information."
    for pattern in _FORBIDDEN:
        if pattern.search(safe_text):
            safe_text = "I can only help with our menu, orders, bookings and business questions."

    order_ok = any(
        t.get("name") == "create_order" and (t.get("result") or {}).get("success")
        for t in tool_calls_log
    )
    booking_ok = any(
        t.get("name") == "create_booking" and (t.get("result") or {}).get("success")
        for t in tool_calls_log
    )
    if _CLAIMS_ORDER.search(safe_text) and not order_ok:
        safe_text = "I still need to confirm the details with you before the order is placed. Shall I proceed?"
    if _CLAIMS_BOOKING.search(safe_text) and not booking_ok:
        safe_text = "Let me confirm the table details with you before booking. Shall I proceed?"

    if len(safe_text) > MAX_RESPONSE_CHARS:
        safe_text = safe_text[:MAX_RESPONSE_CHARS].rsplit(" ", 1)[0] + "…"
    return safe_text
