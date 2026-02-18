from datetime import datetime, timedelta

from app.db import SessionLocal, Base, engine
from app.models import Branch, MenuCategory, MenuItem, Role, RolePermission, ServiceMode, StaffMember, Tenant, TenantListing, User

Base.metadata.create_all(bind=engine)

db = SessionLocal()

owner = User(phone="+251911000001", email="owner@haba.com", full_name="Owner")
consumer = User(phone="+251911000002", email="consumer@haba.com", full_name="Consumer")
admin = User(email="admin@local", full_name="Admin")
db.add_all([owner, consumer, admin])
db.flush()

tenant = Tenant(legal_name="Habesha Beans PLC", display_name="Habesha Beans", business_type="cafe", status="active", owner_user_id=owner.id)
db.add(tenant)
db.flush()

role = Role(tenant_id=tenant.id, name="Owner")
db.add(role)
db.flush()
perms = ["*", "menu.write", "menu.read", "orders.read", "orders.write", "branches.read", "branches.write", "wallet.read", "wallet.write", "staff.read", "staff.write", "promotions.read", "promotions.write"]
for p in perms:
    db.add(RolePermission(role_id=role.id, permission=p))

staff = StaffMember(tenant_id=tenant.id, user_id=owner.id, role_id=role.id)
db.add(staff)

branch = Branch(tenant_id=tenant.id, name="Bole Branch", phone="+251911100100", address_text="Bole, Addis Ababa", latitude=8.9806, longitude=38.7578)
db.add(branch)
db.flush()

cat = MenuCategory(tenant_id=tenant.id, name="Coffee", sort_order=1)
db.add(cat)
db.flush()
item = MenuItem(tenant_id=tenant.id, category_id=cat.id, name="Macchiato", description="Local favorite", base_price=18000)
db.add(item)

mode_pickup = ServiceMode(branch_id=branch.id, mode="pickup", is_enabled=True, delivery_fee=0)
mode_dine = ServiceMode(branch_id=branch.id, mode="dine_in", is_enabled=True, delivery_fee=0)
mode_delivery = ServiceMode(branch_id=branch.id, mode="delivery", is_enabled=True, delivery_fee=5000)
db.add_all([mode_pickup, mode_dine, mode_delivery])

listing = TenantListing(tenant_id=tenant.id, branch_id=branch.id, cuisines=["ethiopian", "coffee"], price_level=2, avg_rating=4.6, review_count=120, order_count_30d=340)
db.add(listing)

db.commit()
print({"tenant_id": tenant.id, "branch_id": branch.id, "owner_user_id": owner.id, "consumer_user_id": consumer.id})
