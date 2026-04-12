from copy import deepcopy
from functools import lru_cache

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
    profile = _REPOSITORY.upsert(payload)
    _get_question_profile_cached.cache_clear()
    _list_question_profiles_cached.cache_clear()
    return profile


@lru_cache(maxsize=512)
def _get_question_profile_cached(question_signature: str):
    return _REPOSITORY.get(question_signature)


def get_question_profile(question_signature: str):
    profile = _get_question_profile_cached(question_signature)
    return deepcopy(profile) if profile else profile


def get_question_profile_fresh(question_signature: str):
    if not question_signature:
        return None
    profile = _REPOSITORY.get(question_signature)
    _get_question_profile_cached.cache_clear()
    _list_question_profiles_cached.cache_clear()
    return deepcopy(profile) if profile else profile


@lru_cache(maxsize=1)
def _list_question_profiles_cached():
    return tuple(_REPOSITORY.list_all())


def list_question_profiles():
    return deepcopy(list(_list_question_profiles_cached()))
