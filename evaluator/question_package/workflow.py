from evaluator.question_profile_store import list_question_profiles, upsert_question_profile
from evaluator.question_package.approvals import (
    approve_question_package,
    get_question_package,
    list_pending_approval_packages,
)
from evaluator.question_package.generator import generate_question_package
from evaluator.question_package.reuser import reuse_existing_package_content
from evaluator.question_package.validator import validate_question_package
from config import QUESTION_REGISTER_MAX_ATTEMPTS


def _has_placeholder_tests(package):
    test_sets = (package or {}).get("test_sets") or {}
    all_tests = list(test_sets.get("positive") or []) + list(test_sets.get("negative") or [])
    for item in all_tests:
        description = (item or {}).get("description") or ""
        if isinstance(description, str) and "faculty model answer baseline" in description.lower():
            return True
    return False


def _has_fallback_feedback(package):
    patterns = (package or {}).get("incorrect_patterns") or []
    for item in patterns:
        feedback = (item or {}).get("feedback") or ""
        lowered = feedback.lower()
        if ("safe fallback" in lowered and "primary review" in lowered) or (
            "retry the evaluation" in lowered and "rule-based checks" in lowered
        ):
            return True
    return False


def _candidate_rank(package):
    status = (package or {}).get("package_status") or ""
    status = status.strip().lower()
    status_rank = {"live": 3, "validated": 2, "generated": 1, "draft": 0}.get(status, 0)
    confidence = float((package or {}).get("package_confidence", 0.0) or 0.0)
    review_required = bool((package or {}).get("review_required", True))
    test_count = int((package or {}).get("positive_test_count", 0) or 0) + int((package or {}).get("negative_test_count", 0) or 0)
    template_family = ((package or {}).get("template_family") or "").strip().lower()
    is_generic_family = template_family.endswith("::generic") or template_family == "python::generic"
    return (
        status_rank,
        0 if review_required else 1,
        confidence,
        0 if is_generic_family else 1,
        0 if _has_placeholder_tests(package) else 1,
        0 if _has_fallback_feedback(package) else 1,
        test_count,
    )


def _is_fully_correct(package):
    status = (package or {}).get("package_status") or ""
    status = status.strip().lower()
    confidence = float((package or {}).get("package_confidence", 0.0) or 0.0)
    review_required = bool((package or {}).get("review_required", True))
    template_family = ((package or {}).get("template_family") or "").strip().lower()
    is_generic_family = template_family.endswith("::generic") or template_family == "python::generic"

    return (
        status in {"validated", "live"}
        and not review_required
        and confidence >= 0.999
        and not is_generic_family
        and not _has_placeholder_tests(package)
        and not _has_fallback_feedback(package)
    )


def prepare_question_profiles(question_payloads, force_llm=False, max_attempts=None):
    existing_profiles = list_question_profiles()
    saved_profiles = []

    for payload in question_payloads:
        prepared_base = reuse_existing_package_content(payload, existing_profiles)

        attempts = int(max_attempts or (QUESTION_REGISTER_MAX_ATTEMPTS if force_llm else 1) or 1)
        attempts = max(1, attempts)
        best = None
        for _ in range(attempts):
            candidate = generate_question_package(dict(prepared_base), force_llm=force_llm)
            candidate = validate_question_package(candidate)
            if best is None or _candidate_rank(candidate) > _candidate_rank(best):
                best = candidate
            if _is_fully_correct(candidate):
                best = candidate
                break

        stored = upsert_question_profile(best)
        saved_profiles.append(stored)
        existing_profiles.append(stored)

    return saved_profiles


def approve_registered_question(question_id, approved_by="faculty", edits=None):
    return approve_question_package(question_id, approved_by=approved_by, edits=edits)


def get_registered_question_package(question_id):
    return get_question_package(question_id)


def list_pending_question_packages():
    return list_pending_approval_packages()
