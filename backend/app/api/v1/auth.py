import json
import re

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.security import create_access_token, hash_password, verify_password
from app.db.session import get_db
from app.models.entities import AISetting, Business, BusinessUser, Subscription, User
from app.schemas.api import LoginIn, RegisterIn, TokenOut, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or "business"


def _unique_slug(db: Session, base: str) -> str:
    slug, i = base, 1
    while db.query(Business).filter(Business.slug == slug).first():
        i += 1
        slug = f"{base}-{i}"
    return slug


def _token_response(db: Session, user: User) -> TokenOut:
    membership = (
        db.query(BusinessUser).filter(BusinessUser.user_id == user.id)
        .order_by(BusinessUser.id).first()
    )
    business = db.get(Business, membership.business_id) if membership else None
    return TokenOut(
        access_token=create_access_token(user.id, user.role),
        user_id=user.id,
        role=user.role,
        business_id=business.id if business else None,
        business_slug=business.slug if business else None,
    )


@router.post("/register", response_model=TokenOut, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterIn, db: Session = Depends(get_db)):
    if db.query(User).filter(User.email == payload.email.lower()).first():
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered")
    business = Business(
        name=payload.business_name,
        slug=_unique_slug(db, _slugify(payload.business_name)),
        business_type=payload.business_type,
        settings=json.dumps({
            "business_hours": {"mon_sun": "11:00-23:00"},
            "delivery_available": True,
            "delivery_fee": 100,
            "delivery_areas": [],
            "booking_capacity_per_slot": 20,
            "booking_slot_minutes": 60,
        }),
    )
    db.add(business)
    db.flush()
    user = User(
        name=payload.name,
        email=payload.email.lower(),
        password_hash=hash_password(payload.password),
        role="owner",
    )
    db.add(user)
    db.flush()
    db.add(BusinessUser(business_id=business.id, user_id=user.id, role="owner"))
    db.add(AISetting(business_id=business.id))
    db.add(Subscription(business_id=business.id, plan="starter", status="trialing"))
    db.commit()
    return _token_response(db, user)


@router.post("/login", response_model=TokenOut)
def login(payload: LoginIn, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == payload.email.lower()).first()
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")
    return _token_response(db, user)


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user
