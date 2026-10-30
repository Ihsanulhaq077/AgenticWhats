# AgenticWhats — Multi-Tenant Agentic AI WhatsApp Business Automation Platform

A SaaS platform that connects businesses to the **official WhatsApp Business Platform** and answers customers with an **agentic AI** (LangGraph + RAG + deterministic tool calling): it handles FAQs, menu questions, ordering, order status, table bookings, cancellations, multilingual chat (English / Urdu / Roman Urdu) and human handoff — with strict multi-tenant data isolation.

> **Demo tenant is synthetic seed data** ("Khyber Taste Restaurant") as required for the FYP; replace it with a real business only with permission.

---

## What it does

```text
Customer ⇄ WhatsApp Cloud API ⇄ FastAPI webhook
    → tenant identification → customer/conversation storage
    → LangGraph agent (intent → RAG | tools | LLM)
    → guardrails (no hallucinated facts/transactions)
    → WhatsApp reply → dashboard analytics
```

Key guarantees (spec §3, §56):

- The AI **never invents** prices, availability, or order status — facts come from the tenant's DB/RAG only.
- Actions happen only through **deterministic tools**; "order confirmed" replies require a successful `create_order()` DB transaction (enforced in guardrails).
- Tenant isolation is enforced in **every SQL query** (and verified by security tests), never only in prompts.
- Duplicate webhook deliveries are idempotent — no double orders.

## Features

| Area | Included |
|---|---|
| Multi-tenant SaaS | Registration → own business/tenant, JWT auth, owner/staff/platform-admin RBAC, plan limits & usage metering, mock checkout |
| WhatsApp | Cloud API webhook (GET verify + POST receive), HMAC signature check, mock mode for offline demos, outbound sender |
| AI agent | LangGraph graph, rule-based offline path **and** OpenAI-compatible tool-calling path, order/booking draft+confirmation flows, guardrails, human handoff |
| RAG | Sentence-aware chunking, pluggable embeddings (local-hash offline / OpenAI-compatible), tenant-scoped vector retrieval, document versioning, re-index |
| Dashboard | Overview analytics (charts), conversations inbox w/ staff takeover+reply, orders kanban-ish status flow, menu CRUD, bookings, knowledge base w/ retrieval tester, AI + WhatsApp + subscription settings |
| Voice/Vision | Modular pipeline stubs — voice messages are stored and flagged; plug an STT provider in `workers/tasks.py` (Pro plan feature) |
| Evaluation | Intent dataset (74 multilingual queries), RAG eval set, tool-calling eval set, `scripts/evaluate.py` with accuracy/macro-F1/hit@1 |

## Repository layout

```text
backend/app/
  agents/      graph.py nodes.py tools.py prompts.py classify.py nlu.py guardrails.py llm.py state.py
  rag/         chunking.py embeddings.py ingestion.py retrieval.py
  api/v1/      auth businesses menu orders bookings customers conversations knowledge analytics whatsapp billing admin
  services/    whatsapp_service.py notification_service.py
  workers/     tasks.py (webhook → agent pipeline, usage metering, plan limits)
  models/ schemas/ db/ core/ tests/
frontend/      Next.js 14 (App Router) + Tailwind + Recharts
data/          seed / synthetic_demo (labeled synthetic) / evaluation datasets
docker/        backend.Dockerfile frontend.Dockerfile
scripts (backend/scripts/): seed_demo.py simulate_whatsapp.py evaluate.py
```

## Quick start (local, no Docker, no API keys needed)

Everything installs inside this folder (`.venv` + `node_modules`), and `.env` sits at the project root.

```bash
# 1. Backend
python -m venv .venv
.venv\Scripts\pip install -r backend\requirements.txt
.venv\Scripts\python backend\scripts\seed_demo.py     # demo tenant + menu + knowledge base
.venv\Scripts\python -m uvicorn app.main:app --app-dir backend --port 8000

# 2. Frontend (second terminal)
cd frontend && npm install && npm run dev
# open http://localhost:3000  → login owner@demo.com / demo1234
```

### Demo the AI agent without WhatsApp

```bash
.venv\Scripts\python backend\scripts\simulate_whatsapp.py "what time do you open?"
.venv\Scripts\python backend\scripts\simulate_whatsapp.py --conversation   # full multi-turn order
```

### Run tests & evaluation

```bash
cd backend && ..\.venv\Scripts\python -m pytest app/tests -q     # 21 tests
.venv\Scripts\python backend\scripts\evaluate.py                 # intent + RAG metrics
```

## Environment variables

Copy `.env.example` → `.env` (a ready `.env` with safe dev defaults already exists at the root). Highlights:

```env
DATABASE_URL=sqlite:///./agenticwhats.db          # or postgresql+psycopg2://...
LLM_PROVIDER=mock          # mock = offline rule-based agent; openai = agentic LLM path
LLM_API_KEY=...            # any OpenAI-compatible endpoint (LLM_BASE_URL, LLM_MODEL)
EMBEDDING_PROVIDER=mock    # mock = local embeddings; openai = hosted
WHATSAPP_ACCESS_TOKEN=     # empty ⇒ mock mode (offline demo); set for live sending
WHATSAPP_VERIFY_TOKEN=agenticwhats-verify
WHATSAPP_APP_SECRET=       # set ⇒ webhook HMAC signature enforced
JWT_SECRET=change-me
```

## Going live with WhatsApp

1. Create a Meta app and add the **WhatsApp** product (Cloud API).
2. In the dashboard → *Settings → WhatsApp connection*, enter your **Phone Number ID**.
3. In the Meta dashboard set the webhook URL to `https://<your-domain>/api/webhooks/whatsapp` with the verify token from `.env`; subscribe to the `messages` field.
4. Put the permanent access token in `WHATSAPP_ACCESS_TOKEN` and the app secret in `WHATSAPP_APP_SECRET` (signature checks turn on automatically).
5. Switch `LLM_PROVIDER=openai` + `LLM_API_KEY` for the full LLM tool-calling agent (optional but recommended in production).

## Docker

```bash
docker compose up --build     # postgres + redis + backend :8000 + frontend :3000
```

## Security & privacy notes

- Passwords hashed (bcrypt), JWT auth, RBAC, tenant-scoped queries, webhook HMAC verification, upload type/size validation, audit logs, usage limits.
- Raw WhatsApp tokens are never stored or returned; secrets only via `.env`.
- All demo conversations/datasets are synthetic and labeled as such; no real customer data is included.

## Known limitations (honest scope)

- Local-hash embeddings are keyword-semantic — use `EMBEDDING_PROVIDER=openai` for production quality.
- SQLite is fine for dev/demo; use PostgreSQL (see docker-compose) in production. A pgvector migration for `knowledge_chunks` is the planned scale path.
- Voice/vision are stubbed at the pipeline level (message stored, agent sees a placeholder); wire STT/vision providers to enable them.
- Billing checkout is a mock plan switch — plug a payment provider for real subscriptions.
