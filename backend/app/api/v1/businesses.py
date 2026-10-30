import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_business, get_current_user
from app.db.session import get_db
from app.models.entities import AISetting, Business, User, WhatsAppAccount
from app.schemas.api import AISettingsIn, BusinessOut, BusinessUpdateIn, WhatsAppConnectIn, WhatsAppStatusOut
from app.services.notification_service import write_audit

router = APIRouter(tags=["business"])


def _business_out(business: Business) -> BusinessOut:
    out = BusinessOut.model_validate(business)
    out.settings = business.settings_dict()
    return out


@router.get("/business", response_model=BusinessOut)
def get_business(business: Business = Depends(get_current_business)):
    return _business_out(business)


@router.patch("/business", response_model=BusinessOut)
def update_business(
    payload: BusinessUpdateIn,
    business: Business = Depends(get_current_business),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    data = payload.model_dump(exclude_unset=True)
    settings = data.pop("settings", None)
    for field, value in data.items():
        setattr(business, field, value)
    if settings is not None:
        merged = business.settings_dict()
        merged.update(settings)
        business.settings = json.dumps(merged)
    db.commit()
    write_audit(db, business_id=business.id, actor_id=user.id, action="business.update",
                entity_type="business", entity_id=business.id)
    return _business_out(business)


@router.get("/business/whatsapp", response_model=WhatsAppStatusOut)
def whatsapp_status(business: Business = Depends(get_current_business), db: Session = Depends(get_db)):
    account = db.query(WhatsAppAccount).filter(WhatsAppAccount.business_id == business.id).first()
    if account is None:
        return WhatsAppStatusOut(status="pending", phone_number_id=None, display_phone=None)
    return WhatsAppStatusOut(status=account.status, phone_number_id=account.phone_number_id,
                             display_phone=account.display_phone)


@router.post("/business/whatsapp/connect", response_model=WhatsAppStatusOut)
def whatsapp_connect(
    payload: WhatsAppConnectIn,
    business: Business = Depends(get_current_business),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not payload.phone_number_id.strip():
        raise HTTPException(400, "phone_number_id is required")
    existing = db.query(WhatsAppAccount).filter(WhatsAppAccount.business_id == business.id).first()
    if existing:
        account = existing
    else:
        account = WhatsAppAccount(business_id=business.id)
        db.add(account)
    conflict = (
        db.query(WhatsAppAccount)
        .filter(WhatsAppAccount.phone_number_id == payload.phone_number_id,
                WhatsAppAccount.business_id != business.id)
        .first()
    )
    if conflict:
        raise HTTPException(409, "This WhatsApp phone number is already connected to another business")
    account.phone_number_id = payload.phone_number_id.strip()
    account.display_phone = payload.display_phone
    account.business_account_id = payload.business_account_id
    # Raw tokens are never persisted/returned; production stores a secret reference.
    account.access_token_reference = "env:WHATSAPP_ACCESS_TOKEN" if payload.access_token else None
    account.status = "connected"
    db.commit()
    write_audit(db, business_id=business.id, actor_id=user.id, action="whatsapp.connect",
                entity_type="whatsapp_account", entity_id=account.id)
    return WhatsAppStatusOut(status=account.status, phone_number_id=account.phone_number_id,
                             display_phone=account.display_phone)


@router.get("/business/ai-settings")
def get_ai_settings(business: Business = Depends(get_current_business), db: Session = Depends(get_db)):
    ai = db.query(AISetting).filter(AISetting.business_id == business.id).first()
    if ai is None:
        ai = AISetting(business_id=business.id)
        db.add(ai)
        db.commit()
    return {
        "agent_name": ai.agent_name, "greeting": ai.greeting, "tone": ai.tone,
        "supported_languages": ai.supported_languages, "instructions": ai.instructions,
        "handoff_keywords": ai.handoff_keywords,
    }


@router.patch("/business/ai-settings")
def update_ai_settings(
    payload: AISettingsIn,
    business: Business = Depends(get_current_business),
    db: Session = Depends(get_db),
):
    ai = db.query(AISetting).filter(AISetting.business_id == business.id).first()
    if ai is None:
        ai = AISetting(business_id=business.id)
        db.add(ai)
        db.commit()
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(ai, field, value)
    db.commit()
    return {"status": "updated"}
