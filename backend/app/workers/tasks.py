"""Message processing pipeline (webhook → tenant → customer → agent → reply).

The webhook endpoint validates, persists, and hands off to
``process_incoming_message`` — executed as a FastAPI BackgroundTask in dev
(a Celery worker performs the same function in the production topology).
"""

import logging
from datetime import datetime

from sqlalchemy.orm import Session

from app.agents.classify import detect_language
from app.agents.graph import run_agent
from app.agents.tools import ToolContext
from app.models.entities import (
    AISetting, Business, Conversation, Customer, Message, UsageRecord, WhatsAppAccount,
)
from app.services import whatsapp_service

logger = logging.getLogger("agenticwhats.worker")


def resolve_tenant(db: Session, phone_number_id: str) -> Business | None:
    account = (
        db.query(WhatsAppAccount)
        .filter(WhatsAppAccount.phone_number_id == phone_number_id)
        .first()
    )
    if account is None:
        return None
    business = db.get(Business, account.business_id)
    if business is None or business.status != "active":
        return None
    return business


def get_or_create_customer(db: Session, business_id: int, wa_number: str, name: str = "") -> Customer:
    customer = (
        db.query(Customer)
        .filter(Customer.business_id == business_id, Customer.whatsapp_number == wa_number)
        .first()
    )
    if customer is None:
        customer = Customer(business_id=business_id, whatsapp_number=wa_number, name=name or wa_number)
        db.add(customer)
        db.commit()
    elif name and not customer.name:
        customer.name = name
        db.commit()
    return customer


def get_or_create_conversation(db: Session, business_id: int, customer_id: int) -> Conversation:
    conversation = (
        db.query(Conversation)
        .filter(
            Conversation.business_id == business_id,
            Conversation.customer_id == customer_id,
            Conversation.status != "closed",
        )
        .order_by(Conversation.id.desc())
        .first()
    )
    if conversation is None:
        conversation = Conversation(business_id=business_id, customer_id=customer_id, status="ai")
        db.add(conversation)
        db.commit()
    return conversation


def store_message(db: Session, *, business_id: int, conversation_id: int, direction: str,
                  content: str, message_type: str = "text", provider_message_id: str | None = None,
                  ai_generated: bool = False, intent: str | None = None) -> Message:
    msg = Message(
        business_id=business_id,
        conversation_id=conversation_id,
        direction=direction,
        message_type=message_type,
        content=content,
        provider_message_id=provider_message_id,
        ai_generated=1 if ai_generated else 0,
        intent=intent,
    )
    db.add(msg)
    db.commit()
    return msg


def is_duplicate(db: Session, provider_message_id: str | None) -> bool:
    """Idempotency guard: WhatsApp redelivers webhooks; we must not double-process."""
    if not provider_message_id:
        return False
    exists = (
        db.query(Message.id)
        .filter(Message.provider_message_id == provider_message_id)
        .first()
    )
    return exists is not None


def record_usage(db: Session, business_id: int, metric: str, quantity: int = 1) -> None:
    period = datetime.utcnow().strftime("%Y-%m")
    row = (
        db.query(UsageRecord)
        .filter(UsageRecord.business_id == business_id, UsageRecord.metric == metric,
                UsageRecord.period == period)
        .first()
    )
    if row:
        row.quantity += quantity
    else:
        db.add(UsageRecord(business_id=business_id, metric=metric, quantity=quantity, period=period))
    db.commit()


def plan_limit_reached(db: Session, business: Business, metric: str = "ai_messages") -> bool:
    from app.models.entities import PLAN_LIMITS, Subscription
    sub = db.query(Subscription).filter(Subscription.business_id == business.id).first()
    plan = sub.plan if sub else "starter"
    limit = PLAN_LIMITS.get(plan, PLAN_LIMITS["starter"]).get(f"{metric}_per_month")
    if limit is None:
        return False
    period = datetime.utcnow().strftime("%Y-%m")
    used = (db.query(UsageRecord)
            .filter(UsageRecord.business_id == business.id, UsageRecord.metric == metric,
                    UsageRecord.period == period)
            .first())
    return bool(used and used.quantity >= limit)


def process_incoming_message(
    db: Session,
    *,
    phone_number_id: str,
    from_number: str,
    profile_name: str,
    text: str,
    message_type: str = "text",
    provider_message_id: str | None = None,
) -> dict:
    """Full pipeline for one inbound message. Returns a processing summary."""
    if is_duplicate(db, provider_message_id):
        return {"status": "duplicate_skipped"}

    business = resolve_tenant(db, phone_number_id)
    if business is None:
        logger.warning("No active tenant for phone_number_id=%s", phone_number_id)
        return {"status": "no_tenant"}

    customer = get_or_create_customer(db, business.id, from_number, profile_name)
    conversation = get_or_create_conversation(db, business.id, customer.id)

    store_message(
        db, business_id=business.id, conversation_id=conversation.id, direction="inbound",
        content=text, message_type=message_type, provider_message_id=provider_message_id,
    )
    conversation.last_message_at = datetime.utcnow()
    db.commit()

    if plan_limit_reached(db, business, "ai_messages"):
        reply = ("We've reached this month's message limit on our AI assistant plan. "
                 "Our team has been notified and will reply manually. 🙏")
        whatsapp_service.send_text(from_number, reply, phone_number_id)
        store_message(db, business_id=business.id, conversation_id=conversation.id,
                      direction="outbound", content=reply, ai_generated=False)
        conversation.status = "needs_human"
        db.commit()
        return {"status": "plan_limit_reached"}

    ai_settings = db.query(AISetting).filter(AISetting.business_id == business.id).first()
    ctx = ToolContext(db, business, customer, conversation, ai_settings)

    try:
        result = run_agent(ctx, text)
    except Exception:  # agent must never crash the pipeline silently
        logger.exception("Agent failure for conversation %s", conversation.id)
        result = {"final_response": "Sorry, something went wrong on our side. Our team will contact you shortly.",
                  "intent": "error", "tool_calls_log": [], "escalate": True}

    reply = result.get("final_response", "")
    intent = result.get("intent")

    send_result = whatsapp_service.send_text(from_number, reply, phone_number_id)
    store_message(
        db, business_id=business.id, conversation_id=conversation.id, direction="outbound",
        content=reply, ai_generated=True, intent=intent,
        provider_message_id=send_result.get("provider_message_id"),
    )
    if result.get("escalate") and conversation.status == "ai":
        conversation.status = "needs_human"
    conversation.last_message_at = datetime.utcnow()
    if intent:
        customer.language = detect_language(text)
    db.commit()

    record_usage(db, business.id, "ai_messages")
    if result.get("escalate"):
        record_usage(db, business.id, "human_handoffs")

    return {
        "status": "processed",
        "conversation_id": conversation.id,
        "intent": intent,
        "reply": reply,
        "tool_calls": [t["name"] for t in result.get("tool_calls_log", [])],
        "escalated": bool(result.get("escalate")),
    }
