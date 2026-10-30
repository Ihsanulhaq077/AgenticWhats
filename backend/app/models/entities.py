from datetime import datetime

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


# ---------------------------------------------------------------------------
# Identity & tenancy
# ---------------------------------------------------------------------------

class User(Base, TimestampMixin):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    name = Column(String(120), nullable=False)
    email = Column(String(255), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    # platform_admin | owner | staff  (RBAC)
    role = Column(String(30), default="owner", nullable=False)
    is_active = Column(Integer, default=1, nullable=False)


class Business(Base, TimestampMixin):
    __tablename__ = "businesses"

    id = Column(Integer, primary_key=True)
    name = Column(String(160), nullable=False)
    slug = Column(String(180), unique=True, index=True, nullable=False)
    business_type = Column(String(50), default="restaurant", nullable=False)
    description = Column(Text, default="")
    address = Column(String(300), default="")
    phone = Column(String(40), default="")
    timezone = Column(String(60), default="Asia/Karachi")
    currency = Column(String(8), default="PKR")
    status = Column(String(20), default="active", nullable=False)  # active | suspended
    # JSON blob for business_hours, delivery areas, payment options, booking capacity
    settings = Column(Text, default="{}")

    def settings_dict(self) -> dict:
        import json
        try:
            return json.loads(self.settings or "{}")
        except (ValueError, TypeError):
            return {}


class BusinessUser(Base):
    __tablename__ = "business_users"
    __table_args__ = (UniqueConstraint("business_id", "user_id", name="uq_business_user"),)

    id = Column(Integer, primary_key=True)
    business_id = Column(Integer, ForeignKey("businesses.id", ondelete="CASCADE"), index=True, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    role = Column(String(30), default="owner", nullable=False)  # owner | staff


class WhatsAppAccount(Base, TimestampMixin):
    __tablename__ = "whatsapp_accounts"

    id = Column(Integer, primary_key=True)
    business_id = Column(Integer, ForeignKey("businesses.id", ondelete="CASCADE"), index=True, nullable=False)
    phone_number_id = Column(String(80), unique=True, index=True)
    business_account_id = Column(String(80))
    # Reference to secret store; never store raw tokens here.
    access_token_reference = Column(String(160))
    display_phone = Column(String(40))
    status = Column(String(20), default="pending", nullable=False)  # pending | connected | error


class AISetting(Base, TimestampMixin):
    __tablename__ = "ai_settings"

    id = Column(Integer, primary_key=True)
    business_id = Column(Integer, ForeignKey("businesses.id", ondelete="CASCADE"), index=True, unique=True)
    agent_name = Column(String(80), default="Sara")
    greeting = Column(Text, default="Assalam-o-Alaikum! Welcome to {business}. How can I help you today?")
    tone = Column(String(30), default="friendly")
    supported_languages = Column(String(120), default="en,ur,roman_urdu")
    instructions = Column(Text, default="")
    handoff_keywords = Column(Text, default="manager,human,complaint,staff")


# ---------------------------------------------------------------------------
# CRM: customers, conversations, messages
# ---------------------------------------------------------------------------

class Customer(Base, TimestampMixin):
    __tablename__ = "customers"
    __table_args__ = (UniqueConstraint("business_id", "whatsapp_number", name="uq_business_customer"),)

    id = Column(Integer, primary_key=True)
    business_id = Column(Integer, ForeignKey("businesses.id", ondelete="CASCADE"), index=True, nullable=False)
    whatsapp_number = Column(String(30), index=True, nullable=False)
    name = Column(String(120), default="")
    language = Column(String(20), default="en")
    metadata_json = Column("metadata", Text, default="{}")


class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(Integer, primary_key=True)
    business_id = Column(Integer, ForeignKey("businesses.id", ondelete="CASCADE"), index=True, nullable=False)
    customer_id = Column(Integer, ForeignKey("customers.id", ondelete="CASCADE"), index=True, nullable=False)
    status = Column(String(20), default="ai", nullable=False)  # ai | needs_human | human | closed
    assigned_staff_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"))
    metadata_json = Column("metadata", Text, default="{}")
    started_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    last_message_at = Column(DateTime, default=datetime.utcnow, index=True)

    def metadata_dict(self) -> dict:
        import json
        try:
            return json.loads(self.metadata_json or "{}")
        except (ValueError, TypeError):
            return {}

    def set_metadata_dict(self, value: dict) -> None:
        import json
        self.metadata_json = json.dumps(value)


class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True)
    business_id = Column(Integer, ForeignKey("businesses.id", ondelete="CASCADE"), index=True, nullable=False)
    conversation_id = Column(Integer, ForeignKey("conversations.id", ondelete="CASCADE"), index=True, nullable=False)
    direction = Column(String(10), nullable=False)  # inbound | outbound
    message_type = Column(String(20), default="text")  # text | audio | image | system
    content = Column(Text, default="")
    provider_message_id = Column(String(120), index=True)
    intent = Column(String(40))
    ai_generated = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, index=True, nullable=False)


# ---------------------------------------------------------------------------
# Catalog & operations
# ---------------------------------------------------------------------------

class Category(Base):
    __tablename__ = "categories"

    id = Column(Integer, primary_key=True)
    business_id = Column(Integer, ForeignKey("businesses.id", ondelete="CASCADE"), index=True, nullable=False)
    name = Column(String(80), nullable=False)


class MenuItem(Base, TimestampMixin):
    __tablename__ = "menu_items"

    id = Column(Integer, primary_key=True)
    business_id = Column(Integer, ForeignKey("businesses.id", ondelete="CASCADE"), index=True, nullable=False)
    category_id = Column(Integer, ForeignKey("categories.id", ondelete="SET NULL"))
    name = Column(String(160), nullable=False)
    description = Column(Text, default="")
    price = Column(Float, nullable=False, default=0.0)
    currency = Column(String(8), default="PKR")
    availability = Column(Integer, default=1, nullable=False)  # 1 available, 0 unavailable
    metadata_json = Column("metadata", Text, default="{}")  # e.g. {"spicy": true, "tags": ["special"]}


class Order(Base, TimestampMixin):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True)
    business_id = Column(Integer, ForeignKey("businesses.id", ondelete="CASCADE"), index=True, nullable=False)
    customer_id = Column(Integer, ForeignKey("customers.id", ondelete="SET NULL"), index=True)
    conversation_id = Column(Integer, ForeignKey("conversations.id", ondelete="SET NULL"))
    status = Column(String(30), default="pending", nullable=False)
    # pending -> confirmed -> preparing -> ready -> out_for_delivery -> delivered | cancelled
    subtotal = Column(Float, default=0.0, nullable=False)
    delivery_fee = Column(Float, default=0.0, nullable=False)
    discount = Column(Float, default=0.0, nullable=False)
    total = Column(Float, default=0.0, nullable=False)
    delivery_address = Column(String(400), default="")
    notes = Column(Text, default="")


class OrderItem(Base):
    __tablename__ = "order_items"

    id = Column(Integer, primary_key=True)
    order_id = Column(Integer, ForeignKey("orders.id", ondelete="CASCADE"), index=True, nullable=False)
    menu_item_id = Column(Integer, ForeignKey("menu_items.id", ondelete="SET NULL"))
    name_snapshot = Column(String(160), default="")
    quantity = Column(Integer, nullable=False, default=1)
    unit_price = Column(Float, nullable=False, default=0.0)
    total = Column(Float, nullable=False, default=0.0)


class Booking(Base, TimestampMixin):
    __tablename__ = "bookings"

    id = Column(Integer, primary_key=True)
    business_id = Column(Integer, ForeignKey("businesses.id", ondelete="CASCADE"), index=True, nullable=False)
    customer_id = Column(Integer, ForeignKey("customers.id", ondelete="SET NULL"), index=True)
    conversation_id = Column(Integer, ForeignKey("conversations.id", ondelete="SET NULL"))
    booking_type = Column(String(30), default="table")
    date = Column(String(12), nullable=False)   # YYYY-MM-DD
    time = Column(String(8), nullable=False)    # HH:MM
    party_size = Column(Integer, default=2, nullable=False)
    status = Column(String(20), default="confirmed", nullable=False)  # confirmed | cancelled
    notes = Column(Text, default="")


# ---------------------------------------------------------------------------
# Knowledge base (RAG)
# ---------------------------------------------------------------------------

class KnowledgeDocument(Base, TimestampMixin):
    __tablename__ = "knowledge_documents"

    id = Column(Integer, primary_key=True)
    business_id = Column(Integer, ForeignKey("businesses.id", ondelete="CASCADE"), index=True, nullable=False)
    title = Column(String(200), nullable=False)
    source_type = Column(String(30), default="text")  # text | faq | file | url
    source_reference = Column(String(400), default="")
    version = Column(Integer, default=1, nullable=False)
    content = Column(Text, default="")


class KnowledgeChunk(Base):
    __tablename__ = "knowledge_chunks"

    id = Column(Integer, primary_key=True)
    business_id = Column(Integer, ForeignKey("businesses.id", ondelete="CASCADE"), index=True, nullable=False)
    document_id = Column(Integer, ForeignKey("knowledge_documents.id", ondelete="CASCADE"), index=True, nullable=False)
    chunk_index = Column(Integer, default=0, nullable=False)
    content = Column(Text, nullable=False)
    # JSON-encoded float vector. In production with PostgreSQL+pgvector this
    # column is migrated to `vector(384)`; the accessor below keeps the API identical.
    embedding = Column(Text, default="[]")
    metadata_json = Column("metadata", Text, default="{}")

    def embedding_list(self) -> list[float]:
        import json
        try:
            return json.loads(self.embedding or "[]")
        except (ValueError, TypeError):
            return []


# ---------------------------------------------------------------------------
# SaaS: subscriptions, usage, audit
# ---------------------------------------------------------------------------

PLAN_LIMITS = {
    "starter": {"ai_messages_per_month": 500, "tools": False, "voice": False, "vision": False},
    "business": {"ai_messages_per_month": 5000, "tools": True, "voice": False, "vision": False},
    "pro": {"ai_messages_per_month": 50000, "tools": True, "voice": True, "vision": True},
}


class Subscription(Base, TimestampMixin):
    __tablename__ = "subscriptions"

    id = Column(Integer, primary_key=True)
    business_id = Column(Integer, ForeignKey("businesses.id", ondelete="CASCADE"), index=True, unique=True)
    plan = Column(String(20), default="starter", nullable=False)
    status = Column(String(20), default="trialing", nullable=False)  # trialing | active | past_due | cancelled
    start_date = Column(DateTime, default=datetime.utcnow)
    renewal_date = Column(DateTime)


class UsageRecord(Base):
    __tablename__ = "usage_records"

    id = Column(Integer, primary_key=True)
    business_id = Column(Integer, ForeignKey("businesses.id", ondelete="CASCADE"), index=True, nullable=False)
    metric = Column(String(40), nullable=False)  # ai_messages | orders | bookings | human_handoffs ...
    quantity = Column(Integer, default=0, nullable=False)
    period = Column(String(10), nullable=False, index=True)  # YYYY-MM


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True)
    business_id = Column(Integer, index=True)
    actor_id = Column(Integer)
    action = Column(String(80), nullable=False)
    entity_type = Column(String(60))
    entity_id = Column(String(60))
    timestamp = Column(DateTime, default=datetime.utcnow, index=True, nullable=False)
