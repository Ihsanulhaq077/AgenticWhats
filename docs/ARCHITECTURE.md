# Architecture

## System overview

```text
                         +----------------------+
                         |      Customers       |
                         +----------+-----------+
                                    v
                         WhatsApp Business Platform (Cloud API)
                                    v
                    FastAPI  POST /api/webhooks/whatsapp
                    (HMAC signature check → fast 200 + background task)
                                    v
              Tenant resolution (whatsapp_accounts.phone_number_id → business)
                                    v
              Customer + Conversation upsert (unique per business+number)
                                    v
        Message persisted (idempotency key = provider_message_id) → queue/background
                                    v
        Plan limit check (subscriptions + usage_records)
                                    v
                            LangGraph agent
        START → classify → route → {agent_core | order | booking | status |
                 cancel | knowledge | greeting | handoff | fallback} → guardrails → END
                                    v
        Deterministic tools (tenant-scoped SQL): menu, orders, bookings,
        business info, knowledge retrieval, transfer_to_human
                                    v
        Outbound WhatsApp send (live or mock) + message stored + usage metering
```

## Two agent paths, one tool layer

- **Rule-based path (default, offline)** — `agents/nodes.py`. Deterministic intent router + NLU extraction (`classify.py`, `nlu.py`). Doubles as Baseline 1 for the FYP evaluation and guarantees the demo works with zero API keys.
- **LLM agentic path** — `agents/llm.py` + `agent_core` node. Any OpenAI-compatible endpoint; the LLM picks tools from `TOOL_SCHEMAS`, the server executes them (`tools.py`), results go back to the LLM for the final grounded reply (max 4 loop iterations).

Both paths pass through the **guardrails node**: secret-leak blocking, unbacked-transaction-claim rewriting, length capping.

## Multi-tenant isolation

- Every tenant-owned table carries `business_id` with FK + index.
- Dashboard requests resolve the tenant via JWT → `business_users` membership (`api/deps.get_current_business`); admins must pass `X-Business-Id` explicitly.
- Agent tools take a `ToolContext` bound to one business; all queries filter on it.
- RAG retrieval filters `knowledge_chunks.business_id` **in SQL**, not in the prompt.
- A `phone_number_id` can be connected to at most one business (unique + conflict check).

## RAG pipeline

`documents → sentence-aware chunking (700 chars, overlap) → embeddings (local-hash or OpenAI-compatible) → knowledge_chunks (JSON vectors; pgvector migration path) → cosine retrieval → top-k context injected into the tenant-aware system prompt or returned by the search_knowledge_base tool`. Re-ingesting the same title bumps the version and replaces chunks.

## Reliability

- Webhook returns 200 immediately; processing runs as a background task (Celery swap-in point for production).
- Idempotency: inbound `provider_message_id` is unique-checked before processing.
- Agent failures degrade to a safe apology + auto-escalation, never crash the pipeline.
- Plan limits gate AI usage per billing period.
