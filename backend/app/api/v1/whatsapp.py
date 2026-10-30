"""WhatsApp webhook endpoints (spec §16-17).

GET  /webhooks/whatsapp — Meta verification handshake.
POST /webhooks/whatsapp — inbound messages: verify signature, parse,
persist, then hand processing to a background task so the endpoint
returns 200 immediately (webhooks must be fast).
"""

import logging

from fastapi import APIRouter, BackgroundTasks, Depends, Header, Query, Request, responses
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services import whatsapp_service
from app.workers.tasks import process_incoming_message

logger = logging.getLogger("agenticwhats.webhook")
router = APIRouter(tags=["whatsapp"])


@router.get("/webhooks/whatsapp")
def verify(
    hub_mode: str = Query("", alias="hub.mode"),
    hub_verify_token: str = Query("", alias="hub.verify_token"),
    hub_challenge: str = Query("", alias="hub.challenge"),
):
    from app.config.settings import get_settings
    settings = get_settings()
    if hub_mode == "subscribe" and hub_verify_token == settings.whatsapp_verify_token:
        return responses.PlainTextResponse(hub_challenge)
    return responses.PlainTextResponse("verification failed", status_code=403)


@router.post("/webhooks/whatsapp")
async def receive(
    request: Request,
    background_tasks: BackgroundTasks,
    x_hub_signature_256: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    raw = await request.body()
    if not whatsapp_service.verify_signature(raw, x_hub_signature_256):
        logger.warning("Rejected webhook with invalid signature")
        return responses.PlainTextResponse("invalid signature", status_code=403)
    try:
        import json
        payload = json.loads(raw or b"{}")
    except ValueError:
        return responses.PlainTextResponse("ok")  # acknowledge malformed body

    messages = whatsapp_service.parse_webhook_payload(payload)
    for m in messages:
        if m["type"] in {"text", "audio", "voice", "image"}:
            background_tasks.add_task(
                _process_task,
                phone_number_id=m["phone_number_id"],
                from_number=m["from"],
                profile_name=m["profile_name"],
                text=m["text"] or ("[voice message]" if m["type"] in {"audio", "voice"} else "[image]"),
                message_type=m["type"],
                provider_message_id=m["message_id"],
            )
    return responses.PlainTextResponse("ok")


def _process_task(**kwargs):
    from app.db.session import SessionLocal
    db = SessionLocal()
    try:
        result = process_incoming_message(db, **kwargs)
        logger.info("Processed inbound message: %s", result)
    finally:
        db.close()
