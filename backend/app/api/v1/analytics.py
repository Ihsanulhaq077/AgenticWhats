from datetime import datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import get_current_business
from app.db.session import get_db
from app.models.entities import (Booking, Business, Conversation, Customer, Message, Order,
                                 OrderItem, UsageRecord)

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("")
def overview(
    days: int = 30,
    business: Business = Depends(get_current_business),
    db: Session = Depends(get_db),
):
    since = datetime.utcnow() - timedelta(days=min(max(days, 1), 365))

    conversations = db.query(func.count(Conversation.id)).filter(
        Conversation.business_id == business.id,
        Conversation.last_message_at >= since).scalar() or 0
    handoffs = db.query(func.count(Conversation.id)).filter(
        Conversation.business_id == business.id,
        Conversation.last_message_at >= since,
        Conversation.status.in_(["needs_human", "human"])).scalar() or 0
    ai_messages = db.query(func.count(Message.id)).filter(
        Message.business_id == business.id, Message.created_at >= since,
        Message.ai_generated == 1).scalar() or 0
    orders = db.query(func.count(Order.id)).filter(
        Order.business_id == business.id, Order.created_at >= since).scalar() or 0
    revenue = db.query(func.coalesce(func.sum(Order.total), 0.0)).filter(
        Order.business_id == business.id, Order.created_at >= since,
        Order.status != "cancelled").scalar() or 0.0
    bookings = db.query(func.count(Booking.id)).filter(
        Booking.business_id == business.id, Booking.created_at >= since).scalar() or 0
    customers = db.query(func.count(Customer.id)).filter(
        Customer.business_id == business.id, Customer.created_at >= since).scalar() or 0

    popular = (
        db.query(OrderItem.name_snapshot, func.sum(OrderItem.quantity).label("qty"))
        .join(Order, Order.id == OrderItem.order_id)
        .filter(Order.business_id == business.id, Order.created_at >= since)
        .group_by(OrderItem.name_snapshot)
        .order_by(func.sum(OrderItem.quantity).desc()).limit(8).all()
    )

    # Daily series for charts
    order_series = (
        db.query(func.date(Order.created_at), func.count(Order.id), func.coalesce(func.sum(Order.total), 0.0))
        .filter(Order.business_id == business.id, Order.created_at >= since)
        .group_by(func.date(Order.created_at)).all()
    )
    msg_series = (
        db.query(func.date(Message.created_at), func.count(Message.id))
        .filter(Message.business_id == business.id, Message.created_at >= since)
        .group_by(func.date(Message.created_at)).all()
    )

    resolution_rate = round(100.0 * (conversations - handoffs) / conversations, 1) if conversations else 0.0

    return {
        "period_days": days,
        "conversations": conversations,
        "human_handoffs": handoffs,
        "ai_messages": ai_messages,
        "orders": orders,
        "revenue": round(revenue, 2),
        "bookings": bookings,
        "new_customers": customers,
        "resolution_rate": resolution_rate,
        "popular_items": [{"name": name, "qty": int(qty)} for name, qty in popular],
        "orders_by_day": [{"date": str(d), "count": int(c), "revenue": float(r)} for d, c, r in order_series],
        "messages_by_day": [{"date": str(d), "count": int(c)} for d, c in msg_series],
    }


@router.get("/usage")
def usage(business: Business = Depends(get_current_business), db: Session = Depends(get_db)):
    rows = db.query(UsageRecord).filter(UsageRecord.business_id == business.id).all()
    return [{"metric": r.metric, "quantity": r.quantity, "period": r.period} for r in rows]
