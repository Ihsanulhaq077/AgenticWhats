"""End-to-end integration tests: register → menu → RAG → webhook → order → status → analytics."""


def _seed_menu(client, tenant):
    r = client.post("/api/menu", headers=tenant["headers"], json={
        "name": "Chicken Biryani", "description": "Spicy basmati rice with chicken",
        "price": 450, "metadata": {"spicy": True}})
    assert r.status_code == 201, r.text
    r2 = client.post("/api/menu", headers=tenant["headers"], json={
        "name": "Beef Burger", "description": "Grilled beef patty", "price": 550})
    assert r2.status_code == 201


def _ingest_kb(client, tenant):
    r = client.post("/api/knowledge/documents", headers=tenant["headers"],
                    data={"title": "Hours", "content":
                          "Q: What time do you open?\nA: We open every day at 11 AM and close at 11 PM.",
                          "source_type": "faq"})
    assert r.status_code == 201, r.text


def _webhook_message(client, phone_number_id, text, from_number="+923007778899"):
    import uuid
    payload = {
        "object": "whatsapp_business_account",
        "entry": [{"id": "E1", "changes": [{"value": {
            "messaging_product": "whatsapp",
            "metadata": {"phone_number_id": phone_number_id},
            "contacts": [{"profile": {"name": "E2E Tester"}, "wa_id": from_number}],
            "messages": [{"from": from_number, "id": f"wamid.{uuid.uuid4().hex[:20]}",
                          "timestamp": "1690000000", "text": {"body": text}, "type": "text"}],
        }, "field": "messages"}]}],
    }
    return client.post("/api/webhooks/whatsapp", json=payload)


def test_full_pipeline(client, tenant):
    _seed_menu(client, tenant)
    _ingest_kb(client, tenant)

    # Connect WhatsApp account
    r = client.post("/api/business/whatsapp/connect", headers=tenant["headers"],
                    json={"phone_number_id": f"E2E-{tenant['business_id']}"})
    assert r.status_code == 200, r.text
    pnid = f"E2E-{tenant['business_id']}"

    # 1. FAQ through RAG
    assert _webhook_message(client, pnid, "What time do you open?").status_code == 200
    # 2. Order flow
    assert _webhook_message(client, pnid, "2 chicken biryani bhej do").status_code == 200
    # 3. Address
    assert _webhook_message(client, pnid, "University Road Peshawar").status_code == 200
    # 4. Confirm
    assert _webhook_message(client, pnid, "yes").status_code == 200
    # 5. Status
    assert _webhook_message(client, pnid, "where is my order?").status_code == 200
    # Duplicate webhook protection: replay the exact same message id
    payload_dup = {
        "object": "whatsapp_business_account",
        "entry": [{"id": "E1", "changes": [{"value": {
            "messaging_product": "whatsapp",
            "metadata": {"phone_number_id": pnid},
            "contacts": [{"profile": {"name": "E2E"}, "wa_id": "+923007778899"}],
            "messages": [{"from": "+923007778899", "id": "wamid.fixed-dup-id",
                          "timestamp": "1690000000", "text": {"body": "hello"}, "type": "text"}],
        }, "field": "messages"}]}],
    }
    assert client.post("/api/webhooks/whatsapp", json=payload_dup).status_code == 200
    assert client.post("/api/webhooks/whatsapp", json=payload_dup).status_code == 200

    # Verify through dashboard APIs
    convs = client.get("/api/conversations", headers=tenant["headers"]).json()
    assert len(convs) >= 1
    conv = next(c for c in convs if c["customer_number"] == "+923007778899")
    detail = client.get(f"/api/conversations/{conv['id']}", headers=tenant["headers"]).json()
    contents = [m["content"] for m in detail["messages"]]
    assert any("11 AM" in c for c in contents), contents  # RAG answer present

    orders = client.get("/api/orders", headers=tenant["headers"]).json()
    assert len(orders) >= 1
    order = orders[0]
    assert order["subtotal"] == 900.0  # 2 × 450, server-side computed
    assert order["total"] == 1000.0    # subtotal + 100 default delivery fee
    assert order["status"] in {"pending", "confirmed"}

    # Staff status update
    r = client.patch(f"/api/orders/{order['id']}", headers=tenant["headers"],
                     json={"status": "preparing"})
    assert r.status_code == 200 and r.json()["status"] == "preparing"

    # Analytics reflects the order
    stats = client.get("/api/analytics?days=30", headers=tenant["headers"]).json()
    assert stats["orders"] >= 1
    assert stats["revenue"] >= 900.0

    # Usage metering
    usage = client.get("/api/analytics/usage", headers=tenant["headers"]).json()
    assert any(u["metric"] == "ai_messages" for u in usage)

    # Subscription mock checkout
    r = client.post("/api/subscription/checkout?plan=pro", headers=tenant["headers"])
    assert r.status_code == 200 and r.json()["plan"] == "pro"


def test_rag_search_is_tenant_scoped(client, tenant):
    """Tenant A's documents must not appear in tenant B's retrieval."""
    import uuid
    other = client.post("/api/auth/register", json={
        "name": "RAG B", "email": f"rag-{uuid.uuid4().hex[:6]}@test.com",
        "password": "password123", "business_name": "RAG Biz B"}).json()
    headers_b = {"Authorization": f"Bearer {other['access_token']}"}
    r = client.post("/api/knowledge/search", headers=headers_b, data={"query": "opening hours"})
    assert r.status_code == 200
    assert r.json() == [] or all("11 AM" not in h["content"] for h in r.json())


def test_booking_via_webhook(client, tenant):
    pnid = f"E2E-{tenant['business_id']}"
    assert _webhook_message(client, pnid, "table for 4 at 8pm", "+923005556677").status_code == 200
    assert _webhook_message(client, pnid, "yes", "+923005556677").status_code == 200
    bookings = client.get("/api/bookings", headers=tenant["headers"]).json()
    assert len(bookings) >= 1
    assert bookings[0]["party_size"] == 4
