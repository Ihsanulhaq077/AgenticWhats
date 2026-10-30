"""Webhook simulator: sends a customer message to the backend exactly like
WhatsApp Cloud API would (same JSON shape). Lets you demo the full pipeline
(webhook → tenant → customer → agent → tools → reply) offline, in mock mode.

Usage:
  ./.venv/Scripts/python.exe backend/scripts/simulate_whatsapp.py "2 chicken biryani" [+92300...]
  ./.venv/Scripts/python.exe backend/scripts/simulate_whatsapp.py --conversation  # multi-turn demo
"""

import json
import sys
import uuid
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

BASE = "http://127.0.0.1:8000"
PHONE_NUMBER_ID = "DEMO-PHONE-ID"
FROM_NUMBER = "+923009998877"


def send_message(text: str, from_number: str = FROM_NUMBER) -> None:
    payload = {
        "object": "whatsapp_business_account",
        "entry": [{
            "id": "ENTRY1",
            "changes": [{
                "value": {
                    "messaging_product": "whatsapp",
                    "metadata": {"display_phone_number": "92915550000", "phone_number_id": PHONE_NUMBER_ID},
                    "contacts": [{"profile": {"name": "Demo Customer"}, "wa_id": from_number}],
                    "messages": [{
                        "from": from_number,
                        "id": f"wamid.sim-{uuid.uuid4().hex[:16]}",
                        "timestamp": "1690000000",
                        "text": {"body": text},
                        "type": "text",
                    }],
                },
                "field": "messages",
            }],
        }],
    }
    r = httpx.post(f"{BASE}/api/webhooks/whatsapp", json=payload, timeout=60)
    print(f"You    : {text}")
    if r.status_code != 200:
        print(f"[webhook HTTP {r.status_code}: {r.text}]")
        return
    import time
    time.sleep(1.5)  # background task processes asynchronously
    conv = _latest_conversation(from_number)
    if conv is None:
        print("[no conversation found - is the server running?]")
        return
    for msg in reversed(conv["messages"]):
        if msg["direction"] == "outbound" and msg["message_type"] != "system":
            print(f"Agent  : {msg['content']}")
            break


def _latest_conversation(from_number: str):
    r = httpx.get(f"{BASE}/api/conversations", headers=_auth_headers(), timeout=30)
    if r.status_code != 200:
        return None
    for conv in r.json():
        if conv["customer_number"] == from_number:
            detail = httpx.get(f"{BASE}/api/conversations/{conv['id']}", headers=_auth_headers(), timeout=30)
            return detail.json()
    return None


def _auth_headers():
    import os
    email = os.environ.get("DEMO_EMAIL", "owner@demo.com")
    password = os.environ.get("DEMO_PASSWORD", "demo1234")
    login = httpx.post(f"{BASE}/api/auth/login", json={"email": email, "password": password}, timeout=30)
    if login.status_code != 200:
        print(f"[login failed: {login.text} - run seed_demo.py first]")
        sys.exit(1)
    token = login.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


MULTI_TURN = [
    "salam",
    "What is the price of chicken biryani?",
    "yar 2 chicken biryani bhej do",
    "University Road, Peshawar",
    "yes",
]

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--conversation":
        for turn in MULTI_TURN:
            send_message(turn)
            print()
    elif len(sys.argv) > 1:
        msg = " ".join(sys.argv[1:])
        send_message(msg)
    else:
        print(__doc__)
