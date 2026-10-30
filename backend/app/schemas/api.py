from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


# ---------- Auth ----------

class RegisterIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    business_name: str = Field(min_length=2, max_length=160)
    business_type: str = "restaurant"


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: int
    role: str
    business_id: int | None = None
    business_slug: str | None = None


class UserOut(BaseModel):
    id: int
    name: str
    email: EmailStr
    role: str

    class Config:
        from_attributes = True


# ---------- Business ----------

class BusinessOut(BaseModel):
    id: int
    name: str
    slug: str
    business_type: str
    description: str
    address: str
    phone: str
    timezone: str
    currency: str
    status: str
    settings: dict = {}

    class Config:
        from_attributes = True


class BusinessUpdateIn(BaseModel):
    name: str | None = None
    description: str | None = None
    address: str | None = None
    phone: str | None = None
    timezone: str | None = None
    currency: str | None = None
    settings: dict | None = None


class WhatsAppConnectIn(BaseModel):
    phone_number_id: str
    display_phone: str = ""
    business_account_id: str = ""
    access_token: str = ""  # stored as env-secret reference, never returned


class WhatsAppStatusOut(BaseModel):
    status: str
    phone_number_id: str | None
    display_phone: str | None


class AISettingsIn(BaseModel):
    agent_name: str | None = None
    greeting: str | None = None
    tone: str | None = None
    supported_languages: str | None = None
    instructions: str | None = None
    handoff_keywords: str | None = None


# ---------- Menu ----------

class MenuCategoryIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)


class MenuItemIn(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    description: str = ""
    price: float = Field(ge=0)
    category_id: int | None = None
    availability: bool = True
    metadata: dict = {}


class MenuItemUpdateIn(BaseModel):
    name: str | None = None
    description: str | None = None
    price: float | None = Field(default=None, ge=0)
    category_id: int | None = None
    availability: bool | None = None
    metadata: dict | None = None


class MenuItemOut(BaseModel):
    id: int
    name: str
    description: str
    price: float
    currency: str
    category_id: int | None
    availability: bool

    class Config:
        from_attributes = True


# ---------- Orders ----------

class OrderItemIn(BaseModel):
    menu_item_id: int
    quantity: int = Field(ge=1, le=99)


class OrderCreateIn(BaseModel):
    customer_id: int
    items: list[OrderItemIn] = Field(min_length=1)
    delivery_address: str = ""
    notes: str = ""


class OrderOut(BaseModel):
    id: int
    business_id: int
    customer_id: int | None
    status: str
    subtotal: float
    delivery_fee: float
    discount: float
    total: float
    delivery_address: str
    notes: str
    created_at: datetime
    items: list[dict] = []

    class Config:
        from_attributes = True


class OrderStatusIn(BaseModel):
    status: str


# ---------- Bookings ----------

class BookingIn(BaseModel):
    customer_id: int
    date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    time: str = Field(pattern=r"^\d{2}:\d{2}$")
    party_size: int = Field(ge=1, le=50)
    booking_type: str = "table"
    notes: str = ""


class BookingOut(BaseModel):
    id: int
    business_id: int
    customer_id: int | None
    booking_type: str
    date: str
    time: str
    party_size: int
    status: str
    notes: str
    created_at: datetime

    class Config:
        from_attributes = True


# ---------- Conversations ----------

class ConversationOut(BaseModel):
    id: int
    business_id: int
    customer_id: int
    customer_name: str = ""
    customer_number: str = ""
    status: str
    assigned_staff_id: int | None
    last_message_at: datetime
    last_message_preview: str = ""


class MessageOut(BaseModel):
    id: int
    direction: str
    message_type: str
    content: str
    intent: str | None
    ai_generated: bool
    created_at: datetime


class StaffReplyIn(BaseModel):
    content: str = Field(min_length=1, max_length=4000)


# ---------- Knowledge ----------

class KnowledgeDocIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1)
    source_type: str = "text"


class KnowledgeDocOut(BaseModel):
    id: int
    title: str
    source_type: str
    version: int
    chunk_count: int = 0
    created_at: datetime


# ---------- Analytics / billing ----------

class AnalyticsOut(BaseModel):
    conversations: int
    ai_messages: int
    human_handoffs: int
    orders: int
    revenue: float
    bookings: int
    popular_items: list[dict]
    resolution_rate: float
    model_config = {"from_attributes": False}


class SubscriptionOut(BaseModel):
    plan: str
    status: str
    renewal_date: datetime | None
    limits: dict
    usage: dict
