"""Deterministic business tools executed server-side.

Every tool is tenant-scoped: database queries always filter by
``business_id`` so one tenant can never touch another tenant's rows.
Prices, totals and availability are computed from the database — never
taken from LLM output. The same functions back both the rule-based agent
(mock mode) and LLM tool-calling mode (TOOL_SCHEMAS).
"""

from datetime import datetime

from sqlalchemy.orm import Session

from app.models.entities import (
    AISetting, Booking, Business, Conversation, Customer, MenuItem, Message, Order, OrderItem,
)

ALLOWED_ORDER_STATUSES = [
    "pending", "confirmed", "preparing", "ready", "out_for_delivery", "delivered", "cancelled",
]
CANCELLABLE_STATUSES = {"pending", "confirmed", "preparing"}
DEFAULT_DELIVERY_FEE = 0.0


class ToolContext:
    """Binds a database session to one tenant + customer + conversation."""

    def __init__(self, db: Session, business: Business, customer: Customer | None = None,
                 conversation: Conversation | None = None, ai_settings: AISetting | None = None):
        self.db = db
        self.business = business
        self.customer = customer
        self.conversation = conversation
        self.ai_settings = ai_settings


# ---------------------------------------------------------------------------
# Menu tools
# ---------------------------------------------------------------------------

def search_menu(ctx: ToolContext, query: str) -> dict:
    """Search the tenant's menu by free-text query (name/description/tags)."""
    from app.agents.nlu import _tokens

    items = ctx.db.query(MenuItem).filter(MenuItem.business_id == ctx.business.id).all()
    if not query or not query.strip():
        return {"items": [_item_out(i) for i in items if i.availability][:15]}
    wanted = _tokens(query)
    scored = []
    for item in items:
        searchable = _tokens(f"{item.name} {item.description}")
        score = len(wanted & searchable) / max(len(wanted | searchable), 1)
        if score > 0:
            scored.append((score, item))
    scored.sort(key=lambda pair: pair[0], reverse=True)
    top = [item for _, item in scored[:10]]
    if not top:
        # Fallback: substring containment on the raw query.
        q = query.lower()
        top = [i for i in items if q in i.name.lower() or q in (i.description or "").lower()][:10]
    return {"items": [_item_out(i) for i in top]}


def _item_out(item: MenuItem) -> dict:
    return {
        "id": item.id,
        "name": item.name,
        "price": item.price,
        "currency": item.currency,
        "available": bool(item.availability),
        "description": (item.description or "")[:120],
    }


def get_menu_item(ctx: ToolContext, item_id: int) -> dict:
    item = ctx.db.query(MenuItem).filter(
        MenuItem.business_id == ctx.business.id, MenuItem.id == item_id
    ).first()
    if item is None:
        return {"error": "menu_item_not_found"}
    return _item_out(item)


def check_item_availability(ctx: ToolContext, item_id: int) -> dict:
    item = ctx.db.query(MenuItem).filter(
        MenuItem.business_id == ctx.business.id, MenuItem.id == item_id
    ).first()
    if item is None:
        return {"error": "menu_item_not_found"}
    return {"id": item.id, "name": item.name, "available": bool(item.availability)}


# ---------------------------------------------------------------------------
# Order tools
# ---------------------------------------------------------------------------

def calculate_order_total(ctx: ToolContext, items: list[dict]) -> dict:
    """Server-side total calculation. Ignores any client/LLM-supplied prices."""
    subtotal, breakdown, errors = 0.0, [], []
    for line in items:
        item = ctx.db.query(MenuItem).filter(
            MenuItem.business_id == ctx.business.id, MenuItem.id == int(line.get("menu_item_id", 0))
        ).first()
        qty = max(1, min(int(line.get("quantity", 1)), 99))
        if item is None:
            errors.append(f"item {line.get('menu_item_id')} not found for this business")
            continue
        if not item.availability:
            errors.append(f"{item.name} is currently unavailable")
            continue
        line_total = round(item.price * qty, 2)
        subtotal = round(subtotal + line_total, 2)
        breakdown.append({"name": item.name, "qty": qty, "unit_price": item.price, "total": line_total})
    fee = float(ctx.business.settings_dict().get("delivery_fee", DEFAULT_DELIVERY_FEE))
    return {"subtotal": subtotal, "delivery_fee": fee, "total": round(subtotal + fee, 2),
            "breakdown": breakdown, "errors": errors}


def create_order(ctx: ToolContext, items: list[dict], delivery_address: str = "", notes: str = "") -> dict:
    """Create an order. Only succeeds via validated DB rows — returns real IDs."""
    if not ctx.customer:
        return {"error": "no_customer_context"}
    priced = calculate_order_total(ctx, items)
    if priced["errors"] or not priced["breakdown"]:
        return {"error": "invalid_items", "details": priced["errors"]}
    order = Order(
        business_id=ctx.business.id,
        customer_id=ctx.customer.id,
        conversation_id=ctx.conversation.id if ctx.conversation else None,
        status="pending",
        subtotal=priced["subtotal"],
        delivery_fee=priced["delivery_fee"],
        total=priced["total"],
        delivery_address=delivery_address,
        notes=notes,
    )
    ctx.db.add(order)
    ctx.db.flush()
    for line in priced["breakdown"]:
        ctx.db.add(OrderItem(
            order_id=order.id,
            name_snapshot=line["name"],
            quantity=line["qty"],
            unit_price=line["unit_price"],
            total=line["total"],
        ))
    ctx.db.commit()
    return {"success": True, "order_id": order.id, "total": order.total,
            "currency": ctx.business.currency, "breakdown": priced["breakdown"],
            "delivery_fee": order.delivery_fee}


def _order_out(ctx: ToolContext, order: Order) -> dict:
    lines = ctx.db.query(OrderItem).filter(OrderItem.order_id == order.id).all()
    return {
        "order_id": order.id, "status": order.status, "total": order.total,
        "currency": ctx.business.currency,
        "created_at": order.created_at.isoformat() if order.created_at else None,
        "items": [{"name": l.name_snapshot, "qty": l.quantity, "total": l.total} for l in lines],
    }


def get_order_status(ctx: ToolContext, order_id: int | None = None) -> dict:
    """Latest order for the customer (or a specific id), tenant-scoped."""
    query = ctx.db.query(Order).filter(Order.business_id == ctx.business.id)
    if order_id is not None:
        query = query.filter(Order.id == order_id)
    elif ctx.customer:
        query = query.filter(Order.customer_id == ctx.customer.id)
    else:
        return {"error": "no_customer_context"}
    order = query.order_by(Order.id.desc()).first()
    if order is None:
        return {"error": "order_not_found"}
    return _order_out(ctx, order)


def cancel_order(ctx: ToolContext, order_id: int | None = None) -> dict:
    query = ctx.db.query(Order).filter(Order.business_id == ctx.business.id)
    if order_id is not None:
        query = query.filter(Order.id == order_id)
    elif ctx.customer:
        query = query.filter(Order.customer_id == ctx.customer.id)
    else:
        return {"error": "no_customer_context"}
    order = query.order_by(Order.id.desc()).first()
    if order is None:
        return {"error": "order_not_found"}
    policy = ctx.business.settings_dict().get("cancellable_statuses", sorted(CANCELLABLE_STATUSES))
    if order.status not in policy:
        return {"success": False, "reason": f"order_in_{order.status}_cannot_be_cancelled"}
    order.status = "cancelled"
    ctx.db.commit()
    return {"success": True, "order_id": order.id, "status": "cancelled"}


# ---------------------------------------------------------------------------
# Booking tools
# ---------------------------------------------------------------------------

def check_booking_availability(ctx: ToolContext, date_str: str, time_str: str, party_size: int) -> dict:
    settings = ctx.business.settings_dict()
    capacity = int(settings.get("booking_capacity_per_slot", 20))
    slot_minutes = int(settings.get("booking_slot_minutes", 60))
    try:
        requested = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
    except ValueError:
        return {"error": "invalid_date_or_time"}
    window_start = requested.timestamp() - slot_minutes * 60
    window_end = requested.timestamp() + slot_minutes * 60
    overlapping = (
        ctx.db.query(Booking)
        .filter(
            Booking.business_id == ctx.business.id,
            Booking.date == date_str,
            Booking.status == "confirmed",
        )
        .all()
    )
    booked = 0
    for b in overlapping:
        try:
            slot = datetime.strptime(f"{b.date} {b.time}", "%Y-%m-%d %H:%M").timestamp()
        except ValueError:
            continue
        if window_start <= slot < window_end:
            booked += b.party_size
    remaining = capacity - booked
    return {
        "available": remaining >= party_size,
        "requested_party_size": party_size,
        "capacity_per_slot": capacity,
        "remaining_capacity": max(remaining, 0),
        "date": date_str,
        "time": time_str,
    }


def create_booking(ctx: ToolContext, date_str: str, time_str: str, party_size: int, notes: str = "") -> dict:
    if not ctx.customer:
        return {"error": "no_customer_context"}
    availability = check_booking_availability(ctx, date_str, time_str, party_size)
    if "error" in availability:
        return availability
    if not availability["available"]:
        return {"success": False, "reason": "slot_full", "details": availability}
    booking = Booking(
        business_id=ctx.business.id,
        customer_id=ctx.customer.id,
        conversation_id=ctx.conversation.id if ctx.conversation else None,
        date=date_str,
        time=time_str,
        party_size=party_size,
        status="confirmed",
        notes=notes,
    )
    ctx.db.add(booking)
    ctx.db.commit()
    return {"success": True, "booking_id": booking.id, "date": date_str, "time": time_str,
            "party_size": party_size}


def cancel_booking(ctx: ToolContext, booking_id: int | None = None) -> dict:
    query = ctx.db.query(Booking).filter(Booking.business_id == ctx.business.id)
    if booking_id is not None:
        query = query.filter(Booking.id == booking_id)
    elif ctx.customer:
        query = query.filter(Booking.customer_id == ctx.customer.id)
    else:
        return {"error": "no_customer_context"}
    booking = query.order_by(Booking.id.desc()).first()
    if booking is None:
        return {"error": "booking_not_found"}
    booking.status = "cancelled"
    ctx.db.commit()
    return {"success": True, "booking_id": booking.id, "status": "cancelled"}


# ---------------------------------------------------------------------------
# Business info tools
# ---------------------------------------------------------------------------

def get_business_hours(ctx: ToolContext) -> dict:
    hours = ctx.business.settings_dict().get("business_hours", {})
    return {"timezone": ctx.business.timezone, "business_hours": hours}


def get_delivery_information(ctx: ToolContext) -> dict:
    s = ctx.business.settings_dict()
    return {
        "delivery_available": bool(s.get("delivery_available", True)),
        "delivery_fee": s.get("delivery_fee", DEFAULT_DELIVERY_FEE),
        "delivery_areas": s.get("delivery_areas", []),
        "min_order": s.get("min_order", 0),
    }


def get_customer_profile(ctx: ToolContext, customer_id: int | None = None) -> dict:
    cid = customer_id or (ctx.customer.id if ctx.customer else None)
    if cid is None:
        return {"error": "no_customer_context"}
    customer = ctx.db.query(Customer).filter(
        Customer.business_id == ctx.business.id, Customer.id == cid
    ).first()
    if customer is None:
        return {"error": "customer_not_found"}
    order_count = ctx.db.query(Order).filter(
        Order.business_id == ctx.business.id, Order.customer_id == cid
    ).count()
    return {"customer_id": customer.id, "name": customer.name, "whatsapp_number": customer.whatsapp_number,
            "language": customer.language, "total_orders": order_count}


# ---------------------------------------------------------------------------
# Human handoff
# ---------------------------------------------------------------------------

def transfer_to_human(ctx: ToolContext, reason: str = "") -> dict:
    if ctx.conversation is None:
        return {"error": "no_conversation_context"}
    ctx.conversation.status = "needs_human"
    ctx.db.add(Message(
        business_id=ctx.business.id,
        conversation_id=ctx.conversation.id,
        direction="outbound",
        message_type="system",
        content=f"Handoff requested. Reason: {reason or 'customer request'}",
        ai_generated=0,
    ))
    ctx.db.commit()
    return {"success": True, "conversation_id": ctx.conversation.id, "status": "needs_human"}


# ---------------------------------------------------------------------------
# Knowledge tool
# ---------------------------------------------------------------------------

def search_knowledge_base(ctx: ToolContext, query: str, k: int = 4) -> dict:
    from app.rag.retrieval import search_knowledge
    return {"results": search_knowledge(ctx.db, ctx.business.id, query, k=k)}


# ---------------------------------------------------------------------------
# Tool registry + JSON schemas for LLM tool-calling mode
# ---------------------------------------------------------------------------

TOOL_REGISTRY: dict[str, callable] = {
    "search_menu": search_menu,
    "get_menu_item": get_menu_item,
    "check_item_availability": check_item_availability,
    "calculate_order_total": calculate_order_total,
    "create_order": create_order,
    "get_order_status": get_order_status,
    "cancel_order": cancel_order,
    "check_booking_availability": check_booking_availability,
    "create_booking": create_booking,
    "cancel_booking": cancel_booking,
    "get_business_hours": get_business_hours,
    "get_delivery_information": get_delivery_information,
    "get_customer_profile": get_customer_profile,
    "transfer_to_human": transfer_to_human,
    "search_knowledge_base": search_knowledge_base,
}

# High-risk tools requiring an explicit confirmation flag in agent flows.
CONFIRMATION_REQUIRED = {"create_order", "create_booking", "cancel_order", "cancel_booking"}


def _schema(name: str, description: str, props: dict, required: list[str]) -> dict:
    return {"name": name, "description": description, "parameters": {
        "type": "object", "properties": props, "required": required}}


TOOL_SCHEMAS = [
    _schema("search_menu", "Search this business's menu by free-text query.",
            {"query": {"type": "string"}}, ["query"]),
    _schema("get_menu_item", "Get one menu item by id.",
            {"item_id": {"type": "integer"}}, ["item_id"]),
    _schema("check_item_availability", "Check whether a menu item is available.",
            {"item_id": {"type": "integer"}}, ["item_id"]),
    _schema("create_order", "Create an order from menu item ids and quantities. Confirm with the customer first.",
            {"items": {"type": "array", "items": {"type": "object", "properties": {
                "menu_item_id": {"type": "integer"}, "quantity": {"type": "integer"}},
                "required": ["menu_item_id", "quantity"]}},
             "delivery_address": {"type": "string"}, "notes": {"type": "string"}},
            ["items"]),
    _schema("get_order_status", "Get the customer's latest order status (or a specific order id).",
            {"order_id": {"type": "integer"}}, []),
    _schema("cancel_order", "Cancel the customer's latest order (or a specific order id) if policy allows.",
            {"order_id": {"type": "integer"}}, []),
    _schema("check_booking_availability", "Check table availability for date (YYYY-MM-DD), time (HH:MM) and party size.",
            {"date_str": {"type": "string"}, "time_str": {"type": "string"}, "party_size": {"type": "integer"}},
            ["date_str", "time_str", "party_size"]),
    _schema("create_booking", "Create a reservation. Confirm with the customer first.",
            {"date_str": {"type": "string"}, "time_str": {"type": "string"},
             "party_size": {"type": "integer"}, "notes": {"type": "string"}},
            ["date_str", "time_str", "party_size"]),
    _schema("cancel_booking", "Cancel the customer's latest booking (or a specific booking id).",
            {"booking_id": {"type": "integer"}}, []),
    _schema("get_business_hours", "Get opening hours and timezone.", {}, []),
    _schema("get_delivery_information", "Get delivery areas, fee and minimum order.", {}, []),
    _schema("get_customer_profile", "Get the current customer's profile and order history size.",
            {"customer_id": {"type": "integer"}}, []),
    _schema("transfer_to_human", "Escalate the conversation to a human staff member.",
            {"reason": {"type": "string"}}, []),
    _schema("search_knowledge_base", "Search the business knowledge base (policies, FAQs) for verified facts.",
            {"query": {"type": "string"}, "k": {"type": "integer"}}, ["query"]),
]


def execute_tool(ctx: ToolContext, name: str, arguments: dict) -> dict:
    """Dispatch a tool call with validation; never trusts LLM-supplied prices."""
    fn = TOOL_REGISTRY.get(name)
    if fn is None:
        return {"error": "unknown_tool", "name": name}
    try:
        return fn(ctx, **arguments)
    except TypeError as exc:
        return {"error": "invalid_arguments", "detail": str(exc)}
