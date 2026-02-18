import uuid
from datetime import datetime
from sqlalchemy import String, Integer, Boolean, DateTime, ForeignKey, Text, JSON, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base


def uuid_pk():
    return mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = uuid_pk()
    phone: Mapped[str | None] = mapped_column(String(32), unique=True, nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True)
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    full_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class UserSession(Base):
    __tablename__ = "user_sessions"
    id: Mapped[str] = uuid_pk()
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    refresh_token_hash: Mapped[str] = mapped_column(String(255))
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class UserAddress(Base):
    __tablename__ = "user_addresses"
    id: Mapped[str] = uuid_pk()
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    label: Mapped[str | None] = mapped_column(String(64), nullable=True)
    latitude: Mapped[float] = mapped_column()
    longitude: Mapped[float] = mapped_column()
    address_text: Mapped[str] = mapped_column(Text)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Tenant(Base):
    __tablename__ = "tenants"
    id: Mapped[str] = uuid_pk()
    legal_name: Mapped[str] = mapped_column(String(255))
    display_name: Mapped[str] = mapped_column(String(255))
    business_type: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(32), default="pending")
    owner_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class TenantVerification(Base):
    __tablename__ = "tenant_verification"
    id: Mapped[str] = uuid_pk()
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"))
    document_type: Mapped[str] = mapped_column(String(64))
    document_url: Mapped[str] = mapped_column(Text)
    verified_by_admin_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="pending")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Role(Base):
    __tablename__ = "roles"
    id: Mapped[str] = uuid_pk()
    tenant_id: Mapped[str | None] = mapped_column(ForeignKey("tenants.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class RolePermission(Base):
    __tablename__ = "role_permissions"
    id: Mapped[str] = uuid_pk()
    role_id: Mapped[str] = mapped_column(ForeignKey("roles.id"))
    permission: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class StaffMember(Base):
    __tablename__ = "staff_members"
    id: Mapped[str] = uuid_pk()
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    role_id: Mapped[str] = mapped_column(ForeignKey("roles.id"))
    status: Mapped[str] = mapped_column(String(32), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Branch(Base):
    __tablename__ = "branches"
    id: Mapped[str] = uuid_pk()
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"))
    name: Mapped[str] = mapped_column(String(255))
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    address_text: Mapped[str] = mapped_column(Text)
    latitude: Mapped[float] = mapped_column()
    longitude: Mapped[float] = mapped_column()
    timezone: Mapped[str] = mapped_column(String(64), default="Africa/Addis_Ababa")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class BranchHour(Base):
    __tablename__ = "branch_hours"
    id: Mapped[str] = uuid_pk()
    branch_id: Mapped[str] = mapped_column(ForeignKey("branches.id"))
    day_of_week: Mapped[int] = mapped_column(Integer)
    open_time: Mapped[str | None] = mapped_column(String(8), nullable=True)
    close_time: Mapped[str | None] = mapped_column(String(8), nullable=True)
    is_closed: Mapped[bool] = mapped_column(Boolean, default=False)


class BranchClosure(Base):
    __tablename__ = "branch_closures"
    id: Mapped[str] = uuid_pk()
    branch_id: Mapped[str] = mapped_column(ForeignKey("branches.id"))
    start_datetime: Mapped[datetime] = mapped_column(DateTime)
    end_datetime: Mapped[datetime] = mapped_column(DateTime)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class ServiceMode(Base):
    __tablename__ = "service_modes"
    id: Mapped[str] = uuid_pk()
    branch_id: Mapped[str] = mapped_column(ForeignKey("branches.id"))
    mode: Mapped[str] = mapped_column(String(16))
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    min_order_amount: Mapped[int] = mapped_column(Integer, default=0)
    delivery_fee: Mapped[int] = mapped_column(Integer, default=0)
    estimated_prep_minutes: Mapped[int] = mapped_column(Integer, default=20)


class MenuCategory(Base):
    __tablename__ = "menu_categories"
    id: Mapped[str] = uuid_pk()
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"))
    branch_id: Mapped[str | None] = mapped_column(ForeignKey("branches.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(255))
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class MenuItem(Base):
    __tablename__ = "menu_items"
    id: Mapped[str] = uuid_pk()
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"))
    branch_id: Mapped[str | None] = mapped_column(ForeignKey("branches.id"), nullable=True)
    category_id: Mapped[str] = mapped_column(ForeignKey("menu_categories.id"))
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    base_price: Mapped[int] = mapped_column(Integer)
    image_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_taxable: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ItemModifier(Base):
    __tablename__ = "item_modifiers"
    id: Mapped[str] = uuid_pk()
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"))
    item_id: Mapped[str] = mapped_column(ForeignKey("menu_items.id"))
    name: Mapped[str] = mapped_column(String(255))
    selection_type: Mapped[str] = mapped_column(String(16), default="single")
    min_select: Mapped[int] = mapped_column(Integer, default=0)
    max_select: Mapped[int] = mapped_column(Integer, default=1)
    is_required: Mapped[bool] = mapped_column(Boolean, default=False)


class ModifierOption(Base):
    __tablename__ = "modifier_options"
    id: Mapped[str] = uuid_pk()
    modifier_id: Mapped[str] = mapped_column(ForeignKey("item_modifiers.id"))
    name: Mapped[str] = mapped_column(String(255))
    price_delta: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class ItemAvailability(Base):
    __tablename__ = "item_availability"
    id: Mapped[str] = uuid_pk()
    branch_id: Mapped[str] = mapped_column(ForeignKey("branches.id"))
    item_id: Mapped[str] = mapped_column(ForeignKey("menu_items.id"))
    is_available: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Order(Base):
    __tablename__ = "orders"
    id: Mapped[str] = uuid_pk()
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"))
    branch_id: Mapped[str] = mapped_column(ForeignKey("branches.id"))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    order_number: Mapped[str] = mapped_column(String(64))
    mode: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(32), default="created")
    subtotal_amount: Mapped[int] = mapped_column(Integer)
    discount_amount: Mapped[int] = mapped_column(Integer, default=0)
    delivery_fee_amount: Mapped[int] = mapped_column(Integer, default=0)
    tax_amount: Mapped[int] = mapped_column(Integer, default=0)
    total_amount: Mapped[int] = mapped_column(Integer)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    scheduled_for: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class OrderItem(Base):
    __tablename__ = "order_items"
    id: Mapped[str] = uuid_pk()
    order_id: Mapped[str] = mapped_column(ForeignKey("orders.id"))
    item_id: Mapped[str] = mapped_column(ForeignKey("menu_items.id"))
    name_snapshot: Mapped[str] = mapped_column(String(255))
    unit_price_snapshot: Mapped[int] = mapped_column(Integer)
    quantity: Mapped[int] = mapped_column(Integer)
    line_total: Mapped[int] = mapped_column(Integer)


class OrderItemModifier(Base):
    __tablename__ = "order_item_modifiers"
    id: Mapped[str] = uuid_pk()
    order_item_id: Mapped[str] = mapped_column(ForeignKey("order_items.id"))
    modifier_name_snapshot: Mapped[str] = mapped_column(String(255))
    option_name_snapshot: Mapped[str] = mapped_column(String(255))
    price_delta_snapshot: Mapped[int] = mapped_column(Integer)


class OrderEvent(Base):
    __tablename__ = "order_events"
    id: Mapped[str] = uuid_pk()
    order_id: Mapped[str] = mapped_column(ForeignKey("orders.id"))
    actor_type: Mapped[str] = mapped_column(String(16))
    actor_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    event: Mapped[str] = mapped_column(String(64))
    data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Reservation(Base):
    __tablename__ = "reservations"
    id: Mapped[str] = uuid_pk()
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"))
    branch_id: Mapped[str] = mapped_column(ForeignKey("branches.id"))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    party_size: Mapped[int] = mapped_column(Integer)
    reserved_at: Mapped[datetime] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String(32), default="requested")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class Review(Base):
    __tablename__ = "reviews"
    id: Mapped[str] = uuid_pk()
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"))
    branch_id: Mapped[str] = mapped_column(ForeignKey("branches.id"))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    order_id: Mapped[str | None] = mapped_column(ForeignKey("orders.id"), nullable=True)
    rating: Mapped[int] = mapped_column(Integer)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="visible")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Promotion(Base):
    __tablename__ = "promotions"
    id: Mapped[str] = uuid_pk()
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"))
    name: Mapped[str] = mapped_column(String(255))
    type: Mapped[str] = mapped_column(String(32))
    value: Mapped[int] = mapped_column(Integer)
    min_order_amount: Mapped[int] = mapped_column(Integer, default=0)
    start_at: Mapped[datetime] = mapped_column(DateTime)
    end_at: Mapped[datetime] = mapped_column(DateTime)
    usage_limit_total: Mapped[int | None] = mapped_column(Integer, nullable=True)
    usage_limit_per_user: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class PromotionRedemption(Base):
    __tablename__ = "promotion_redemptions"
    id: Mapped[str] = uuid_pk()
    promotion_id: Mapped[str] = mapped_column(ForeignKey("promotions.id"))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    order_id: Mapped[str] = mapped_column(ForeignKey("orders.id"))
    redeemed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class WalletAccount(Base):
    __tablename__ = "wallet_accounts"
    __table_args__ = (UniqueConstraint("owner_type", "owner_id", "currency"),)
    id: Mapped[str] = uuid_pk()
    owner_type: Mapped[str] = mapped_column(String(16))
    owner_id: Mapped[str] = mapped_column(String(36))
    currency: Mapped[str] = mapped_column(String(8), default="ETB")
    balance: Mapped[int] = mapped_column(Integer, default=0)


class LedgerEntry(Base):
    __tablename__ = "ledger_entries"
    id: Mapped[str] = uuid_pk()
    account_id: Mapped[str] = mapped_column(ForeignKey("wallet_accounts.id"))
    type: Mapped[str] = mapped_column(String(32))
    direction: Mapped[str] = mapped_column(String(16))
    amount: Mapped[int] = mapped_column(Integer)
    reference_type: Mapped[str] = mapped_column(String(32))
    reference_id: Mapped[str] = mapped_column(String(36))
    metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class PaymentIntent(Base):
    __tablename__ = "payment_intents"
    id: Mapped[str] = uuid_pk()
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    purpose: Mapped[str] = mapped_column(String(32))
    amount: Mapped[int] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(8), default="ETB")
    provider: Mapped[str] = mapped_column(String(32))
    provider_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="created")
    order_id: Mapped[str | None] = mapped_column(ForeignKey("orders.id"), nullable=True)
    return_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    callback_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Payment(Base):
    __tablename__ = "payments"
    id: Mapped[str] = uuid_pk()
    payment_intent_id: Mapped[str] = mapped_column(ForeignKey("payment_intents.id"))
    provider_txn_id: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(32))
    raw_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Payout(Base):
    __tablename__ = "payouts"
    id: Mapped[str] = uuid_pk()
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"))
    amount: Mapped[int] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(8), default="ETB")
    method: Mapped[str] = mapped_column(String(32))
    destination: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(32), default="requested")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class TenantListing(Base):
    __tablename__ = "tenant_listings"
    id: Mapped[str] = uuid_pk()
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"))
    branch_id: Mapped[str] = mapped_column(ForeignKey("branches.id"))
    cuisines: Mapped[list | None] = mapped_column(JSON, nullable=True)
    price_level: Mapped[int | None] = mapped_column(Integer, nullable=True)
    avg_rating: Mapped[float] = mapped_column(default=0)
    review_count: Mapped[int] = mapped_column(Integer, default=0)
    order_count_30d: Mapped[int] = mapped_column(Integer, default=0)
    is_featured: Mapped[bool] = mapped_column(Boolean, default=False)


class IdempotencyKey(Base):
    __tablename__ = "idempotency_keys"
    id: Mapped[str] = uuid_pk()
    key: Mapped[str] = mapped_column(String(128), unique=True)
    request_hash: Mapped[str] = mapped_column(String(128))
    response: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
