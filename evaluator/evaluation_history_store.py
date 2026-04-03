import atexit
import queue
import threading

from config import EVALUATION_HISTORY_BACKEND, EVALUATION_HISTORY_DB_PATH
from evaluator.evaluation_history_repository import SqliteEvaluationHistoryRepository


def _build_repository():
    if EVALUATION_HISTORY_BACKEND == "sqlite":
        return SqliteEvaluationHistoryRepository(EVALUATION_HISTORY_DB_PATH)
    raise ValueError(f"Unsupported evaluation history backend: {EVALUATION_HISTORY_BACKEND}")


_REPOSITORY = _build_repository()
_SAVE_QUEUE = queue.Queue()
_SAVE_STOP = object()


def _save_worker():
    while True:
        payload = _SAVE_QUEUE.get()
        if payload is _SAVE_STOP:
            _SAVE_QUEUE.task_done()
            break
        try:
            _REPOSITORY.save(payload)
        finally:
            _SAVE_QUEUE.task_done()


_SAVE_THREAD = threading.Thread(target=_save_worker, daemon=True)
_SAVE_THREAD.start()


def _shutdown_save_worker():
    try:
        _SAVE_QUEUE.put(_SAVE_STOP)
        _SAVE_QUEUE.join()
    except Exception:
        pass


atexit.register(_shutdown_save_worker)


def save_evaluation_record(payload: dict) -> dict:
    _SAVE_QUEUE.put(dict(payload))
    return payload


def list_recent_evaluation_records(limit: int = 100):
    return _REPOSITORY.list_recent(limit=limit)


def list_student_evaluation_records(student_id: str, limit: int = 100):
    return _REPOSITORY.list_for_student(student_id=student_id, limit=limit)
