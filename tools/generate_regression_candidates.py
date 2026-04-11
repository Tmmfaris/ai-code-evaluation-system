import argparse
import json
import os
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

from evaluator.evaluation_history_store import list_recent_evaluation_records
from llm.llm_engine import call_llm


def _slugify(text):
    text = (text or "").strip().lower()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return text.strip("_") or "case"


def _score_band(score):
    if score <= 5:
        return (0, 0)
    if score >= 95:
        return (100, 100)
    if score <= 25:
        return (0, min(30, score + 5))
    if score <= 60:
        return (max(0, score - 10), min(100, score + 10))
    return (max(0, score - 5), min(100, score + 5))


def _select_representative_records(records, per_group=3):
    grouped = defaultdict(list)
    for record in records:
        key = (
            (record.get("language") or "").strip().lower(),
            (record.get("question") or "").strip(),
            (record.get("model_answer") or "").strip(),
        )
        grouped[key].append(record)

    selected = []
    selected_keys = set()
    for group_records in grouped.values():
        group_records = sorted(group_records, key=lambda item: item.get("score", 0))
        if not group_records:
            continue
        for candidate in (group_records[0], group_records[-1]):
            key = (
                candidate.get("language"),
                candidate.get("question"),
                candidate.get("model_answer"),
                candidate.get("student_answer"),
                candidate.get("score"),
            )
            if key not in selected_keys:
                selected.append(candidate)
                selected_keys.add(key)
        if len(group_records) > 1:
            if len(group_records) > 2:
                mid = group_records[len(group_records) // 2]
                key = (
                    mid.get("language"),
                    mid.get("question"),
                    mid.get("model_answer"),
                    mid.get("student_answer"),
                    mid.get("score"),
                )
                if key not in selected_keys:
                    selected.append(mid)
                    selected_keys.add(key)
    return selected[: max(1, per_group * len(grouped))]


def _heuristic_cases(records, limit):
    cases = []
    seen = set()
    for record in records[:limit]:
        language = (record.get("language") or "").strip().lower()
        question = (record.get("question") or "").strip()
        model_answer = (record.get("model_answer") or "").strip()
        student_answer = (record.get("student_answer") or "").strip()
        score = int(record.get("score", 0) or 0)
        min_score, max_score = _score_band(score)
        base_id = _slugify(f"{language}_{question[:40]}")
        case_id = f"{base_id}_{score}"
        if case_id in seen:
            continue
        seen.add(case_id)
        cases.append(
            {
                "id": case_id,
                "student_id": f"auto-{base_id}",
                "language": language,
                "question": question,
                "model_answer": model_answer,
                "student_answer": student_answer,
                "expected_min_score": min_score,
                "expected_max_score": max_score,
            }
        )
    return cases


def _parse_json_array(text):
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    start = text.find("[")
    end = text.rfind("]")
    if start >= 0 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return None
    return None


def _llm_cases(records, limit):
    if not records:
        return []

    payload = [
        {
            "language": (r.get("language") or "").strip().lower(),
            "question": (r.get("question") or "").strip(),
            "model_answer": (r.get("model_answer") or "").strip(),
            "student_answer": (r.get("student_answer") or "").strip(),
            "score": int(r.get("score", 0) or 0),
            "feedback": (r.get("feedback") or "").strip(),
        }
        for r in records[:limit]
    ]

    prompt = (
        "You are helping build regression test cases for an evaluator.\n"
        "Return ONLY a JSON array of regression cases with fields:\n"
        "id, student_id, language, question, model_answer, student_answer, expected_min_score, expected_max_score.\n"
        "Use the provided score to set a tight expected range. Use exact 0 or 100 when appropriate.\n"
        "Do not include any extra keys or commentary.\n"
        "Here are evaluation records:\n"
        + json.dumps(payload, ensure_ascii=True)
    )

    raw = call_llm(prompt)
    parsed = _parse_json_array(raw)
    if not isinstance(parsed, list):
        return None
    cleaned = []
    for item in parsed:
        if not isinstance(item, dict):
            continue
        cleaned.append(
            {
                "id": str(item.get("id") or "").strip() or _slugify(item.get("question")),
                "student_id": str(item.get("student_id") or "").strip() or "auto-llm",
                "language": str(item.get("language") or "").strip().lower(),
                "question": str(item.get("question") or "").strip(),
                "model_answer": str(item.get("model_answer") or "").strip(),
                "student_answer": str(item.get("student_answer") or "").strip(),
                "expected_min_score": int(item.get("expected_min_score", 0) or 0),
                "expected_max_score": int(item.get("expected_max_score", 100) or 0),
            }
        )
    return cleaned


def main():
    parser = argparse.ArgumentParser(description="Generate draft regression cases using recent evaluation history.")
    parser.add_argument("--limit", type=int, default=30, help="Number of recent records to consider.")
    parser.add_argument("--out", default="tests/regression_candidates.json", help="Output JSON path.")
    parser.add_argument("--heuristic-only", action="store_true", help="Skip LLM and use heuristic scoring.")
    args = parser.parse_args()

    records = list_recent_evaluation_records(limit=max(1, args.limit))
    selected = _select_representative_records(records, per_group=3)

    cases = None
    if not args.heuristic_only:
        cases = _llm_cases(selected, limit=min(len(selected), args.limit))
    if not cases:
        cases = _heuristic_cases(selected, limit=min(len(selected), args.limit))

    output_payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "evaluation_history",
        "count": len(cases),
        "cases": cases,
    }

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as handle:
        json.dump(output_payload, handle, indent=2, ensure_ascii=True)

    print(f"Wrote {len(cases)} regression candidates to {args.out}")
    print("Review and copy selected cases into tests/regression_cases.json")


if __name__ == "__main__":
    main()
