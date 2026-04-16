import os
import uuid
from pathlib import Path


# Ensure tests run against isolated stores so results are deterministic and not
# affected by whatever is already present under ./data from local development.
_BASE = Path(__file__).resolve().parent / ".tmp_store"
_BASE.mkdir(parents=True, exist_ok=True)
_RUN_ID = uuid.uuid4().hex

os.environ.setdefault("AI_EVAL_QUESTION_PROFILE_BACKEND", "sqlite")
os.environ.setdefault("AI_EVAL_QUESTION_PROFILE_STORE_PATH", str(_BASE / f"question_profiles_{_RUN_ID}.json"))
os.environ.setdefault("AI_EVAL_QUESTION_PROFILE_DB_PATH", str(_BASE / f"question_profiles_{_RUN_ID}.db"))
os.environ.setdefault("AI_EVAL_EVALUATION_HISTORY_DB_PATH", str(_BASE / f"evaluation_history_{_RUN_ID}.db"))
os.environ.setdefault("AI_EVAL_QUESTION_LEARNING_DB_PATH", str(_BASE / f"question_learning_{_RUN_ID}.db"))

