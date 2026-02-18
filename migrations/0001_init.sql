-- MVP schema for Demobemni, PostgreSQL
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE TABLE users (
  id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  phone text UNIQUE,
  email text UNIQUE,
  password_hash text,
  full_name text,
  status text NOT NULL DEFAULT 'active',
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE user_sessions (
  id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id uuid NOT NULL REFERENCES users(id),
  refresh_token_hash text NOT NULL,
  expires_at timestamptz NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE user_addresses (
  id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id uuid NOT NULL REFERENCES users(id),
  label text,
  latitude double precision NOT NULL,
  longitude double precision NOT NULL,
  address_text text NOT NULL,
  is_default boolean NOT NULL DEFAULT false,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE tenants (
  id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  legal_name text NOT NULL,
  display_name text NOT NULL,
  business_type text NOT NULL,
  status text NOT NULL DEFAULT 'pending',
  owner_user_id uuid REFERENCES users(id),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE tenant_verification (
  id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  tenant_id uuid NOT NULL REFERENCES tenants(id),
  document_type text NOT NULL,
  document_url text NOT NULL,
  verified_by_admin_id uuid REFERENCES users(id),
  status text NOT NULL DEFAULT 'pending',
  notes text,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE roles (
  id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  tenant_id uuid REFERENCES tenants(id),
  name text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE role_permissions (
  id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  role_id uuid NOT NULL REFERENCES roles(id),
  permission text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE staff_members (
  id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  tenant_id uuid NOT NULL REFERENCES tenants(id),
  user_id uuid NOT NULL REFERENCES users(id),
  role_id uuid NOT NULL REFERENCES roles(id),
  status text NOT NULL DEFAULT 'active',
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE branches (
  id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  tenant_id uuid NOT NULL REFERENCES tenants(id),
  name text NOT NULL,
  phone text,
  address_text text NOT NULL,
  latitude double precision NOT NULL,
  longitude double precision NOT NULL,
  timezone text NOT NULL DEFAULT 'Africa/Addis_Ababa',
  is_active boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE branch_hours (
  id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  branch_id uuid NOT NULL REFERENCES branches(id),
  day_of_week int NOT NULL,
  open_time time,
  close_time time,
  is_closed boolean NOT NULL DEFAULT false
);
CREATE TABLE branch_closures (
  id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  branch_id uuid NOT NULL REFERENCES branches(id),
  start_datetime timestamptz NOT NULL,
  end_datetime timestamptz NOT NULL,
  reason text
);
CREATE TABLE service_modes (
  id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  branch_id uuid NOT NULL REFERENCES branches(id),
  mode text NOT NULL,
  is_enabled boolean NOT NULL DEFAULT true,
  min_order_amount int NOT NULL DEFAULT 0,
  delivery_fee int NOT NULL DEFAULT 0,
  estimated_prep_minutes int NOT NULL DEFAULT 20
);
CREATE TABLE menu_categories (
  id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  tenant_id uuid NOT NULL REFERENCES tenants(id),
  branch_id uuid REFERENCES branches(id),
  name text NOT NULL,
  sort_order int NOT NULL DEFAULT 0,
  is_active boolean NOT NULL DEFAULT true
);
CREATE TABLE menu_items (
  id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  tenant_id uuid NOT NULL REFERENCES tenants(id),
  branch_id uuid REFERENCES branches(id),
  category_id uuid NOT NULL REFERENCES menu_categories(id),
  name text NOT NULL,
  description text,
  base_price int NOT NULL,
  image_url text,
  is_active boolean NOT NULL DEFAULT true,
  is_taxable boolean NOT NULL DEFAULT false,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE item_modifiers (
  id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  tenant_id uuid NOT NULL REFERENCES tenants(id),
  item_id uuid NOT NULL REFERENCES menu_items(id),
  name text NOT NULL,
  selection_type text NOT NULL,
  min_select int NOT NULL DEFAULT 0,
  max_select int NOT NULL DEFAULT 1,
  is_required boolean NOT NULL DEFAULT false
);
CREATE TABLE modifier_options (
  id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  modifier_id uuid NOT NULL REFERENCES item_modifiers(id),
  name text NOT NULL,
  price_delta int NOT NULL DEFAULT 0,
  is_active boolean NOT NULL DEFAULT true
);
CREATE TABLE item_availability (
  id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  branch_id uuid NOT NULL REFERENCES branches(id),
  item_id uuid NOT NULL REFERENCES menu_items(id),
  is_available boolean NOT NULL DEFAULT true,
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE orders (
  id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  tenant_id uuid NOT NULL REFERENCES tenants(id),
  branch_id uuid NOT NULL REFERENCES branches(id),
  user_id uuid NOT NULL REFERENCES users(id),
  order_number text NOT NULL,
  mode text NOT NULL,
  status text NOT NULL,
  subtotal_amount int NOT NULL,
  discount_amount int NOT NULL DEFAULT 0,
  delivery_fee_amount int NOT NULL DEFAULT 0,
  tax_amount int NOT NULL DEFAULT 0,
  total_amount int NOT NULL,
  notes text,
  scheduled_for timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE order_items (
  id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  order_id uuid NOT NULL REFERENCES orders(id),
  item_id uuid NOT NULL REFERENCES menu_items(id),
  name_snapshot text NOT NULL,
  unit_price_snapshot int NOT NULL,
  quantity int NOT NULL,
  line_total int NOT NULL
);
CREATE TABLE order_item_modifiers (
  id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  order_item_id uuid NOT NULL REFERENCES order_items(id),
  modifier_name_snapshot text NOT NULL,
  option_name_snapshot text NOT NULL,
  price_delta_snapshot int NOT NULL
);
CREATE TABLE order_events (
  id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  order_id uuid NOT NULL REFERENCES orders(id),
  actor_type text NOT NULL,
  actor_id uuid,
  event text NOT NULL,
  data jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE reservations (
  id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  tenant_id uuid NOT NULL REFERENCES tenants(id),
  branch_id uuid NOT NULL REFERENCES branches(id),
  user_id uuid NOT NULL REFERENCES users(id),
  party_size int NOT NULL,
  reserved_at timestamptz NOT NULL,
  status text NOT NULL,
  notes text
);
CREATE TABLE reviews (
  id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  tenant_id uuid NOT NULL REFERENCES tenants(id),
  branch_id uuid NOT NULL REFERENCES branches(id),
  user_id uuid NOT NULL REFERENCES users(id),
  order_id uuid REFERENCES orders(id),
  rating int NOT NULL,
  comment text,
  status text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE promotions (
  id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  tenant_id uuid NOT NULL REFERENCES tenants(id),
  name text NOT NULL,
  type text NOT NULL,
  value int NOT NULL,
  min_order_amount int NOT NULL,
  start_at timestamptz NOT NULL,
  end_at timestamptz NOT NULL,
  usage_limit_total int,
  usage_limit_per_user int,
  is_active boolean NOT NULL DEFAULT true
);
CREATE TABLE promotion_redemptions (
  id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  promotion_id uuid NOT NULL REFERENCES promotions(id),
  user_id uuid NOT NULL REFERENCES users(id),
  order_id uuid NOT NULL REFERENCES orders(id),
  redeemed_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE wallet_accounts (
  id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  owner_type text NOT NULL,
  owner_id uuid NOT NULL,
  currency text NOT NULL DEFAULT 'ETB',
  balance int NOT NULL DEFAULT 0,
  UNIQUE(owner_type, owner_id, currency)
);
CREATE TABLE ledger_entries (
  id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  account_id uuid NOT NULL REFERENCES wallet_accounts(id),
  type text NOT NULL,
  direction text NOT NULL,
  amount int NOT NULL,
  reference_type text NOT NULL,
  reference_id uuid NOT NULL,
  metadata jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE payment_intents (
  id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id uuid NOT NULL REFERENCES users(id),
  purpose text NOT NULL,
  amount int NOT NULL,
  currency text NOT NULL,
  provider text NOT NULL,
  provider_reference text,
  status text NOT NULL,
  order_id uuid REFERENCES orders(id),
  return_url text,
  callback_url text,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE payments (
  id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  payment_intent_id uuid NOT NULL REFERENCES payment_intents(id),
  provider_txn_id text NOT NULL,
  status text NOT NULL,
  raw_payload jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE payouts (
  id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  tenant_id uuid NOT NULL REFERENCES tenants(id),
  amount int NOT NULL,
  currency text NOT NULL,
  method text NOT NULL,
  destination text NOT NULL,
  status text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE tenant_listings (
  id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  tenant_id uuid NOT NULL REFERENCES tenants(id),
  branch_id uuid NOT NULL REFERENCES branches(id),
  cuisines text[],
  price_level int,
  avg_rating numeric(3,2) NOT NULL DEFAULT 0,
  review_count int NOT NULL DEFAULT 0,
  order_count_30d int NOT NULL DEFAULT 0,
  is_featured boolean NOT NULL DEFAULT false
);
CREATE TABLE idempotency_keys (
  id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  key text UNIQUE NOT NULL,
  request_hash text NOT NULL,
  response jsonb NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);
