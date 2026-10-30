from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.api.deps import get_current_business, get_current_user
from app.db.session import get_db
from app.models.entities import Business, Conversation, Customer, Message, User
from app.schemas.api import StaffReplyIn
from app.services import whatsapp_service
from app.services.notification_service import write_audit

router = APIRouter(prefix="/conversations", tags=["conversations"])


@router.get("")
def list_conversations(
    q: str | None = None,
    status_filter: str | None = None,
    business: Business = Depends(get_current_business),
    db: Session = Depends(get_db),
):
    query = (
        db.query(Conversation, Customer)
        .join(Customer, Customer.id == Conversation.customer_id)
        .filter(Conversation.business_id == business.id)
    )
    if status_filter:
        query = query.filter(Conversation.status == status_filter)
    if q:
        like = f"%{q}%"
        query = query.filter(or_(Customer.name.ilike(like), Customer.whatsapp_number.ilike(like)))
    rows = query.order_by(Conversation.last_message_at.desc()).limit(100).all()
    out = []
    for conversation, customer in rows:
        last = (
            db.query(Message).filter(Message.conversation_id == conversation.id)
            .order_by(Message.id.desc()).first()
        )
        out.append({
            "id": conversation.id,
            "business_id": conversation.business_id,
            "customer_id": customer.id,
            "customer_name": customer.name,
            "customer_number": customer.whatsapp_number,
            "status": conversation.status,
            "assigned_staff_id": conversation.assigned_staff_id,
            "last_message_at": conversation.last_message_at,
            "last_message_preview": (last.content[:80] if last else ""),
        })
    return out


@router.get("/{conversation_id}")
def get_conversation(
    conversation_id: int,
    business: Business = Depends(get_current_business),
    db: Session = Depends(get_db),
):
    conversation = db.query(Conversation).filter(
        Conversation.business_id == business.id, Conversation.id == conversation_id).first()
    if conversation is None:
        raise HTTPException(404, "Conversation not found")
    customer = db.get(Customer, conversation.customer_id)
    messages = (
        db.query(Message).filter(Message.conversation_id == conversation.id)
        .order_by(Message.id).all()
    )
    return {
        "id": conversation.id,
        "status": conversation.status,
        "customer": {
            "id": customer.id, "name": customer.name,
            "whatsapp_number": customer.whatsapp_number, "language": customer.language,
        } if customer else None,
        "messages": [
            {"id": m.id, "direction": m.direction, "message_type": m.message_type,
             "content": m.content, "intent": m.intent, "ai_generated": bool(m.ai_generated),
             "created_at": m.created_at}
            for m in messages
        ],
    }


@router.post("/{conversation_id}/reply")
def staff_reply(
    conversation_id: int,
    payload: StaffReplyIn,
    business: Business = Depends(get_current_business),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    conversation = db.query(Conversation).filter(
        Conversation.business_id == business.id, Conversation.id == conversation_id).first()
    if conversation is None:
        raise HTTPException(404, "Conversation not found")
    customer = db.get(Customer, conversation.customer_id)
    if customer is None:
        raise HTTPException(400, "Conversation has no customer")
    send = whatsapp_service.send_text(customer.whatsapp_number, payload.content)
    db.add(Message(
        business_id=business.id, conversation_id=conversation.id, direction="outbound",
        content=payload.content, ai_generated=0,
        provider_message_id=send.get("provider_message_id"),
    ))
    conversation.status = "human"
    conversation.assigned_staff_id = user.id
    conversation.last_message_at = datetime.utcnow()
    db.commit()
    write_audit(db, business_id=business.id, actor_id=user.id, action="conversation.staff_reply",
                entity_type="conversation", entity_id=conversation.id)
    return {"status": "sent", "mode": send.get("mode")}


@router.post("/{conversation_id}/takeover")
def takeover(
    conversation_id: int,
    business: Business = Depends(get_current_business),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    conversation = db.query(Conversation).filter(
        Conversation.business_id == business.id, Conversation.id == conversation_id).first()
    if conversation is None:
        raise HTTPException(404, "Conversation not found")
    conversation.status = "human"
    conversation.assigned_staff_id = user.id
    db.commit()
    write_audit(db, business_id=business.id, actor_id=user.id, action="conversation.takeover",
                entity_type="conversation", entity_id=conversation.id)
    return {"status": "human", "assigned_staff_id": user.id}


@router.post("/{conversation_id}/close")
def close(
    conversation_id: int,
    business: Business = Depends(get_current_business),
    db: Session = Depends(get_db),
):
    conversation = db.query(Conversation).filter(
        Conversation.business_id == business.id, Conversation.id == conversation_id).first()
    if conversation is None:
        raise HTTPException(404, "Conversation not found")
    conversation.status = "closed"
    db.commit()
    return {"status": "closed"}


@router.get("/stats/summary")
def stats_summary(business: Business = Depends(get_current_business), db: Session = Depends(get_db)):
    groups = (
        db.query(Conversation.status, func.count(Conversation.id))
        .filter(Conversation.business_id == business.id)
        .group_by(Conversation.status).all()
    )
    return {status: count for status, count in groups}
