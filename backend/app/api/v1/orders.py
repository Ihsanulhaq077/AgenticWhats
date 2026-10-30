from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.agents.tools import ALLOWED_ORDER_STATUSES, ToolContext, calculate_order_total, create_order
from app.api.deps import get_current_business
from app.db.session import get_db
from app.models.entities import Business, Customer, Order, OrderItem
from app.schemas.api import OrderCreateIn, OrderOut, OrderStatusIn
from app.services.notification_service import write_audit

router = APIRouter(prefix="/orders", tags=["orders"])


def _order_out(db: Session, order: Order) -> OrderOut:
    out = OrderOut.model_validate(order)
    out.items = [
        {"name": l.name_snapshot, "qty": l.quantity, "unit_price": l.unit_price, "total": l.total}
        for l in db.query(OrderItem).filter(OrderItem.order_id == order.id).all()
    ]
    return out


@router.get("", response_model=list[OrderOut])
def list_orders(
    status_filter: str | None = None,
    business: Business = Depends(get_current_business),
    db: Session = Depends(get_db),
):
    query = db.query(Order).filter(Order.business_id == business.id)
    if status_filter:
        query = query.filter(Order.status == status_filter)
    orders = query.order_by(Order.id.desc()).limit(200).all()
    return [_order_out(db, o) for o in orders]


@router.get("/{order_id}", response_model=OrderOut)
def get_order(
    order_id: int,
    business: Business = Depends(get_current_business),
    db: Session = Depends(get_db),
):
    order = db.query(Order).filter(Order.business_id == business.id, Order.id == order_id).first()
    if order is None:
        raise HTTPException(404, "Order not found")
    return _order_out(db, order)


@router.post("", response_model=OrderOut, status_code=201)
def create_order_manual(
    payload: OrderCreateIn,
    business: Business = Depends(get_current_business),
    db: Session = Depends(get_db),
):
    """Dashboard/manual order creation — same deterministic tool the agent uses."""
    customer = db.query(Customer).filter(
        Customer.business_id == business.id, Customer.id == payload.customer_id).first()
    if customer is None:
        raise HTTPException(400, "customer not found for this business")
    ctx = ToolContext(db, business, customer)
    result = create_order(
        ctx,
        items=[i.model_dump() for i in payload.items],
        delivery_address=payload.delivery_address,
        notes=payload.notes,
    )
    if not result.get("success"):
        raise HTTPException(400, result.get("error", "order_failed"), detail=result.get("details"))
    order = db.get(Order, result["order_id"])
    write_audit(db, business_id=business.id, actor_id=None, action="order.create",
                entity_type="order", entity_id=order.id)
    return _order_out(db, order)


@router.patch("/{order_id}", response_model=OrderOut)
def update_status(
    order_id: int,
    payload: OrderStatusIn,
    business: Business = Depends(get_current_business),
    db: Session = Depends(get_db),
):
    if payload.status not in ALLOWED_ORDER_STATUSES:
        raise HTTPException(400, f"status must be one of {ALLOWED_ORDER_STATUSES}")
    order = db.query(Order).filter(Order.business_id == business.id, Order.id == order_id).first()
    if order is None:
        raise HTTPException(404, "Order not found")
    order.status = payload.status
    db.commit()
    write_audit(db, business_id=business.id, actor_id=None, action="order.status_update",
                entity_type="order", entity_id=order.id)
    return _order_out(db, order)
