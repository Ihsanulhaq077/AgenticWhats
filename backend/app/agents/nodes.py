"""LangGraph agent nodes.

Two execution paths share the same deterministic tools:

- ``agent_core`` — used when an LLM key is configured. Runs an agentic
  tool-calling loop (LLM decides which tools to call, tools do the real work).
- intent-specific nodes — the offline rule-based path (Baseline 1) so the
  platform fully works with zero API keys.

Both paths converge on the guardrails node.
"""

import json
from datetime import datetime

from sqlalchemy.orm import Session

from app.agents.classify import classify
from app.agents.guardrails import validate_response
from app.agents.llm import llm_service
from app.agents.nlu import (
    is_confirmation, parse_date, parse_order_items, parse_party_size, parse_time,
)
from app.agents.prompts import build_system_prompt
from app.agents.state import AgentState
from app.agents.tools import (
    ToolContext, calculate_order_total, cancel_order, check_booking_availability,
    create_booking, create_order, execute_tool, get_business_hours,
    get_delivery_information, get_order_status, search_knowledge_base, search_menu,
    transfer_to_human, TOOL_SCHEMAS,
)
from app.models.entities import AISetting, Business, Conversation, MenuItem, Message


def _ctx(state: AgentState) -> ToolContext:
    return state["ctx"]  # injected by run_agent(); not part of serialized state


def _save_draft(ctx: ToolContext, key: str, draft: dict | None) -> None:
    meta = ctx.conversation.metadata_dict() if ctx.conversation else {}
    if draft is None:
        meta.pop(key, None)
    else:
        meta[key] = draft
    if ctx.conversation:
        ctx.conversation.set_metadata_dict(meta)
        ctx.db.commit()


def _load_draft(ctx: ToolContext, key: str) -> dict | None:
    if not ctx.conversation:
        return None
    return ctx.conversation.metadata_dict().get(key)


def _fmt_money(amount: float, currency: str) -> str:
    return f"{currency} {amount:,.0f}" if currency == "PKR" else f"{currency} {amount:,.2f}"


def _fmt_menu(items: list[dict], currency: str, limit: int = 6) -> str:
    lines = []
    for it in items[:limit]:
        status = "" if it["available"] else " (unavailable)"
        lines.append(f"• {it['name']} — {_fmt_money(it['price'], currency)}{status}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Node: classify
# ---------------------------------------------------------------------------

def classify_node(state: AgentState) -> dict:
    result = classify(state["user_message"])
    return {"intent": result["intent"], "language": result["language"],
            "confidence": result["confidence"], "tool_calls_log": []}


def route_after_classify(state: AgentState) -> str:
    # Active drafts (awaiting address/confirmation) always resume their
    # workflow regardless of how the new message classifies — "yes",
    # an address, or menu edits must reach the pending workflow.
    ctx = _ctx(state)
    if ctx.conversation is not None:
        meta = ctx.conversation.metadata_dict()
        if meta.get("order_draft", {}).get("awaiting") in {"address", "confirm"}:
            return "order_node"
        if meta.get("booking_draft", {}).get("awaiting") == "confirm":
            return "booking_node"
    if llm_service.available:
        return "agent_core"
    intent = state["intent"]
    if intent == "greeting":
        return "greeting_node"
    if intent in {"create_order", "modify_order"}:
        return "order_node"
    if intent == "order_status":
        return "status_node"
    if intent == "cancel_order":
        return "cancel_node"
    if intent in {"booking", "cancel_booking"}:
        return "booking_node"
    if intent in {"complaint", "human_handoff"}:
        return "handoff_node"
    if intent in {"menu", "menu_price", "item_availability", "offer", "business_hours",
                  "location", "delivery", "payment"}:
        return "knowledge_node"
    return "fallback_node"


# ---------------------------------------------------------------------------
# Node: knowledge / FAQ (rule-based path)
# ---------------------------------------------------------------------------

_KNOWLEDGE_INTENTS = {"menu", "menu_price", "item_availability", "offer"}
_SETTINGS_INTENTS = {"business_hours": get_business_hours, "delivery": get_delivery_information}


def knowledge_node(state: AgentState) -> dict:
    ctx = _ctx(state)
    msg = state["user_message"]
    intent = state["intent"]
    tool_log: list[dict] = []

    if intent in _KNOWLEDGE_INTENTS:
        menu = search_menu(ctx, msg)
        tool_log.append({"name": "search_menu", "arguments": {"query": msg}, "result": menu})
        if menu["items"]:
            text = "Here's what I found:\n" + _fmt_menu(menu["items"], ctx.business.currency)
            if intent == "item_availability":
                avail = [i for i in menu["items"] if i["available"]]
                text = ("Available right now:\n" + _fmt_menu(avail, ctx.business.currency)
                        if avail else "Sorry, that item is currently unavailable.")
            return {"final_response": text, "tool_calls_log": tool_log, "retrieved_context": []}

    rag = search_knowledge_base(ctx, msg)
    tool_log.append({"name": "search_knowledge_base", "arguments": {"query": msg}, "result": rag})
    hits = rag.get("results") or []
    if hits and hits[0]["score"] >= 0.15:
        answer = hits[0]["content"].strip()
        if len(hits) > 1 and len(answer) < 160:
            answer += "\n" + hits[1]["content"].strip()
        return {"final_response": answer[:800], "tool_calls_log": tool_log,
                "retrieved_context": hits}

    if intent in _SETTINGS_INTENTS:
        info = _SETTINGS_INTENTS[intent](ctx)
        tool_log.append({"name": intent, "arguments": {}, "result": info})
        if intent == "business_hours":
            hours = info.get("business_hours") or {}
            days = ", ".join(f"{d}: {t}" for d, t in list(hours.items())[:7]) or "not specified"
            return {"final_response": f"Our hours ({info['timezone']}):\n{days}", "tool_calls_log": tool_log}
        return {"final_response": json.dumps(info), "tool_calls_log": tool_log}

    return fallback_node(state, tool_log=tool_log)


def fallback_node(state: AgentState, tool_log: list[dict] | None = None) -> dict:
    ctx = _ctx(state)
    tool_log = list(tool_log or [])
    rag = search_knowledge_base(ctx, state["user_message"])
    tool_log.append({"name": "search_knowledge_base", "arguments": {"query": state["user_message"]},
                     "result": rag})
    hits = rag.get("results") or []
    if hits and hits[0]["score"] >= 0.2:
        return {"final_response": hits[0]["content"].strip()[:700], "tool_calls_log": tool_log,
                "retrieved_context": hits}
    return {
        "final_response": (
            "I'm sorry, I don't have verified information for that yet. I can help with our menu, "
            "prices, orders, order status and table bookings. Type \"human\" anytime to chat with our team."
        ),
        "tool_calls_log": tool_log,
    }


# ---------------------------------------------------------------------------
# Node: order workflow (rule-based path, multi-turn draft + confirmation)
# ---------------------------------------------------------------------------

def order_node(state: AgentState) -> dict:
    ctx = _ctx(state)
    msg = state["user_message"].strip()
    tool_log: list[dict] = []
    draft = _load_draft(ctx, "order_draft")

    if draft:
        conf = is_confirmation(msg)
        if draft.get("awaiting") == "address":
            if conf == "no":
                _save_draft(ctx, "order_draft", None)
                return {"final_response": "Okay, I've cancelled the order. Anything else?", "tool_calls_log": tool_log}
            draft["address"] = msg
            draft["awaiting"] = "confirm"
            _save_draft(ctx, "order_draft", draft)
            total = calculate_order_total(ctx, draft["items"])
            tool_log.append({"name": "calculate_order_total", "arguments": {"items": draft["items"]}, "result": total})
            return {"final_response": _order_summary(draft, total, ctx) + "\nShall I confirm the order? (yes/no)",
                    "tool_calls_log": tool_log}
        if draft.get("awaiting") == "confirm":
            if conf == "yes":
                result = create_order(ctx, draft["items"], draft.get("address", ""), draft.get("notes", ""))
                tool_log.append({"name": "create_order", "arguments": {"items": draft["items"]}, "result": result})
                if result.get("success"):
                    _save_draft(ctx, "order_draft", None)
                    return {"final_response": (
                        f"✅ Order #{result['order_id']} confirmed! Total {_fmt_money(result['total'], result['currency'])} "
                        f"(incl. delivery {_fmt_money(result['delivery_fee'], result['currency'])}). "
                        "We'll start preparing it right away."), "tool_calls_log": tool_log}
                return {"final_response": "Sorry, I couldn't place the order: " + "; ".join(result.get("details", [result.get("error", "unknown")])),
                        "tool_calls_log": tool_log}
            if conf == "no":
                _save_draft(ctx, "order_draft", None)
                return {"final_response": "No problem, order cancelled. Would you like to change anything?",
                        "tool_calls_log": tool_log}
            # Customer may have edited items mid-confirmation — re-parse.
            parsed = _parse_current_items(ctx, msg)
            if parsed:
                draft["items"] = [
                    {"menu_item_id": item.id, "name": item.name, "quantity": qty} for item, qty in parsed
                ]
                _save_draft(ctx, "order_draft", draft)

    parsed = _parse_current_items(ctx, msg)
    if not parsed:
        menu = search_menu(ctx, msg)
        tool_log.append({"name": "search_menu", "arguments": {"query": msg}, "result": menu})
        if menu["items"]:
            return {"final_response": "I couldn't match those items exactly. Here's our menu:\n"
                                      + _fmt_menu(menu["items"], ctx.business.currency)
                                      + "\nWhich items would you like?",
                    "tool_calls_log": tool_log}
        return {"final_response": "Please tell me the item names from our menu, e.g. \"2 chicken biryani\".",
                "tool_calls_log": tool_log}

    unavailable = [(item, qty) for item, qty in parsed if not item.availability]
    if unavailable and len(unavailable) == len(parsed):
        names = ", ".join(i.name for i, _ in unavailable)
        return {"final_response": f"Sorry, {names} is currently unavailable. Would you like something else? "
                                  "Type \"menu\" to see available items.",
                "tool_calls_log": tool_log}
    parsed = [(i, q) for i, q in parsed if i.availability]

    draft = {
        "type": "order",
        "items": [{"menu_item_id": item.id, "name": item.name, "quantity": qty} for item, qty in parsed],
        "awaiting": "address", "address": "", "notes": "",
    }
    delivery = get_delivery_information(ctx)
    tool_log.append({"name": "get_delivery_information", "arguments": {}, "result": delivery})
    if not delivery.get("delivery_available", True):
        draft["awaiting"] = "confirm"
        _save_draft(ctx, "order_draft", draft)
        total = calculate_order_total(ctx, draft["items"])
        tool_log.append({"name": "calculate_order_total", "arguments": {"items": draft["items"]}, "result": total})
        return {"final_response": _order_summary(draft, total, ctx) + "\nConfirm? (yes/no)",
                "tool_calls_log": tool_log}
    _save_draft(ctx, "order_draft", draft)
    summary = ", ".join(f"{d['quantity']}× {d['name']}" for d in draft["items"])
    return {"final_response": f"Great choice! You want: {summary}.\nPlease share your delivery address.",
            "tool_calls_log": tool_log}


def _parse_current_items(ctx: ToolContext, msg: str):
    menu_items = ctx.db.query(MenuItem).filter(MenuItem.business_id == ctx.business.id).all()
    return parse_order_items(msg, menu_items)


def _order_summary(draft: dict, total: dict, ctx: ToolContext) -> str:
    lines = [f"{d['quantity']}× {d['name']} — {_fmt_money(l['total'], ctx.business.currency)}"
             for d, l in zip(draft["items"], total.get("breakdown", []))]
    addr = f"\nDeliver to: {draft.get('address')}" if draft.get("address") else ""
    return "Order summary:\n" + "\n".join(lines) + f"\nTotal: {_fmt_money(total['total'], ctx.business.currency)}" + addr


# ---------------------------------------------------------------------------
# Node: order status & cancellation (rule-based path)
# ---------------------------------------------------------------------------

def status_node(state: AgentState) -> dict:
    ctx = _ctx(state)
    result = get_order_status(ctx)
    tool_log = [{"name": "get_order_status", "arguments": {}, "result": result}]
    if result.get("error") == "order_not_found":
        return {"final_response": "I couldn't find any recent order for your number. Would you like to place one?",
                "tool_calls_log": tool_log}
    items = ", ".join(f"{i['qty']}× {i['name']}" for i in result["items"])
    return {"final_response": f"Your order #{result['order_id']} ({items}) is currently *{result['status']}* "
                              f"— total {_fmt_money(result['total'], result['currency'])}.",
            "tool_calls_log": tool_log}


def cancel_node(state: AgentState) -> dict:
    ctx = _ctx(state)
    latest = get_order_status(ctx)
    if latest.get("error"):
        return {"final_response": "I couldn't find a recent order to cancel.", "tool_calls_log": []}
    if latest["status"] in {"pending", "confirmed", "preparing"}:
        result = cancel_order(ctx)
        tool_log = [{"name": "cancel_order", "arguments": {}, "result": result}]
        if result.get("success"):
            return {"final_response": f"✅ Your order #{result['order_id']} has been cancelled. "
                                      "Is there anything else you'd like?",
                    "tool_calls_log": tool_log}
        return {"final_response": "I couldn't cancel the order. Let me connect you to our team.",
                "tool_calls_log": tool_log, "escalate": True}
    result = cancel_order(ctx)
    tool_log = [{"name": "cancel_order", "arguments": {}, "result": result}]
    return {"final_response": f"Order #{latest['order_id']} is already {latest['status']}, so it can no longer "
                              "be cancelled. Type \"human\" if you'd like our team to help.",
            "tool_calls_log": tool_log}


# ---------------------------------------------------------------------------
# Node: booking workflow (rule-based path)
# ---------------------------------------------------------------------------

def booking_node(state: AgentState) -> dict:
    ctx = _ctx(state)
    msg = state["user_message"].strip()
    intent = state["intent"]
    tool_log: list[dict] = []

    if intent == "cancel_booking":
        from app.agents.tools import cancel_booking as cancel_booking_tool
        result = cancel_booking_tool(ctx)
        tool_log.append({"name": "cancel_booking", "arguments": {}, "result": result})
        if result.get("success"):
            return {"final_response": f"✅ Your booking #{result['booking_id']} has been cancelled.",
                    "tool_calls_log": tool_log}
        return {"final_response": "I couldn't find a booking to cancel. Type \"human\" if you need help.",
                "tool_calls_log": tool_log}

    draft = _load_draft(ctx, "booking_draft")
    if draft and draft.get("awaiting") == "confirm":
        conf = is_confirmation(msg)
        if conf == "yes":
            result = create_booking(ctx, draft["date"], draft["time"], draft["party_size"], draft.get("notes", ""))
            tool_log.append({"name": "create_booking", "arguments": {k: draft[k] for k in ("date", "time", "party_size")}, "result": result})
            if result.get("success"):
                _save_draft(ctx, "booking_draft", None)
                return {"final_response": f"✅ Table booked! Booking #{result['booking_id']} for "
                                          f"{result['party_size']} on {result['date']} at {result['time']}. "
                                          "We'll see you then!",
                        "tool_calls_log": tool_log}
            return {"final_response": "Sorry, that slot just filled up. Would you like a different time?",
                    "tool_calls_log": tool_log}
        if conf == "no":
            _save_draft(ctx, "booking_draft", None)
            return {"final_response": "Okay, booking cancelled. Let me know if you'd like another time.",
                    "tool_calls_log": tool_log}

    party = parse_party_size(msg)
    time_str = parse_time(msg)
    missing = []
    if not party:
        missing.append("how many people")
    if not time_str:
        missing.append("what time (e.g. 8pm)")
    if missing:
        return {"final_response": "Happy to book a table! Please tell me " + " and ".join(missing) + ".",
                "tool_calls_log": tool_log}
    date_str = parse_date(msg)
    avail = check_booking_availability(ctx, date_str, time_str, party)
    tool_log.append({"name": "check_booking_availability",
                     "arguments": {"date_str": date_str, "time_str": time_str, "party_size": party},
                     "result": avail})
    if avail.get("error"):
        return {"final_response": "I couldn't understand that date/time. Could you restate, e.g. \"tomorrow 8pm\"?",
                "tool_calls_log": tool_log}
    if not avail.get("available"):
        return {"final_response": f"Sorry, we're full on {date_str} at {time_str} for {party} people. "
                                  "Would you like to try a different time?",
                "tool_calls_log": tool_log}
    _save_draft(ctx, "booking_draft", {"type": "booking", "date": date_str, "time": time_str,
                                       "party_size": party, "notes": "", "awaiting": "confirm"})
    return {"final_response": f"You'd like a table for {party} on {date_str} at {time_str}. Confirm? (yes/no)",
            "tool_calls_log": tool_log}


# ---------------------------------------------------------------------------
# Node: human handoff & greeting (rule-based path)
# ---------------------------------------------------------------------------

def handoff_node(state: AgentState) -> dict:
    ctx = _ctx(state)
    result = transfer_to_human(ctx, reason=f"intent={state['intent']}")
    tool_log = [{"name": "transfer_to_human", "arguments": {"reason": state["intent"]}, "result": result}]
    return {"final_response": "I'm connecting you to a member of our team right away — they'll be with you shortly. 🙏",
            "tool_calls_log": tool_log, "escalate": True}


def greeting_node(state: AgentState) -> dict:
    ctx = _ctx(state)
    ai = ctx.ai_settings or AISetting(business_id=ctx.business.id)
    greeting = (ai.greeting or "Welcome to {business}!").format(business=ctx.business.name)
    return {"final_response": f"{greeting}\nYou can ask about our menu, place an order, or book a table."}


# ---------------------------------------------------------------------------
# Node: agentic core (LLM path) — tool-calling loop
# ---------------------------------------------------------------------------

def agent_core(state: AgentState) -> dict:
    ctx = _ctx(state)
    db: Session = ctx.db
    history_rows = (
        db.query(Message)
        .filter(Message.conversation_id == ctx.conversation.id)
        .order_by(Message.id.desc())
        .limit(10)
        .all()
    ) if ctx.conversation else []
    history = [
        {"role": "assistant" if m.direction == "outbound" else "user", "content": m.content}
        for m in reversed(history_rows) if m.message_type == "text"
    ]

    rag = search_knowledge_base(ctx, state["user_message"])
    retrieved = rag.get("results") or []
    context_block = "\n---\n".join(
        f"[{r['metadata'].get('source', 'kb')}] {r['content']}" for r in retrieved
    )
    system = build_system_prompt(ctx.business, ctx.ai_settings, context_block, state.get("language", "en"))
    if state.get("intent") == "order_status":
        system += "\nThe customer is asking about order status — call get_order_status."
    messages = [{"role": "system", "content": system}, *history,
                {"role": "user", "content": state["user_message"]}]

    tool_log: list[dict] = []
    final_text = ""
    for _ in range(4):
        result = llm_service.chat(messages, tools=TOOL_SCHEMAS)
        if result["tool_calls"]:
            messages.append(result["raw"])
            for tc in result["tool_calls"]:
                tool_result = execute_tool(ctx, tc["name"], tc["arguments"])
                tool_log.append({"name": tc["name"], "arguments": tc["arguments"], "result": tool_result})
                messages.append({"role": "tool", "tool_call_id": tc["id"], "name": tc["name"],
                                 "content": json.dumps(tool_result, default=str)[:4000]})
            if result["content"]:
                final_text = result["content"]
                break
            continue
        final_text = result["content"]
        break

    escalate = any(t["name"] == "transfer_to_human" and t["result"].get("success") for t in tool_log)
    return {"final_response": final_text, "tool_calls_log": tool_log,
            "retrieved_context": retrieved, "escalate": escalate}


# ---------------------------------------------------------------------------
# Node: guardrails (final validation before sending)
# ---------------------------------------------------------------------------

def guardrails_node(state: AgentState) -> dict:
    safe = validate_response(state.get("final_response", ""), state.get("tool_calls_log"))
    return {"final_response": safe}


def _now_iso() -> str:
    return datetime.utcnow().isoformat()
