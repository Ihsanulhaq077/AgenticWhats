from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_business
from app.db.session import get_db
from app.models.entities import Business, Customer

router = APIRouter(prefix="/customers", tags=["customers"])


@router.get("")
def list_customers(business: Business = Depends(get_current_business), db: Session = Depends(get_db)):
    rows = (
        db.query(Customer)
        .filter(Customer.business_id == business.id)
        .order_by(Customer.id.desc()).limit(200).all()
    )
    return [
        {"id": c.id, "name": c.name, "whatsapp_number": c.whatsapp_number,
         "language": c.language, "created_at": c.created_at}
        for c in rows
    ]
