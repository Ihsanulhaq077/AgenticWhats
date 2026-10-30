"""WhatsApp Cloud API integration (official platform only).

- Outbound: POST /{phone_number_id}/messages. When no access token is
  configured the sender runs in MOCK mode: payloads are logged and the
  message is marked sent, so the full pipeline is demoable offline.
- Inbound: signature verification (X-Hub-Signature-256, HMAC-SHA256 of the
  raw body with the app secret) is enforced whenever WHATSAPP_APP_SECRET
  is configured.
"""

import hashlib
import hmac
import json
import logging

import httpx

from app.config.settings import get_settings

settings = get_settings()
logger = logging.getLogger("agenticwhats.whatsapp")


class WhatsAppError(Exception):
    pass


def verify_signature(raw_body: bytes, signature_header: str | None) -> bool:
    if not settings.whatsapp_app_secret:
        return True  # dev mode without app secret configured
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    expected = hmac.new(
        settings.whatsapp_app_secret.encode(), raw_body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature_header.removeprefix("sha256="))


def is_mock_mode() -> bool:
    return not settings.whatsapp_access_token


def send_text(to: str, body: str, phone_number_id: str | None = None) -> dict:
    """Send a WhatsApp text message. Returns {"success", "mode", "provider_message_id"}."""
    pnid = phone_number_id or settings.whatsapp_phone_number_id
    if is_mock_mode():
        logger.info("[WHATSAPP MOCK] to=%s body=%r", to, body)
        return {"success": True, "mode": "mock", "provider_message_id": f"mock-{hmac.new(b'mock', body.encode(), hashlib.sha256).hexdigest()[:12]}"}
    if not pnid:
        raise WhatsAppError("phone_number_id missing")
    resp = httpx.post(
        f"https://graph.facebook.com/{settings.whatsapp_api_version}/{pnid}/messages",
        headers={"Authorization": f"Bearer {settings.whatsapp_access_token}"},
        json={"messaging_product": "whatsapp", "to": to, "type": "text",
              "text": {"preview_url": False, "body": body[:3500]}},
        timeout=30,
    )
    if resp.status_code >= 400:
        logger.error("WhatsApp send failed %s: %s", resp.status_code, resp.text)
        return {"success": False, "mode": "live", "error": resp.text}
    data = resp.json()
    messages = data.get("messages") or []
    return {"success": True, "mode": "live",
            "provider_message_id": messages[0].get("id") if messages else None}


def parse_webhook_payload(payload: dict) -> list[dict]:
    """Extract normalized inbound messages from a Cloud API webhook body.

    Returns list of dicts: phone_number_id, from, profile_name, message_id,
    type, text, media_id, mime_type.
    """
    out = []
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {}) or {}
            pnid = value.get("metadata", {}).get("phone_number_id")
            contacts = {c.get("wa_id"): c.get("profile", {}).get("name", "")
                        for c in value.get("contacts", [])}
            for m in value.get("messages", []):
                msg_type = m.get("type", "unknown")
                text = ""
                if msg_type == "text":
                    text = m.get("text", {}).get("body", "")
                elif msg_type == "audio" or msg_type == "voice":
                    text = ""  # transcription handled by voice pipeline
                out.append({
                    "phone_number_id": pnid,
                    "from": m.get("from", ""),
                    "profile_name": contacts.get(m.get("from", ""), ""),
                    "message_id": m.get("id", ""),
                    "type": msg_type,
                    "text": text,
                    "media_id": (m.get(msg_type) or {}).get("id") if isinstance(m.get(msg_type), dict) else None,
                    "mime_type": (m.get(msg_type) or {}).get("mime_type") if isinstance(m.get(msg_type), dict) else None,
                    "timestamp": m.get("timestamp"),
                })
            # delivery/read statuses are stored but don't trigger the agent
    return out


def download_media(media_id: str) -> bytes | None:
    """Download media from the Cloud API (voice notes, images)."""
    if is_mock_mode():
        return None
    try:
        url_resp = httpx.get(
            f"https://graph.facebook.com/{settings.whatsapp_api_version}/{media_id}",
            headers={"Authorization": f"Bearer {settings.whatsapp_access_token}"},
            timeout=30,
        )
        url_resp.raise_for_status()
        media_url = url_resp.json().get("url")
        if not media_url:
            return None
        data_resp = httpx.get(media_url, headers={"Authorization": f"Bearer {settings.whatsapp_access_token}"}, timeout=60)
        data_resp.raise_for_status()
        return data_resp.content
    except (httpx.HTTPError, ValueError) as exc:
        logger.error("Media download failed: %s", exc)
        return None


def send_raw(payload: dict) -> dict:  # pragma: no cover - debug helper
    logger.info("[WHATSAPP MOCK send_raw] %s", json.dumps(payload)[:500])
    return {"success": True, "mode": "mock"}
