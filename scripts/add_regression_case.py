import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REGRESSION_PATH = ROOT / "tests" / "regression_cases.json"


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python scripts/add_regression_case.py path/to/new_case.json")
        return 1

    new_case_path = Path(sys.argv[1]).resolve()
    payload = json.loads(new_case_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise SystemExit("New regression case must be a single JSON object.")

    required_keys = {
        "id",
        "student_id",
        "language",
        "question",
        "model_answer",
        "student_answer",
        "expected_min_score",
        "expected_max_score",
    }
    missing = sorted(required_keys - set(payload))
    if missing:
        raise SystemExit(f"Missing required keys: {', '.join(missing)}")

    cases = json.loads(REGRESSION_PATH.read_text(encoding="utf-8"))
    existing_ids = {item.get("id") for item in cases if isinstance(item, dict)}
    if payload["id"] in existing_ids:
        raise SystemExit(f"Regression case id already exists: {payload['id']}")

    cases.append(payload)
    cases.sort(key=lambda item: item.get("id", ""))
    REGRESSION_PATH.write_text(json.dumps(cases, indent=2) + "\n", encoding="utf-8")
    print(f"Added regression case: {payload['id']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
