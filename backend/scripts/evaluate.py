"""Evaluation harness (spec §23): measures the rule-based NLU baseline and
RAG retrieval against the datasets in data/.

Usage:
  ./.venv/Scripts/python.exe backend/scripts/evaluate.py
  (run seed_demo.py first so the demo tenant + knowledge base exist)
"""

import csv
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.db.session import SessionLocal  # noqa: E402
from app.models.entities import Business  # noqa: E402
from app.agents.classify import classify  # noqa: E402
from app.rag.retrieval import search_knowledge  # noqa: E402


def intent_eval() -> dict:
    dataset = ROOT / "data" / "synthetic_demo" / "intent_dataset.csv"
    rows = list(csv.DictReader(dataset.open(encoding="utf-8")))
    per_intent = Counter()
    hits = Counter()
    correct = 0
    lang_correct = 0

    def norm_lang(lang: str, text: str) -> str:
        # The dataset marks Roman Urdu messages variously; the detector's
        # en/ur/roman_urdu is compared leniently for script-only splits.
        detected = classify(text)["language"]
        if lang == "ur":
            return 1 if detected == "ur" else 0
        return 1 if detected in {"en", "roman_urdu"} else 0

    for row in rows:
        result = classify(row["text"])
        ok = result["intent"] == row["intent"]
        correct += ok
        lang_correct += norm_lang(row["language"], row["text"])
        per_intent[row["intent"]] += 1
        hits[row["intent"]] += ok

    accuracy = correct / len(rows)
    # Macro F1
    f1s = []
    for intent, total in per_intent.items():
        tp = hits[intent]
        fp = sum(h for i, h in hits.items() if i != intent and i == intent)  # placeholder
        predicted = sum(1 for r in rows if classify(r["text"])["intent"] == intent)
        precision = tp / predicted if predicted else 0.0
        recall = tp / total if total else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
        f1s.append(f1)
    macro_f1 = sum(f1s) / len(f1s)

    return {
        "n": len(rows),
        "intent_accuracy": round(accuracy, 3),
        "intent_macro_f1": round(macro_f1, 3),
        "language_accuracy_en_vs_ur": round(lang_correct / len(rows), 3),
    }


def rag_eval() -> dict:
    dataset = ROOT / "data" / "evaluation" / "rag_eval_dataset.csv"
    rows = list(csv.DictReader(dataset.open(encoding="utf-8")))
    db = SessionLocal()
    try:
        business = db.query(Business).filter(Business.slug == "khyber-taste").first()
        if business is None:
            return {"error": "run seed_demo.py first"}
        hits_at_1 = 0
        keyword_hits = 0
        for row in rows:
            results = search_knowledge(db, business.id, row["question"], k=3)
            if results:
                top_source = results[0]["metadata"].get("source", "")
                if row["expected_source"].lower() in top_source.lower():
                    hits_at_1 += 1
                # Groundedness proxy: expected answer keyword overlap in top-3
                snippet = " ".join(r["content"].lower() for r in results)
                key_words = [w for w in row["expected_answer"].lower().split() if len(w) > 3][:5]
                if key_words and sum(w in snippet for w in key_words) / len(key_words) >= 0.6:
                    keyword_hits += 1
        return {
            "n": len(rows),
            "source_hit_at_1": round(hits_at_1 / len(rows), 3),
            "answer_keyword_coverage_top3": round(keyword_hits / len(rows), 3),
        }
    finally:
        db.close()


if __name__ == "__main__":
    print("== Intent classification (rule-based baseline, synthetic dataset) ==")
    for k, v in intent_eval().items():
        print(f"  {k}: {v}")
    print("== RAG retrieval (demo tenant knowledge base) ==")
    for k, v in rag_eval().items():
        print(f"  {k}: {v}")
