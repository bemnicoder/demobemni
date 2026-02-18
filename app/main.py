import hashlib
import math
import os
import random
import time
from datetime import datetime, timedelta
from typing import Optional

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from jose import jwt
from pydantic import BaseModel, Field
from sqlalchemy import and_, desc, func, or_
from sqlalchemy.orm import Session

from .db import Base, engine, get_db
from .models import (
    Branch, BranchHour, IdempotencyKey, ItemAvailability, ItemModifier, LedgerEntry, MenuCategory, MenuItem,
    ModifierOption, Order, OrderEvent, OrderItem, OrderItemModifier, Payment, PaymentIntent, Payout, Promotion,
    Review, Role, RolePermission, ServiceMode, StaffMember, Tenant, TenantListing, TenantVerification, User, UserAddress,
    UserSession, WalletAccount
)

app = FastAPI(title="Demobemni API", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
Base.metadata.create_all(bind=engine)

JWT_SECRET = os.getenv("JWT_SECRET", "devsecret")
ACCESS_EXP_MIN = int(os.getenv("ACCESS_EXP_MIN", "120"))
REFRESH_EXP_DAYS = int(os.getenv("REFRESH_EXP_DAYS", "30"))
PLATFORM_FEE_BPS = int(os.getenv("PLATFORM_FEE_BPS", "1000"))

otp_store: dict[str, tuple[str, float]] = {}
rate_store: dict[str, list[float]] = {}


def issue_tokens(user_id: str, role: str = "consumer"):
    now = datetime.utcnow()
    access = jwt.encode({"sub": user_id, "role": role, "exp": now + timedelta(minutes=ACCESS_EXP_MIN)}, JWT_SECRET)
    refresh = jwt.encode({"sub": user_id, "type": "refresh", "exp": now + timedelta(days=REFRESH_EXP_DAYS)}, JWT_SECRET)
    return {"access_token": access, "refresh_token": refresh, "token_type": "bearer"}


def get_current_user(authorization: str = Header(default=""), db: Session = Depends(get_db)) -> User:
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing token")
    token = authorization.replace("Bearer ", "")
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Invalid token") from exc
    user = db.get(User, payload.get("sub"))
    if not user:
        raise HTTPException(status_code=401, detail="Invalid user")
    return user


def get_staff(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> StaffMember:
    staff = db.query(StaffMember).filter_by(user_id=user.id, status="active").first()
    if not staff:
        raise HTTPException(status_code=403, detail="Staff access required")
    return staff


def role_permissions(staff: StaffMember, db: Session):
    return {p.permission for p in db.query(RolePermission).filter_by(role_id=staff.role_id).all()}


def require_permission(perm: str):
    def dep(staff: StaffMember = Depends(get_staff), db: Session = Depends(get_db)):
        perms = role_permissions(staff, db)
        if perm not in perms and "*" not in perms:
            raise HTTPException(status_code=403, detail=f"Missing permission: {perm}")
        return staff
    return dep


def ensure_wallet(db: Session, owner_type: str, owner_id: str):
    wa = db.query(WalletAccount).filter_by(owner_type=owner_type, owner_id=owner_id, currency="ETB").first()
    if not wa:
        wa = WalletAccount(owner_type=owner_type, owner_id=owner_id, currency="ETB", balance=0)
        db.add(wa)
        db.flush()
    return wa


def add_ledger(db: Session, account: WalletAccount, type_: str, direction: str, amount: int, ref_type: str, ref_id: str, metadata=None):
    entry = LedgerEntry(account_id=account.id, type=type_, direction=direction, amount=amount,
                        reference_type=ref_type, reference_id=ref_id, metadata=metadata or {})
    db.add(entry)
    if direction == "credit":
        account.balance += amount
    else:
        account.balance -= amount


class OtpRequest(BaseModel):
    phone: str


class OtpVerify(BaseModel):
    phone: str
    code: str


class OrderCreateItem(BaseModel):
    itemId: str
    qty: int = Field(gt=0)
    modifiers: list[dict] = []


class CreateOrderBody(BaseModel):
    branchId: str
    mode: str
    items: list[OrderCreateItem]
    notes: Optional[str] = None
    scheduledFor: Optional[datetime] = None
    promoCode: Optional[str] = None


class PayOrderBody(BaseModel):
    provider: Optional[str] = "mock"
    useWallet: bool = False


class ConfirmPaymentBody(BaseModel):
    payment_intent_id: str
    provider_txn_id: str
    status: str
    raw_payload: dict = {}


@app.post("/v1/auth/request-otp")
def request_otp(body: OtpRequest):
    now = time.time()
    attempts = [t for t in rate_store.get(body.phone, []) if now - t < 60]
    if len(attempts) >= 5:
        raise HTTPException(status_code=429, detail="Too many requests")
    attempts.append(now)
    rate_store[body.phone] = attempts
    code = f"{random.randint(100000, 999999)}"
    otp_store[body.phone] = (code, now + 300)
    return {"message": "OTP generated", "code": code}


@app.post("/v1/auth/verify-otp")
def verify_otp(body: OtpVerify, db: Session = Depends(get_db)):
    rec = otp_store.get(body.phone)
    if not rec or rec[1] < time.time() or rec[0] != body.code:
        raise HTTPException(status_code=400, detail="Invalid OTP")
    user = db.query(User).filter_by(phone=body.phone).first()
    if not user:
        user = User(phone=body.phone, full_name="New User")
        db.add(user)
        db.flush()
    tokens = issue_tokens(user.id)
    sess = UserSession(user_id=user.id, refresh_token_hash=hashlib.sha256(tokens["refresh_token"].encode()).hexdigest(),
                       expires_at=datetime.utcnow() + timedelta(days=REFRESH_EXP_DAYS))
    db.add(sess)
    db.commit()
    return tokens


@app.post("/v1/auth/logout")
def logout(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    db.query(UserSession).filter_by(user_id=user.id).delete()
    db.commit()
    return {"message": "logged out"}


@app.get("/v1/me")
def me(user: User = Depends(get_current_user)):
    return {"id": user.id, "phone": user.phone, "full_name": user.full_name}


@app.get("/v1/search/branches")
def search_branches(lat: float, lng: float, radius: float = 3, q: str = "", mode: Optional[str] = None,
                    open_now: bool = False, price_level: Optional[int] = None,
                    min_rating: float = 0, cuisine: Optional[str] = None, db: Session = Depends(get_db)):
    rows = db.query(TenantListing, Branch, Tenant).join(Branch, Branch.id == TenantListing.branch_id).join(Tenant, Tenant.id == TenantListing.tenant_id).all()
    out = []
    for listing, branch, tenant in rows:
        d = 111 * math.sqrt((branch.latitude - lat) ** 2 + (branch.longitude - lng) ** 2)
        if d > radius:
            continue
        if q and q.lower() not in f"{tenant.display_name} {branch.name}".lower():
            continue
        if price_level and listing.price_level != price_level:
            continue
        if listing.avg_rating < min_rating:
            continue
        if cuisine and (not listing.cuisines or cuisine not in listing.cuisines):
            continue
        score = (10 if open_now else 0) + (5 - min(d, 5)) + listing.avg_rating + (listing.order_count_30d / 100) + (listing.review_count / 200)
        out.append({"tenantId": tenant.id, "branchId": branch.id, "name": branch.name, "distance_km": round(d, 2), "score": score})
    return sorted(out, key=lambda x: x["score"], reverse=True)


@app.get("/v1/branches/{branch_id}")
def get_branch(branch_id: str, db: Session = Depends(get_db)):
    b = db.get(Branch, branch_id)
    if not b:
        raise HTTPException(404, "Not found")
    return b.__dict__


@app.get("/v1/branches/{branch_id}/menu")
def branch_menu(branch_id: str, db: Session = Depends(get_db)):
    categories = db.query(MenuCategory).filter(or_(MenuCategory.branch_id == branch_id, MenuCategory.branch_id.is_(None))).all()
    items = db.query(MenuItem).filter(or_(MenuItem.branch_id == branch_id, MenuItem.branch_id.is_(None)), MenuItem.is_active.is_(True)).all()
    return {"categories": [c.__dict__ for c in categories], "items": [i.__dict__ for i in items]}


@app.get("/v1/branches/{branch_id}/reviews")
def branch_reviews(branch_id: str, db: Session = Depends(get_db)):
    reviews = db.query(Review).filter_by(branch_id=branch_id, status="visible").all()
    return reviews


@app.post("/v1/orders")
def create_order(body: CreateOrderBody, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    branch = db.get(Branch, body.branchId)
    if not branch:
        raise HTTPException(404, "Branch not found")
    subtotal = 0
    order = Order(tenant_id=branch.tenant_id, branch_id=branch.id, user_id=user.id, order_number=f"{datetime.utcnow().strftime('%Y%m%d')}-{random.randint(1000,9999)}",
                  mode=body.mode, subtotal_amount=0, total_amount=0, notes=body.notes, scheduled_for=body.scheduledFor)
    db.add(order)
    db.flush()
    for line in body.items:
        item = db.get(MenuItem, line.itemId)
        if not item or item.tenant_id != branch.tenant_id or not item.is_active:
            raise HTTPException(400, detail="Invalid item")
        availability = db.query(ItemAvailability).filter_by(branch_id=branch.id, item_id=item.id).first()
        if availability and not availability.is_available:
            raise HTTPException(400, detail=f"Item unavailable: {item.name}")
        modifier_total = 0
        oi = OrderItem(order_id=order.id, item_id=item.id, name_snapshot=item.name, unit_price_snapshot=item.base_price,
                       quantity=line.qty, line_total=0)
        db.add(oi)
        db.flush()
        for mod_req in line.modifiers:
            modifier = db.get(ItemModifier, mod_req.get("modifierId"))
            if not modifier or modifier.item_id != item.id:
                continue
            for opt_id in mod_req.get("optionIds", []):
                opt = db.get(ModifierOption, opt_id)
                if not opt or opt.modifier_id != modifier.id or not opt.is_active:
                    continue
                modifier_total += opt.price_delta
                db.add(OrderItemModifier(order_item_id=oi.id, modifier_name_snapshot=modifier.name,
                                         option_name_snapshot=opt.name, price_delta_snapshot=opt.price_delta))
        line_total = (item.base_price + modifier_total) * line.qty
        oi.line_total = line_total
        subtotal += line_total
    delivery_fee = 0
    if body.mode == "delivery":
        sm = db.query(ServiceMode).filter_by(branch_id=branch.id, mode="delivery", is_enabled=True).first()
        delivery_fee = sm.delivery_fee if sm else 0
    discount = 0
    if body.promoCode:
        promo = db.query(Promotion).filter_by(tenant_id=branch.tenant_id, name=body.promoCode, is_active=True).first()
        if promo and subtotal >= promo.min_order_amount:
            if promo.type == "percent_off":
                discount = subtotal * promo.value // 100
            elif promo.type == "amount_off":
                discount = promo.value
            elif promo.type == "free_delivery":
                discount = delivery_fee
    order.subtotal_amount = subtotal
    order.discount_amount = min(discount, subtotal + delivery_fee)
    order.delivery_fee_amount = delivery_fee
    order.tax_amount = 0
    order.total_amount = subtotal + delivery_fee - order.discount_amount
    db.add(OrderEvent(order_id=order.id, actor_type="user", actor_id=user.id, event="created", data={"mode": body.mode}))
    db.commit()
    return {"orderId": order.id, "status": order.status, "total": order.total_amount}


@app.get("/v1/orders")
def list_orders(status: str = "active", user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    q = db.query(Order).filter_by(user_id=user.id)
    if status == "active":
        q = q.filter(Order.status.in_(["created", "paid", "accepted", "preparing", "ready"]))
    else:
        q = q.filter(Order.status.in_(["completed", "canceled", "refunded"]))
    return q.order_by(desc(Order.created_at)).all()


@app.get("/v1/orders/{order_id}")
def order_detail(order_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    order = db.get(Order, order_id)
    if not order or order.user_id != user.id:
        raise HTTPException(404, "Order not found")
    return order


@app.post("/v1/orders/{order_id}/cancel")
def cancel_order(order_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    order = db.get(Order, order_id)
    if not order or order.user_id != user.id:
        raise HTTPException(404, "Order not found")
    if order.status == "created" or order.status == "paid":
        if order.status == "paid" and db.query(OrderEvent).filter_by(order_id=order.id, event="accepted").first():
            raise HTTPException(400, "Accepted orders cannot be canceled")
        order.status = "canceled"
        db.add(OrderEvent(order_id=order.id, actor_type="user", actor_id=user.id, event="canceled", data={}))
        db.commit()
        return {"status": "canceled"}
    raise HTTPException(400, "Invalid status transition")


@app.post("/v1/orders/{order_id}/review")
def review_order(order_id: str, payload: dict, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    order = db.get(Order, order_id)
    if not order or order.user_id != user.id:
        raise HTTPException(404, "Order not found")
    if not (order.status == "completed"):
        raise HTTPException(400, "Only completed orders can be reviewed")
    r = Review(tenant_id=order.tenant_id, branch_id=order.branch_id, user_id=user.id, order_id=order.id,
               rating=payload.get("rating"), comment=payload.get("comment"), status="visible")
    db.add(r)
    db.commit()
    return {"reviewId": r.id}


@app.get("/v1/wallet")
def get_wallet(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    wa = ensure_wallet(db, "user", user.id)
    txns = db.query(LedgerEntry).filter_by(account_id=wa.id).order_by(desc(LedgerEntry.created_at)).limit(10).all()
    db.commit()
    return {"balance": wa.balance, "currency": "ETB", "transactions": txns}


@app.get("/v1/wallet/transactions")
def wallet_transactions(cursor: Optional[str] = None, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    wa = ensure_wallet(db, "user", user.id)
    q = db.query(LedgerEntry).filter_by(account_id=wa.id).order_by(desc(LedgerEntry.created_at))
    if cursor:
        q = q.filter(LedgerEntry.created_at < datetime.fromisoformat(cursor))
    rows = q.limit(20).all()
    next_cursor = rows[-1].created_at.isoformat() if rows else None
    return {"items": rows, "next_cursor": next_cursor}


@app.post("/v1/wallet/topup-intent")
def topup_intent(payload: dict, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    pi = PaymentIntent(user_id=user.id, purpose="topup", amount=payload["amount"], provider=payload.get("provider", "mock"),
                       currency="ETB", status="pending", provider_reference=f"MOCK-{random.randint(10000,99999)}")
    db.add(pi)
    db.commit()
    return {"payment_intent_id": pi.id, "checkout_reference": pi.provider_reference}


@app.post("/v1/orders/{order_id}/pay")
def pay_order(order_id: str, body: PayOrderBody, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    order = db.get(Order, order_id)
    if not order or order.user_id != user.id:
        raise HTTPException(404, "Order not found")
    if order.status != "created":
        raise HTTPException(400, "Order not payable")
    if body.useWallet:
        uw = ensure_wallet(db, "user", user.id)
        tw = ensure_wallet(db, "tenant", order.tenant_id)
        pw = ensure_wallet(db, "platform", "platform")
        if uw.balance < order.total_amount:
            raise HTTPException(400, "Insufficient wallet balance")
        fee = order.total_amount * PLATFORM_FEE_BPS // 10000
        merchant_amount = order.total_amount - fee
        add_ledger(db, uw, "payment", "debit", order.total_amount, "order", order.id, {"via": "wallet"})
        add_ledger(db, tw, "payment", "credit", merchant_amount, "order", order.id, {})
        add_ledger(db, pw, "fee", "credit", fee, "order", order.id, {})
        order.status = "paid"
        db.add(OrderEvent(order_id=order.id, actor_type="system", actor_id=None, event="paid", data={"method": "wallet"}))
        db.commit()
        return {"status": "paid"}
    pi = PaymentIntent(user_id=user.id, purpose="order_payment", amount=order.total_amount, provider=body.provider or "mock",
                       currency="ETB", status="pending", order_id=order.id, provider_reference=f"MOCK-{random.randint(10000,99999)}")
    db.add(pi)
    db.commit()
    return {"payment_intent_id": pi.id, "checkout_reference": pi.provider_reference}


@app.post("/v1/payments/confirm")
def confirm_payment(body: ConfirmPaymentBody, idempotency_key: str = Header(default=""), db: Session = Depends(get_db)):
    if not idempotency_key:
        raise HTTPException(400, "Idempotency-Key required")
    req_hash = hashlib.sha256(f"{body.payment_intent_id}:{body.provider_txn_id}:{body.status}".encode()).hexdigest()
    existing = db.query(IdempotencyKey).filter_by(key=idempotency_key).first()
    if existing:
        if existing.request_hash != req_hash:
            raise HTTPException(409, "Idempotency key reuse with different payload")
        return existing.response
    pi = db.get(PaymentIntent, body.payment_intent_id)
    if not pi:
        raise HTTPException(404, "payment_intent not found")
    payment = Payment(payment_intent_id=pi.id, provider_txn_id=body.provider_txn_id, status=body.status, raw_payload=body.raw_payload)
    db.add(payment)
    response = {"payment_id": payment.id, "status": body.status}
    if body.status == "succeeded":
        pi.status = "succeeded"
        uw = ensure_wallet(db, "user", pi.user_id)
        if pi.purpose == "topup":
            add_ledger(db, uw, "topup", "credit", pi.amount, "payment", pi.id, {"provider": pi.provider})
            response["wallet_balance"] = uw.balance
        elif pi.purpose == "order_payment":
            order = db.get(Order, pi.order_id)
            tw = ensure_wallet(db, "tenant", order.tenant_id)
            pw = ensure_wallet(db, "platform", "platform")
            fee = order.total_amount * PLATFORM_FEE_BPS // 10000
            merchant_amount = order.total_amount - fee
            add_ledger(db, tw, "payment", "credit", merchant_amount, "order", order.id, {"provider": pi.provider})
            add_ledger(db, pw, "fee", "credit", fee, "order", order.id, {})
            order.status = "paid"
            db.add(OrderEvent(order_id=order.id, actor_type="system", actor_id=None, event="paid", data={"method": pi.provider}))
            response["order_status"] = order.status
    else:
        pi.status = body.status
    idem = IdempotencyKey(key=idempotency_key, request_hash=req_hash, response=response)
    db.add(idem)
    db.commit()
    return response


@app.post("/v1/refunds/request")
def refund_request(payload: dict, user: User = Depends(get_current_user)):
    return {"status": "queued", "orderId": payload.get("orderId")}


@app.get("/v1/addresses")
def get_addresses(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.query(UserAddress).filter_by(user_id=user.id).all()


@app.post("/v1/addresses")
def create_address(payload: dict, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    addr = UserAddress(user_id=user.id, **payload)
    db.add(addr)
    db.commit()
    return addr


@app.patch("/v1/addresses/{addr_id}")
def patch_address(addr_id: str, payload: dict, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    addr = db.get(UserAddress, addr_id)
    if not addr or addr.user_id != user.id:
        raise HTTPException(404, "Address not found")
    for k, v in payload.items():
        setattr(addr, k, v)
    db.commit()
    return addr


@app.delete("/v1/addresses/{addr_id}")
def delete_address(addr_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    addr = db.get(UserAddress, addr_id)
    if not addr or addr.user_id != user.id:
        raise HTTPException(404, "Address not found")
    db.delete(addr)
    db.commit()
    return {"deleted": True}


@app.post("/v1/partner/tenants")
def create_tenant(payload: dict, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    t = Tenant(legal_name=payload["legal_name"], display_name=payload["display_name"], business_type=payload["business_type"], owner_user_id=user.id)
    db.add(t)
    db.commit()
    return t


@app.post("/v1/partner/tenants/{tenant_id}/documents")
def upload_tenant_doc(tenant_id: str, payload: dict, db: Session = Depends(get_db), staff: StaffMember = Depends(get_staff)):
    if staff.tenant_id != tenant_id:
        raise HTTPException(403, "Tenant isolation violation")
    d = TenantVerification(tenant_id=tenant_id, document_type=payload["document_type"], document_url=payload["document_url"], status="pending")
    db.add(d)
    db.commit()
    return d


@app.get("/v1/partner/tenants/{tenant_id}")
def get_tenant(tenant_id: str, staff: StaffMember = Depends(get_staff), db: Session = Depends(get_db)):
    if staff.tenant_id != tenant_id:
        raise HTTPException(403, "Tenant isolation violation")
    return db.get(Tenant, tenant_id)


@app.post("/v1/partner/branches")
def partner_create_branch(payload: dict, staff: StaffMember = Depends(require_permission("branches.write")), db: Session = Depends(get_db)):
    b = Branch(tenant_id=staff.tenant_id, **payload)
    db.add(b)
    db.commit()
    return b


@app.get("/v1/partner/branches")
def partner_list_branches(staff: StaffMember = Depends(require_permission("branches.read")), db: Session = Depends(get_db)):
    return db.query(Branch).filter_by(tenant_id=staff.tenant_id).all()


@app.patch("/v1/partner/branches/{branch_id}")
def partner_patch_branch(branch_id: str, payload: dict, staff: StaffMember = Depends(require_permission("branches.write")), db: Session = Depends(get_db)):
    b = db.get(Branch, branch_id)
    if not b or b.tenant_id != staff.tenant_id:
        raise HTTPException(404, "not found")
    for k, v in payload.items():
        setattr(b, k, v)
    db.commit()
    return b


@app.put("/v1/partner/branches/{branch_id}/hours")
def partner_hours(branch_id: str, payload: list[dict], staff: StaffMember = Depends(require_permission("branches.write")), db: Session = Depends(get_db)):
    b = db.get(Branch, branch_id)
    if not b or b.tenant_id != staff.tenant_id:
        raise HTTPException(404, "not found")
    db.query(BranchHour).filter_by(branch_id=branch_id).delete()
    for h in payload:
        db.add(BranchHour(branch_id=branch_id, **h))
    db.commit()
    return {"updated": True}


@app.post("/v1/partner/menu/categories")
def create_category(payload: dict, staff: StaffMember = Depends(require_permission("menu.write")), db: Session = Depends(get_db)):
    c = MenuCategory(tenant_id=staff.tenant_id, **payload)
    db.add(c)
    db.commit()
    return c


@app.patch("/v1/partner/menu/categories/{cat_id}")
def patch_category(cat_id: str, payload: dict, staff: StaffMember = Depends(require_permission("menu.write")), db: Session = Depends(get_db)):
    c = db.get(MenuCategory, cat_id)
    if not c or c.tenant_id != staff.tenant_id:
        raise HTTPException(404, "not found")
    for k, v in payload.items():
        setattr(c, k, v)
    db.commit()
    return c


@app.post("/v1/partner/menu/items")
def create_item(payload: dict, staff: StaffMember = Depends(require_permission("menu.write")), db: Session = Depends(get_db)):
    i = MenuItem(tenant_id=staff.tenant_id, **payload)
    db.add(i)
    db.commit()
    return i


@app.patch("/v1/partner/menu/items/{item_id}")
def patch_item(item_id: str, payload: dict, staff: StaffMember = Depends(require_permission("menu.write")), db: Session = Depends(get_db)):
    i = db.get(MenuItem, item_id)
    if not i or i.tenant_id != staff.tenant_id:
        raise HTTPException(404, "not found")
    for k, v in payload.items():
        setattr(i, k, v)
    db.commit()
    return i


@app.post("/v1/partner/menu/items/{item_id}/modifiers")
def create_modifier(item_id: str, payload: dict, staff: StaffMember = Depends(require_permission("menu.write")), db: Session = Depends(get_db)):
    item = db.get(MenuItem, item_id)
    if not item or item.tenant_id != staff.tenant_id:
        raise HTTPException(404, "not found")
    m = ItemModifier(item_id=item_id, tenant_id=staff.tenant_id, **payload)
    db.add(m)
    db.flush()
    for opt in payload.get("options", []):
        db.add(ModifierOption(modifier_id=m.id, **opt))
    db.commit()
    return m


@app.patch("/v1/partner/menu/modifiers/{mod_id}")
def patch_modifier(mod_id: str, payload: dict, staff: StaffMember = Depends(require_permission("menu.write")), db: Session = Depends(get_db)):
    m = db.get(ItemModifier, mod_id)
    if not m or m.tenant_id != staff.tenant_id:
        raise HTTPException(404, "not found")
    for k, v in payload.items():
        if k != "options":
            setattr(m, k, v)
    db.commit()
    return m


@app.put("/v1/partner/menu/items/{item_id}/availability")
def set_availability(item_id: str, payload: dict, staff: StaffMember = Depends(require_permission("menu.write")), db: Session = Depends(get_db)):
    branch_id = payload["branch_id"]
    branch = db.get(Branch, branch_id)
    if not branch or branch.tenant_id != staff.tenant_id:
        raise HTTPException(404, "branch not found")
    av = db.query(ItemAvailability).filter_by(branch_id=branch_id, item_id=item_id).first()
    if not av:
        av = ItemAvailability(branch_id=branch_id, item_id=item_id, is_available=payload["is_available"])
        db.add(av)
    else:
        av.is_available = payload["is_available"]
        av.updated_at = datetime.utcnow()
    db.commit()
    return av


@app.get("/v1/partner/orders")
def partner_orders(status: str = "new", branchId: Optional[str] = None, staff: StaffMember = Depends(require_permission("orders.read")), db: Session = Depends(get_db)):
    q = db.query(Order).filter_by(tenant_id=staff.tenant_id)
    if branchId:
        q = q.filter_by(branch_id=branchId)
    if status == "new":
        q = q.filter(Order.status.in_(["paid"]))
    elif status == "active":
        q = q.filter(Order.status.in_(["accepted", "preparing", "ready"]))
    else:
        q = q.filter(Order.status.in_(["completed", "canceled", "refunded"]))
    return q.order_by(desc(Order.created_at)).all()


@app.get("/v1/partner/orders/{order_id}")
def partner_order(order_id: str, staff: StaffMember = Depends(require_permission("orders.read")), db: Session = Depends(get_db)):
    o = db.get(Order, order_id)
    if not o or o.tenant_id != staff.tenant_id:
        raise HTTPException(404, "not found")
    return o


def transition_order(o: Order, next_status: str, actor_id: str, db: Session):
    allowed = {
        "paid": ["accepted", "canceled", "refunded"],
        "accepted": ["preparing"],
        "preparing": ["ready"],
        "ready": ["completed"],
        "created": ["paid", "canceled"],
    }
    if next_status not in allowed.get(o.status, []):
        raise HTTPException(400, f"Invalid transition {o.status}->{next_status}")
    o.status = next_status
    db.add(OrderEvent(order_id=o.id, actor_type="staff", actor_id=actor_id, event=next_status, data={}))


@app.post("/v1/partner/orders/{order_id}/accept")
def partner_accept(order_id: str, staff: StaffMember = Depends(require_permission("orders.write")), db: Session = Depends(get_db)):
    o = db.get(Order, order_id)
    if not o or o.tenant_id != staff.tenant_id:
        raise HTTPException(404, "not found")
    transition_order(o, "accepted", staff.user_id, db)
    db.commit()
    return {"status": o.status}


@app.post("/v1/partner/orders/{order_id}/reject")
def partner_reject(order_id: str, payload: dict, staff: StaffMember = Depends(require_permission("orders.write")), db: Session = Depends(get_db)):
    o = db.get(Order, order_id)
    if not o or o.tenant_id != staff.tenant_id:
        raise HTTPException(404, "not found")
    transition_order(o, "canceled", staff.user_id, db)
    db.add(OrderEvent(order_id=o.id, actor_type="staff", actor_id=staff.user_id, event="rejected", data=payload))
    db.commit()
    return {"status": o.status}


@app.post("/v1/partner/orders/{order_id}/status")
def partner_status(order_id: str, payload: dict, staff: StaffMember = Depends(require_permission("orders.write")), db: Session = Depends(get_db)):
    o = db.get(Order, order_id)
    if not o or o.tenant_id != staff.tenant_id:
        raise HTTPException(404, "not found")
    transition_order(o, payload["status"], staff.user_id, db)
    db.commit()
    return {"status": o.status}


@app.post("/v1/partner/promotions")
def create_promo(payload: dict, staff: StaffMember = Depends(require_permission("promotions.write")), db: Session = Depends(get_db)):
    p = Promotion(tenant_id=staff.tenant_id, **payload)
    db.add(p)
    db.commit()
    return p


@app.get("/v1/partner/promotions")
def list_promo(staff: StaffMember = Depends(require_permission("promotions.read")), db: Session = Depends(get_db)):
    return db.query(Promotion).filter_by(tenant_id=staff.tenant_id).all()


@app.patch("/v1/partner/promotions/{promo_id}")
def patch_promo(promo_id: str, payload: dict, staff: StaffMember = Depends(require_permission("promotions.write")), db: Session = Depends(get_db)):
    p = db.get(Promotion, promo_id)
    if not p or p.tenant_id != staff.tenant_id:
        raise HTTPException(404, "not found")
    for k, v in payload.items():
        setattr(p, k, v)
    db.commit()
    return p


@app.post("/v1/partner/staff/invite")
def invite_staff(payload: dict, staff: StaffMember = Depends(require_permission("staff.write")), db: Session = Depends(get_db)):
    user = db.query(User).filter(or_(User.phone == payload.get("phone"), User.email == payload.get("email"))).first()
    if not user:
        user = User(phone=payload.get("phone"), email=payload.get("email"), full_name="Invited staff")
        db.add(user)
        db.flush()
    sm = StaffMember(tenant_id=staff.tenant_id, user_id=user.id, role_id=payload["roleId"], status="active")
    db.add(sm)
    db.commit()
    return sm


@app.get("/v1/partner/staff")
def list_staff(staff: StaffMember = Depends(require_permission("staff.read")), db: Session = Depends(get_db)):
    return db.query(StaffMember).filter_by(tenant_id=staff.tenant_id).all()


@app.patch("/v1/partner/staff/{staff_id}")
def patch_staff(staff_id: str, payload: dict, caller: StaffMember = Depends(require_permission("staff.write")), db: Session = Depends(get_db)):
    sm = db.get(StaffMember, staff_id)
    if not sm or sm.tenant_id != caller.tenant_id:
        raise HTTPException(404, "not found")
    for k, v in payload.items():
        setattr(sm, "role_id" if k == "roleId" else k, v)
    db.commit()
    return sm


@app.get("/v1/partner/roles")
def list_roles(staff: StaffMember = Depends(require_permission("staff.read")), db: Session = Depends(get_db)):
    return db.query(Role).filter(or_(Role.tenant_id == staff.tenant_id, Role.tenant_id.is_(None))).all()


@app.post("/v1/partner/roles")
def create_role(payload: dict, staff: StaffMember = Depends(require_permission("staff.write")), db: Session = Depends(get_db)):
    r = Role(tenant_id=staff.tenant_id, name=payload["name"])
    db.add(r)
    db.commit()
    return r


@app.put("/v1/partner/roles/{role_id}/permissions")
def set_role_permissions(role_id: str, payload: dict, staff: StaffMember = Depends(require_permission("staff.write")), db: Session = Depends(get_db)):
    r = db.get(Role, role_id)
    if not r or r.tenant_id not in (None, staff.tenant_id):
        raise HTTPException(404, "role not found")
    db.query(RolePermission).filter_by(role_id=role_id).delete()
    for perm in payload.get("permissions", []):
        db.add(RolePermission(role_id=role_id, permission=perm))
    db.commit()
    return {"updated": True}


@app.get("/v1/partner/wallet")
def partner_wallet(staff: StaffMember = Depends(require_permission("wallet.read")), db: Session = Depends(get_db)):
    wa = ensure_wallet(db, "tenant", staff.tenant_id)
    txns = db.query(LedgerEntry).filter_by(account_id=wa.id).order_by(desc(LedgerEntry.created_at)).limit(20).all()
    db.commit()
    return {"balance": wa.balance, "transactions": txns}


@app.get("/v1/partner/settlements")
def settlements(staff: StaffMember = Depends(require_permission("wallet.read")), db: Session = Depends(get_db)):
    wa = ensure_wallet(db, "tenant", staff.tenant_id)
    gross = db.query(func.coalesce(func.sum(LedgerEntry.amount), 0)).filter_by(account_id=wa.id, direction="credit", type="payment").scalar() or 0
    fees = db.query(func.coalesce(func.sum(LedgerEntry.amount), 0)).join(WalletAccount, WalletAccount.id == LedgerEntry.account_id).filter(
        WalletAccount.owner_type == "platform", LedgerEntry.type == "fee").scalar() or 0
    return {"gross_sales_minor": gross, "fees_minor": fees}


@app.post("/v1/partner/payouts/request")
def payout_request(payload: dict, staff: StaffMember = Depends(require_permission("wallet.write")), db: Session = Depends(get_db)):
    wa = ensure_wallet(db, "tenant", staff.tenant_id)
    amount = payload["amount"]
    if wa.balance < amount:
        raise HTTPException(400, "Insufficient balance")
    add_ledger(db, wa, "payout", "debit", amount, "payout", "pending", {"method": payload["method"]})
    p = Payout(tenant_id=staff.tenant_id, amount=amount, currency="ETB", method=payload["method"], destination=payload["destination"], status="processing")
    db.add(p)
    db.commit()
    return p


@app.get("/v1/admin/tenants")
def admin_tenants(status: str = "pending", user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if user.email != "admin@local":
        raise HTTPException(403, "Admin required")
    return db.query(Tenant).filter_by(status=status).all()


@app.post("/v1/admin/tenants/{tenant_id}/approve")
def admin_approve_tenant(tenant_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if user.email != "admin@local":
        raise HTTPException(403, "Admin required")
    t = db.get(Tenant, tenant_id)
    t.status = "active"
    db.commit()
    return t


@app.post("/v1/admin/tenants/{tenant_id}/reject")
def admin_reject_tenant(tenant_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if user.email != "admin@local":
        raise HTTPException(403, "Admin required")
    t = db.get(Tenant, tenant_id)
    t.status = "suspended"
    db.commit()
    return t


@app.patch("/v1/admin/reviews/{review_id}")
def admin_review(review_id: str, payload: dict, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if user.email != "admin@local":
        raise HTTPException(403, "Admin required")
    r = db.get(Review, review_id)
    r.status = payload["status"]
    db.commit()
    return r


@app.post("/v1/admin/refunds/{refund_id}/{action}")
def admin_refund(refund_id: str, action: str, user: User = Depends(get_current_user)):
    if user.email != "admin@local":
        raise HTTPException(403, "Admin required")
    return {"refundId": refund_id, "action": action}


@app.post("/v1/reservations")
def create_reservation(payload: dict, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    from .models import Reservation
    branch = db.get(Branch, payload["branch_id"])
    r = Reservation(tenant_id=branch.tenant_id, user_id=user.id, **payload)
    db.add(r)
    db.commit()
    return r


@app.get("/v1/reservations")
def list_reservations(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    from .models import Reservation
    return db.query(Reservation).filter_by(user_id=user.id).all()


@app.post("/v1/reservations/{res_id}/cancel")
def cancel_res(res_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    from .models import Reservation
    r = db.get(Reservation, res_id)
    if r.user_id != user.id:
        raise HTTPException(403, "forbidden")
    r.status = "canceled"
    db.commit()
    return r
