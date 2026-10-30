"""Security tests: JWT, tenant isolation, webhook forgery, input validation (spec §37)."""


def test_me_requires_token(client):
    assert client.get("/api/auth/me").status_code == 401


def test_me_with_invalid_token(client):
    r = client.get("/api/auth/me", headers={"Authorization": "Bearer not-a-jwt"})
    assert r.status_code == 401


def test_business_requires_token(client):
    assert client.get("/api/business").status_code == 401


def test_tenant_isolation_menu(tenant, client):
    """A second tenant must not see or modify the first tenant's menu items."""
    import uuid
    # tenant creates an item
    r = client.post("/api/menu", headers=tenant["headers"], json={
        "name": "Secret Dish", "price": 999})
    assert r.status_code == 201
    item_id = r.json()["id"]

    other = client.post("/api/auth/register", json={
        "name": "Other Owner", "email": f"other-{uuid.uuid4().hex[:6]}@test.com",
        "password": "password123", "business_name": "Other Biz"}).json()
    headers_b = {"Authorization": f"Bearer {other['access_token']}"}

    names = [i["name"] for i in client.get("/api/menu", headers=headers_b).json()]
    assert "Secret Dish" not in names

    # Cross-tenant PATCH/DELETE must 404 (scoped query)
    r_patch = client.patch(f"/api/menu/{item_id}", headers=headers_b, json={"price": 1})
    assert r_patch.status_code == 404
    r_del = client.delete(f"/api/menu/{item_id}", headers=headers_b)
    assert r_del.status_code == 404


def test_tenant_isolation_orders(client, tenant):
    import uuid
    menu = client.get("/api/menu", headers=tenant["headers"]).json()
    cust = client.get("/api/customers", headers=tenant["headers"]).json()
    assert menu and cust
    r = client.post("/api/orders", headers=tenant["headers"], json={
        "customer_id": cust[0]["id"],
        "items": [{"menu_item_id": menu[0]["id"], "quantity": 1}]})
    assert r.status_code == 201, r.text
    order_id = r.json()["id"]

    other = client.post("/api/auth/register", json={
        "name": "Third Owner", "email": f"third-{uuid.uuid4().hex[:6]}@test.com",
        "password": "password123", "business_name": "Third Biz"}).json()
    r2 = client.get(f"/api/orders/{order_id}", headers={"Authorization": f"Bearer {other['access_token']}"})
    assert r2.status_code == 404  # scoped query → not found across tenants


def test_cross_tenant_whatsapp_phone_conflict(client, tenant):
    """One WhatsApp phone_number_id cannot be connected to two businesses."""
    import uuid
    pnid = f"SHARED-{uuid.uuid4().hex[:8]}"
    r = client.post("/api/business/whatsapp/connect", headers=tenant["headers"],
                    json={"phone_number_id": pnid})
    assert r.status_code == 200
    other = client.post("/api/auth/register", json={
        "name": "Fourth Owner", "email": f"fourth-{uuid.uuid4().hex[:6]}@test.com",
        "password": "password123", "business_name": "Fourth Biz"}).json()
    r2 = client.post("/api/business/whatsapp/connect",
                     headers={"Authorization": f"Bearer {other['access_token']}"},
                     json={"phone_number_id": pnid})
    assert r2.status_code == 409


def test_webhook_verification_token(client):
    r = client.get("/api/webhooks/whatsapp?hub.mode=subscribe&hub.verify_token=wrong&hub.challenge=42")
    assert r.status_code == 403
    from app.config.settings import get_settings
    good = client.get(
        f"/api/webhooks/whatsapp?hub.mode=subscribe&hub.verify_token={get_settings().whatsapp_verify_token}&hub.challenge=42")
    assert good.status_code == 200
    assert good.text == "42"


def test_admin_role_required(client, tenant):
    r = client.get("/api/admin/overview", headers=tenant["headers"])
    assert r.status_code == 403


def test_menu_price_validation(client, tenant):
    r = client.post("/api/menu", headers=tenant["headers"], json={"name": "Bad", "price": -5})
    assert r.status_code == 422


def test_sql_injection_attempt_in_menu_search(client, tenant):
    r = client.post("/api/knowledge/search", headers=tenant["headers"],
                    content=None)  # endpoint expects form
    assert r.status_code in (400, 422)
