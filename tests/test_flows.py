from fastapi.testclient import TestClient

from app.main import app, otp_store
from app.db import Base, engine, SessionLocal
from app.models import Branch, MenuCategory, MenuItem, Role, RolePermission, StaffMember, Tenant, TenantListing, User


Base.metadata.drop_all(bind=engine)
Base.metadata.create_all(bind=engine)


def bootstrap():
    db = SessionLocal()
    owner = User(phone="+251911111111", full_name="Owner")
    customer = User(phone="+251922222222", full_name="Customer")
    db.add_all([owner, customer])
    db.flush()
    tenant = Tenant(legal_name="T", display_name="T", business_type="restaurant", status="active", owner_user_id=owner.id)
    db.add(tenant)
    db.flush()
    role = Role(tenant_id=tenant.id, name="Owner")
    db.add(role)
    db.flush()
    for p in ["*", "orders.read", "orders.write", "menu.write", "branches.read", "branches.write", "wallet.read", "wallet.write", "staff.read", "staff.write", "promotions.read", "promotions.write"]:
        db.add(RolePermission(role_id=role.id, permission=p))
    db.add(StaffMember(tenant_id=tenant.id, user_id=owner.id, role_id=role.id, status="active"))
    branch = Branch(tenant_id=tenant.id, name="B", phone="x", address_text="addis", latitude=8.9, longitude=38.7)
    db.add(branch)
    db.flush()
    cat = MenuCategory(tenant_id=tenant.id, name="Cat")
    db.add(cat)
    db.flush()
    item = MenuItem(tenant_id=tenant.id, category_id=cat.id, name="Burger", base_price=10000, is_active=True)
    db.add(item)
    db.add(TenantListing(tenant_id=tenant.id, branch_id=branch.id, cuisines=["ethiopian"], price_level=2, avg_rating=4.5, review_count=10, order_count_30d=5))
    db.commit()
    return owner, customer, branch, item


def login(client, phone):
    code = client.post("/v1/auth/request-otp", json={"phone": phone}).json()["code"]
    r = client.post("/v1/auth/verify-otp", json={"phone": phone, "code": code})
    return r.json()["access_token"]


def test_order_create_and_payment_confirm_and_partner_lifecycle():
    owner, customer, branch, item = bootstrap()
    client = TestClient(app)
    user_token = login(client, customer.phone)
    owner_token = login(client, owner.phone)

    r = client.post("/v1/orders", headers={"Authorization": f"Bearer {user_token}"}, json={
        "branchId": branch.id,
        "mode": "pickup",
        "items": [{"itemId": item.id, "qty": 2, "modifiers": []}]
    })
    assert r.status_code == 200
    order_id = r.json()["orderId"]
    assert r.json()["total"] == 20000

    pay = client.post(f"/v1/orders/{order_id}/pay", headers={"Authorization": f"Bearer {user_token}"}, json={"useWallet": False, "provider": "mock"})
    assert pay.status_code == 200
    pi_id = pay.json()["payment_intent_id"]

    c1 = client.post("/v1/payments/confirm", headers={"Idempotency-Key": "k1"}, json={
        "payment_intent_id": pi_id,
        "provider_txn_id": "txn-1",
        "status": "succeeded",
        "raw_payload": {"ok": True}
    })
    assert c1.status_code == 200
    c2 = client.post("/v1/payments/confirm", headers={"Idempotency-Key": "k1"}, json={
        "payment_intent_id": pi_id,
        "provider_txn_id": "txn-1",
        "status": "succeeded",
        "raw_payload": {"ok": True}
    })
    assert c2.status_code == 200
    assert c1.json() == c2.json()

    a = client.post(f"/v1/partner/orders/{order_id}/accept", headers={"Authorization": f"Bearer {owner_token}"})
    assert a.status_code == 200
    assert a.json()["status"] == "accepted"
    p = client.post(f"/v1/partner/orders/{order_id}/status", headers={"Authorization": f"Bearer {owner_token}"}, json={"status": "preparing"})
    assert p.status_code == 200
    rdy = client.post(f"/v1/partner/orders/{order_id}/status", headers={"Authorization": f"Bearer {owner_token}"}, json={"status": "ready"})
    assert rdy.status_code == 200
    done = client.post(f"/v1/partner/orders/{order_id}/status", headers={"Authorization": f"Bearer {owner_token}"}, json={"status": "completed"})
    assert done.status_code == 200
    assert done.json()["status"] == "completed"
