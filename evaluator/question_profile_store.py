from config import (
    QUESTION_PROFILE_BACKEND,
    QUESTION_PROFILE_DB_PATH,
    QUESTION_PROFILE_STORE_PATH,
)
from evaluator.question_profile_repository import (
    JsonQuestionProfileRepository,
    SqliteQuestionProfileRepository,
)


def _build_repository():
    if QUESTION_PROFILE_BACKEND == "json":
        return JsonQuestionProfileRepository(QUESTION_PROFILE_STORE_PATH)
    if QUESTION_PROFILE_BACKEND == "sqlite":
        return SqliteQuestionProfileRepository(
            db_path=QUESTION_PROFILE_DB_PATH,
            legacy_json_path=QUESTION_PROFILE_STORE_PATH,
        )
    raise ValueError(f"Unsupported question profile backend: {QUESTION_PROFILE_BACKEND}")


_REPOSITORY = _build_repository()


def upsert_question_profile(payload: dict) -> dict:
    return _REPOSITORY.upsert(payload)


def get_question_profile(question_id: str):
    return _REPOSITORY.get(question_id)


def list_question_profiles():
    return _REPOSITORY.list_all()
