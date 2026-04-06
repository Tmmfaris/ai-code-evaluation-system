import atexit
import queue
import threading

from config import QUESTION_LEARNING_DB_PATH
from evaluator.question_learning_repository import SqliteQuestionLearningRepository


_REPOSITORY = SqliteQuestionLearningRepository(QUESTION_LEARNING_DB_PATH)
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


def save_learning_signal(payload: dict) -> dict:
    _SAVE_QUEUE.put(dict(payload))
    return payload


def list_recent_learning_signals(limit: int = 100):
    return _REPOSITORY.list_recent(limit=limit)
