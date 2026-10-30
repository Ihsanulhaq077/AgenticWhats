from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.agents.tools import ToolContext, cancel_booking, check_booking_availability, create_booking
from app.api.deps import get_current_business
from app.db.session import get_db
from app.models.entities import Booking, Business, Customer
from app.schemas.api import BookingIn, BookingOut

router = APIRouter(prefix="/bookings", tags=["bookings"])


@router.get("", response_model=list[BookingOut])
def list_bookings(business: Business = Depends(get_current_business), db: Session = Depends(get_db)):
    return (
        db.query(Booking).filter(Booking.business_id == business.id)
        .order_by(Booking.date.desc(), Booking.time).limit(200).all()
    )


@router.post("", response_model=BookingOut, status_code=201)
def create(
    payload: BookingIn,
    business: Business = Depends(get_current_business),
    db: Session = Depends(get_db),
):
    customer = db.query(Customer).filter(
        Customer.business_id == business.id, Customer.id == payload.customer_id).first()
    if customer is None:
        raise HTTPException(400, "customer not found for this business")
    ctx = ToolContext(db, business, customer)
    availability = check_booking_availability(ctx, payload.date, payload.time, payload.party_size)
    if availability.get("error"):
        raise HTTPException(400, availability["error"])
    if not availability.get("available"):
        raise HTTPException(409, "Slot full", detail=availability)
    result = create_booking(ctx, payload.date, payload.time, payload.party_size, payload.notes)
    if not result.get("success"):
        raise HTTPException(400, result)
    booking = db.get(Booking, result["booking_id"])
    return booking


@router.patch("/{booking_id}/cancel", response_model=BookingOut)
def cancel(
    booking_id: int,
    business: Business = Depends(get_current_business),
    db: Session = Depends(get_db),
):
    booking = db.query(Booking).filter(
        Booking.business_id == business.id, Booking.id == booking_id).first()
    if booking is None:
        raise HTTPException(404, "Booking not found")
    booking.status = "cancelled"
    db.commit()
    return booking
