from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_business
from app.db.session import get_db
from app.models.entities import PLAN_LIMITS, Business, Subscription, UsageRecord
from app.services.notification_service import write_audit

router = APIRouter(prefix="/subscription", tags=["billing"])


@router.get("")
def current(business: Business = Depends(get_current_business), db: Session = Depends(get_db)):
    sub = db.query(Subscription).filter(Subscription.business_id == business.id).first()
    if sub is None:
        sub = Subscription(business_id=business.id)
        db.add(sub)
        db.commit()
    period = datetime.utcnow().strftime("%Y-%m")
    rows = db.query(UsageRecord).filter(
        UsageRecord.business_id == business.id, UsageRecord.period == period).all()
    usage = {r.metric: r.quantity for r in rows}
    return {
        "plan": sub.plan, "status": sub.status,
        "start_date": sub.start_date, "renewal_date": sub.renewal_date,
        "limits": PLAN_LIMITS.get(sub.plan, PLAN_LIMITS["starter"]),
        "usage": usage,
    }


@router.get("/plans")
def plans():
    return [
        {"plan": name, **limits} for name, limits in PLAN_LIMITS.items()
    ]


@router.post("/checkout")
def checkout(
    plan: str,
    business: Business = Depends(get_current_business),
    db: Session = Depends(get_db),
):
    """Mock checkout: switches the plan and sets renewal in 30 days.

    A real payment provider (Stripe/Easypaisa/JazzCash...) plugs in here;
    raw card data is never handled by this API.
    """
    if plan not in PLAN_LIMITS:
        raise HTTPException(400, f"plan must be one of {list(PLAN_LIMITS)}")
    sub = db.query(Subscription).filter(Subscription.business_id == business.id).first()
    if sub is None:
        sub = Subscription(business_id=business.id)
        db.add(sub)
    sub.plan = plan
    sub.status = "active"
    sub.renewal_date = datetime.utcnow() + timedelta(days=30)
    db.commit()
    write_audit(db, business_id=business.id, actor_id=None, action="subscription.change",
                entity_type="subscription", entity_id=sub.id)
    return {"status": "active", "plan": plan, "renewal_date": sub.renewal_date}
