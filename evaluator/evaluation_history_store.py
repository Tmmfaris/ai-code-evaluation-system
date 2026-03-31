from config import EVALUATION_HISTORY_BACKEND, EVALUATION_HISTORY_DB_PATH
from evaluator.evaluation_history_repository import SqliteEvaluationHistoryRepository


def _build_repository():
    if EVALUATION_HISTORY_BACKEND == "sqlite":
        return SqliteEvaluationHistoryRepository(EVALUATION_HISTORY_DB_PATH)
    raise ValueError(f"Unsupported evaluation history backend: {EVALUATION_HISTORY_BACKEND}")


_REPOSITORY = _build_repository()


def save_evaluation_record(payload: dict) -> dict:
    return _REPOSITORY.save(payload)


def list_recent_evaluation_records(limit: int = 100):
    return _REPOSITORY.list_recent(limit=limit)


def list_student_evaluation_records(student_id: str, limit: int = 100):
    return _REPOSITORY.list_for_student(student_id=student_id, limit=limit)
