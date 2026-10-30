from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import require_platform_admin
from app.db.session import get_db
from app.models.entities import (Booking, Business, Conversation, Message, Order, Subscription,
                                 UsageRecord, User)
from app.services.notification_service import write_audit

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/businesses")
def list_businesses(admin: User = Depends(require_platform_admin), db: Session = Depends(get_db)):
    rows = (
        db.query(Business, Subscription)
        .outerjoin(Subscription, Subscription.business_id == Business.id)
        .order_by(Business.id).all()
    )
    out = []
    for business, sub in rows:
        messages = db.query(func.count(Message.id)).filter(Message.business_id == business.id).scalar() or 0
        orders = db.query(func.count(Order.id)).filter(Order.business_id == business.id).scalar() or 0
        out.append({
            "id": business.id, "name": business.name, "slug": business.slug,
            "type": business.business_type, "status": business.status,
            "plan": sub.plan if sub else "none", "plan_status": sub.status if sub else "none",
            "messages": messages, "orders": orders,
            "created_at": business.created_at,
        })
    return out


@router.patch("/businesses/{business_id}/status")
def set_status(
    business_id: int,
    action: str,
    admin: User = Depends(require_platform_admin),
    db: Session = Depends(get_db),
):
    if action not in {"suspend", "activate"}:
        raise HTTPException(400, "action must be suspend or activate")
    business = db.get(Business, business_id)
    if business is None:
        raise HTTPException(404, "Business not found")
    business.status = "suspended" if action == "suspend" else "active"
    db.commit()
    write_audit(db, business_id=business.id, actor_id=admin.id, action=f"admin.{action}",
                entity_type="business", entity_id=business.id)
    return {"id": business.id, "status": business.status}


@router.get("/overview")
def overview(admin: User = Depends(require_platform_admin), db: Session = Depends(get_db)):
    usage = {r.metric: 0 for r in db.query(UsageRecord).distinct(UsageRecord.metric).all()}
    for r in db.query(UsageRecord).all():
        usage[r.metric] = usage.get(r.metric, 0) + r.quantity
    return {
        "total_businesses": db.query(func.count(Business.id)).scalar() or 0,
        "active_businesses": db.query(func.count(Business.id))
            .filter(Business.status == "active").scalar() or 0,
        "suspended_businesses": db.query(func.count(Business.id))
            .filter(Business.status == "suspended").scalar() or 0,
        "total_users": db.query(func.count(User.id)).scalar() or 0,
        "total_messages": db.query(func.count(Message.id)).scalar() or 0,
        "total_orders": db.query(func.count(Order.id)).scalar() or 0,
        "total_bookings": db.query(func.count(Booking.id)).scalar() or 0,
        "total_conversations": db.query(func.count(Conversation.id)).scalar() or 0,
        "usage": usage,
    }
