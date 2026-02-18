# Demobemni MVP Backend (FastAPI)

Multi-tenant backend for Addis Ababa restaurants/cafés marketplace, including:
- Consumer mobile API
- Partner dashboard API
- Admin API
- Internal append-only ledger and mocked provider payments

## Stack
- FastAPI + SQLAlchemy (modular monolith)
- PostgreSQL-compatible schema migration in `migrations/0001_init.sql`
- JWT auth + OTP mock

## Setup
```bash
python -m venv .venv && source .venv/bin/activate
pip install -e .
cp .env.example .env
python seed.py
uvicorn app.main:app --reload
```

OpenAPI docs:
- `http://localhost:8000/docs`

## Environment variables
See `.env.example`.

## Migration
Run SQL directly against PostgreSQL:
```bash
psql "$DATABASE_URL" -f migrations/0001_init.sql
```

## Seed data
```bash
python seed.py
```
Prints IDs for test users/tenant/branch.

## Example curls

### OTP login
```bash
curl -X POST http://localhost:8000/v1/auth/request-otp -H 'Content-Type: application/json' -d '{"phone":"+251911000002"}'
curl -X POST http://localhost:8000/v1/auth/verify-otp -H 'Content-Type: application/json' -d '{"phone":"+251911000002","code":"<code>"}'
```

### Search branches
```bash
curl "http://localhost:8000/v1/search/branches?lat=8.98&lng=38.76&radius=5"
```

### Create order + pay by provider
```bash
curl -X POST http://localhost:8000/v1/orders -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' -d '{
  "branchId":"<branch-id>",
  "mode":"pickup",
  "items":[{"itemId":"<item-id>","qty":1,"modifiers":[]}]
}'

curl -X POST http://localhost:8000/v1/orders/<order-id>/pay -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' -d '{"useWallet":false,"provider":"mock"}'

curl -X POST http://localhost:8000/v1/payments/confirm \
  -H 'Idempotency-Key: demo-key-1' -H 'Content-Type: application/json' \
  -d '{"payment_intent_id":"<pi-id>","provider_txn_id":"tx123","status":"succeeded","raw_payload":{}}'
```

## Tests
```bash
pytest -q
```
Covers key flows:
- order creation total computation
- idempotent payment confirmation + ledger side effects
- partner order accept -> preparing -> ready -> completed transitions
