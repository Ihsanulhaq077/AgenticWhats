import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.agents.llm import llm_service
from app.config.settings import get_settings
from app.db.session import engine
from app.models.entities import Base  # noqa: F401 - registers all tables
from app.services.whatsapp_service import is_mock_mode

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")

settings = get_settings()

app = FastAPI(
    title="AgenticWhats API",
    description="Multi-tenant agentic AI WhatsApp business automation platform",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup() -> None:
    # Dev convenience: create tables if missing. Production uses Alembic
    # migrations (backend/alembic) — see README.
    Base.metadata.create_all(bind=engine)


@app.get("/health", tags=["meta"])
def health():
    return {
        "status": "ok",
        "app": settings.app_name,
        "environment": settings.app_env,
        "llm_mode": llm_service.mode,
        "whatsapp_mode": "mock" if is_mock_mode() else "live",
    }


from app.api.v1 import (  # noqa: E402
    admin, analytics, auth, billing, bookings, businesses, conversations, customers, knowledge,
    menu, orders, whatsapp,
)

prefix = settings.api_v1_prefix
app.include_router(auth.router, prefix=prefix)
app.include_router(businesses.router, prefix=prefix)
app.include_router(menu.router, prefix=prefix)
app.include_router(orders.router, prefix=prefix)
app.include_router(bookings.router, prefix=prefix)
app.include_router(customers.router, prefix=prefix)
app.include_router(conversations.router, prefix=prefix)
app.include_router(knowledge.router, prefix=prefix)
app.include_router(analytics.router, prefix=prefix)
app.include_router(whatsapp.router, prefix=prefix)
app.include_router(billing.router, prefix=prefix)
app.include_router(admin.router, prefix=prefix)
