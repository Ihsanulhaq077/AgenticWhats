"""Staff notification service (human handoff alerts).

Dev: logs + in-app flag on the conversation. Production: plug email/SMS/
push providers behind the same interface.
"""

import logging

from sqlalchemy.orm import Session

from app.models.entities import AuditLog, Conversation

logger = logging.getLogger("agenticwhats.notifications")


def notify_staff_handoff(db: Session, conversation: Conversation, business_name: str) -> None:
    logger.info("HANDOFF ALERT: business=%s conversation=%s needs human attention",
                business_name, conversation.id)


def write_audit(db: Session, *, business_id: int | None, actor_id: int | None, action: str,
                entity_type: str = "", entity_id: str | int = "") -> None:
    db.add(AuditLog(
        business_id=business_id, actor_id=actor_id, action=action,
        entity_type=entity_type, entity_id=str(entity_id),
    ))
    db.commit()
