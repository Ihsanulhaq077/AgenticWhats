# FYP Evaluation Guide

## Datasets (all synthetic / public — provenance labeled)

| File | Purpose | Size |
|---|---|---|
| `data/synthetic_demo/intent_dataset.csv` | Intent classification, 18 intents × en/roman_urdu/ur | 74 rows (manually written, labeled synthetic) |
| `data/evaluation/rag_eval_dataset.csv` | RAG retrieval against the demo tenant KB | 8 Q/A + expected source |
| `data/evaluation/toolcalling_eval_dataset.csv` | Tool selection correctness | 8 cases |

Public datasets recommended for extended study (not bundled): CLINC150, BANKING77, MultiWOZ, MASSIVE, SNIPS — see master spec §26 for license notes.

## Running the harness

```bash
./.venv/Scripts/python.exe backend/scripts/seed_demo.py   # once
./.venv/Scripts/python.exe backend/scripts/evaluate.py
```

Current results (rule-based baseline, mock embeddings):

```text
Intent classification : accuracy 0.824, macro-F1 0.812 (74 examples, 18 intents)
Language detection    : 0.986 (en vs ur script split)
RAG retrieval         : source hit@1 0.875, answer keyword coverage@3 0.875
```

## Baseline comparison plan (spec §48)

| System | Where |
|---|---|
| B1 Rule-based chatbot | `LLM_PROVIDER=mock` (this repo's offline path) |
| B2 LLM-only | Set `LLM_PROVIDER=openai`, disable tool schemas & RAG context in `agent_core` |
| B3 LLM+RAG | Keep RAG context, keep tools hidden |
| Proposed LLM+RAG+Agent+Tools | Full configuration (default with LLM key) |

Measure per configuration: intent accuracy, hallucination rate (facts not in KB), tool-selection accuracy (`toolcalling_eval_dataset.csv`), task completion (order/booking created in DB), escalation correctness, response latency. Log `tool_calls_log` per run (returned by `run_agent`) as the ground-truth trace.

## Research questions (spec §47)

1. Reduction of human support workload → handoff rate from `/api/analytics`.
2. RAG vs LLM-only hallucination rate → compare B2 vs B3 on `rag_eval_dataset.csv`.
3. Cross-language intent accuracy → slice `intent_dataset.csv` by `language`.
4. Tool-calling reliability → B4 vs B3 on `toolcalling_eval_dataset.csv`.
5. Tenant-specific retrieval effect → run RAG eval with/without `business_id` filter (isolation ablation).
