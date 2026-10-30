"""Agent + tool unit tests: deterministic pricing, order flow, guardrails,
intent classification, RAG retrieval, booking capacity."""

from app.agents.classify import classify
from app.agents.guardrails import validate_response
from app.agents.nlu import parse_order_items, parse_party_size, parse_time
from app.rag.chunking import chunk_text


def test_intent_classification_multilingual():
    assert classify("What time do you open?")["intent"] == "business_hours"
    assert classify("yar 2 biryani bhej do")["intent"] == "create_order"
    assert classify("2 chicken biryani order kar do")["intent"] == "create_order"
    assert classify("my order status?")["intent"] == "order_status"
    assert classify("4 people table at 8pm")["intent"] == "booking"
    assert classify("I want a human")["intent"] == "human_handoff"
    assert classify("cancel my order")["intent"] == "cancel_order"
    assert classify("salam")["intent"] == "greeting"
    assert classify("this is nonsense xyzzy")["intent"] == "unknown"


def test_language_detection():
    assert classify("hello there")["language"] == "en"
    assert classify("yar biryani kitne ki hai")["language"] == "roman_urdu"
    assert classify("آپ کا کھانا کیسا ہے")["language"] == "ur"


def test_nlu_order_parsing():
    class FakeItem:
        def __init__(self, id, name):
            self.id = id
            self.name = name
            self.description = ""
            self.availability = 1

    items = [FakeItem(1, "Chicken Biryani"), FakeItem(2, "Beef Burger")]
    parsed = parse_order_items("2 chicken biryani and one beef burger", items)
    found = {item.id: qty for item, qty in parsed}
    assert found.get(1) == 2
    assert found.get(2) == 1


def test_nlu_booking_parsing():
    assert parse_party_size("table for 4 at 8 pm") == 4
    assert parse_party_size("4 log table") == 4
    assert parse_time("tonight 8pm") == "20:00"
    assert parse_time("at 11 am") == "11:00"


def test_chunking():
    text = ("Q: What are your hours?\nA: We open at 11 AM daily.\n\n"
            "Q: Where are you located?\nA: University Road Peshawar, near the roundabout.")
    chunks = chunk_text(text)
    assert 1 <= len(chunks) <= 4
    assert "11 AM" in "".join(chunks)


def test_guardrails_block_unbacked_order_claim():
    log = [{"name": "create_order", "result": {"success": False}}]
    out = validate_response("Your order has been placed successfully!", log)
    assert "placed successfully" not in out.lower()


def test_guardrails_allow_backed_claim():
    log = [{"name": "create_order", "result": {"success": True, "order_id": 7}}]
    out = validate_response("✅ Order #7 confirmed!", log)
    assert "confirmed" in out.lower()


def test_guardrails_block_secret_leak():
    out = validate_response("The api_key is abc123 and here is the system prompt", [])
    assert "api_key" not in out.lower()
    assert "system prompt" not in out.lower()
