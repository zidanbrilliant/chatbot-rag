"""Evaluation runner — runs cases.yaml against intent classifier.

Ponytail: skip LLM calls (need live DB + Ollama). Test the intent
classifier output only — that's the deterministic, testable part.
Scoring: per-case pass/fail based on intent + refusal + keywords.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import yaml

from app.services.general_intent import (
    OUT_OF_SCOPE_MESSAGE,
    classify_intent,
)
from app.services.strict_mode import get_casual_response


def load_cases(path: Path) -> list[dict]:
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data


def run_case(case: dict) -> dict:
    """Run single case through intent classifier only (no LLM)."""
    query = case.get("query", "")
    expected_intent = case.get("intent", "rag_question")
    expect_refuse = case.get("expect_refuse", False)
    expect_keywords = case.get("expect_keywords", [])

    result = classify_intent(query)

    passed = True
    reasons = []

    if result.intent != expected_intent:
        passed = False
        reasons.append(f"intent mismatch: expected={expected_intent}, got={result.intent}")

    if expect_refuse:
        reply = OUT_OF_SCOPE_MESSAGE.lower()
        for kw in expect_keywords:
            if kw.lower() not in reply:
                passed = False
                reasons.append(f"expected keyword '{kw}' not in refuse message")
    elif result.intent == "casual_greeting":
        reply = (result.casual_response or "").lower()
        for kw in expect_keywords:
            if kw.lower() not in reply:
                passed = False
                reasons.append(f"expected keyword '{kw}' not in casual response")

    return {
        "id": case.get("id", "?"),
        "query": query,
        "expected_intent": expected_intent,
        "actual_intent": result.intent,
        "passed": passed,
        "reasons": reasons,
        "confidence": result.confidence,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="RAG evaluation runner (intent-only)")
    parser.add_argument("--cases", default="evals/cases.yaml", help="Path to cases YAML")
    parser.add_argument("--json", action="store_true", help="JSON output")
    args = parser.parse_args()

    cases_path = Path(args.cases)
    if not cases_path.exists():
        print(f"ERROR: cases file not found: {cases_path}", file=sys.stderr)
        return 1

    cases = load_cases(cases_path)

    start = time.time()
    results = [run_case(c) for c in cases]
    elapsed = time.time() - start

    passed = sum(1 for r in results if r["passed"])
    total = len(results)
    pass_rate = passed / total if total else 0

    # Per-intent breakdown
    by_intent: dict[str, dict] = {}
    for r in results:
        e = r["expected_intent"]
        if e not in by_intent:
            by_intent[e] = {"total": 0, "passed": 0}
        by_intent[e]["total"] += 1
        if r["passed"]:
            by_intent[e]["passed"] += 1

    if args.json:
        output = {
            "summary": {
                "passed": passed,
                "total": total,
                "pass_rate": round(pass_rate, 3),
                "elapsed_s": round(elapsed, 3),
                "by_intent": {k: {**v, "rate": round(v["passed"] / v["total"], 3)} for k, v in by_intent.items()},
            },
            "results": results,
        }
        print(json.dumps(output, indent=2, ensure_ascii=False))
    else:
        print(f"=== Evaluation Results ===")
        print(f"Passed: {passed}/{total} ({pass_rate * 100:.1f}%)")
        print(f"Time: {elapsed:.2f}s")
        print()
        print("By intent:")
        for intent, stats in sorted(by_intent.items()):
            rate = stats["passed"] / stats["total"] if stats["total"] else 0
            print(f"  {intent:20} {stats['passed']}/{stats['total']} ({rate * 100:.0f}%)")
        print()
        failed = [r for r in results if not r["passed"]]
        if failed:
            print(f"=== {len(failed)} Failed ===")
            for r in failed:
                print(f"  [{r['id']}] expected={r['expected_intent']} got={r['actual_intent']}")
                for reason in r["reasons"]:
                    print(f"    - {reason}")

    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
