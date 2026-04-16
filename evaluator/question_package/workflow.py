from evaluator.question_profile_store import list_question_profiles, upsert_question_profile
from evaluator.question_package.approvals import (
    approve_question_package,
    get_question_package,
    list_pending_approval_packages,
)
from evaluator.question_package.generator import generate_question_package
from evaluator.question_package.reuser import reuse_existing_package_content
from evaluator.question_package.validator import validate_question_package
from config import (
    QUESTION_REGISTER_HARD_MAX_ATTEMPTS,
    QUESTION_REGISTER_LLM_MAX_ATTEMPTS,
    QUESTION_REGISTER_MAX_ATTEMPTS,
    REQUIRE_PACKAGE_COVERAGE_FOR_REGISTRATION,
    REGISTER_REQUIRE_LLM_ASSISTANCE,
    REGISTER_STRICT_VALIDATE,
    REGISTER_STRICT_MIN_CONFIDENCE,
)


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


def _is_internal_probe_question(package):
    lowered = ((package or {}).get("question") or "").strip().lower()
    internal_markers = (
        "guardrail probe",
        "scoring fallback probe",
        "llm repair package",
        "fenced llm json",
        "fallback not package",
    )
    return any(marker in lowered for marker in internal_markers)


def _has_required_case_coverage(package):
    template_family = ((package or {}).get("template_family") or "").strip().lower()
    test_sets = (package or {}).get("test_sets") or {}
    positives = [item for item in (test_sets.get("positive") or []) if isinstance(item, dict)]
    negatives = [item for item in (test_sets.get("negative") or []) if isinstance(item, dict)]
    required_positive = [item for item in positives if item.get("required")]
    required_negative = [item for item in negatives if item.get("required")]
    incorrect_patterns = [item for item in ((package or {}).get("incorrect_patterns") or []) if isinstance(item, dict)]
    accepted_solutions = [item for item in ((package or {}).get("accepted_solutions") or []) if isinstance(item, str) and item.strip()]
    if template_family == "python::model_answer_derived":
        return (
            len(positives) >= 2
            and len(required_positive) >= 1
            and len(incorrect_patterns) >= 2
            and len(accepted_solutions) >= 1
        )
    return (
        len(positives) >= 2
        and len(negatives) >= 1
        and len(required_positive) >= 1
        and len(required_negative) >= 1
        and len(incorrect_patterns) >= 2
        and len(accepted_solutions) >= 1
    )


def _candidate_rank(package):
    status = (package or {}).get("package_status") or ""
    status = status.strip().lower()
    status_rank = {"live": 3, "validated": 2, "generated": 1, "draft": 0}.get(status, 0)
    confidence = float((package or {}).get("package_confidence", 0.0) or 0.0)
    review_required = bool((package or {}).get("review_required", True))
    test_count = int((package or {}).get("positive_test_count", 0) or 0) + int((package or {}).get("negative_test_count", 0) or 0)
    template_family = ((package or {}).get("template_family") or "").strip().lower()
    is_generic_family = template_family.endswith("::generic") or template_family == "python::generic"
    generation_sources = (package or {}).get("generation_sources") or []
    llm_assisted = bool((package or {}).get("llm_assisted")) or any(
        isinstance(item, str) and item.strip().lower().startswith("llm")
        for item in generation_sources
    )
    return (
        status_rank,
        0 if review_required else 1,
        confidence,
        1 if llm_assisted else 0,
        0 if is_generic_family else 1,
        0 if _has_placeholder_tests(package) else 1,
        0 if _has_fallback_feedback(package) else 1,
        test_count,
    )


def _has_llm_assistance(package):
    generation_sources = (package or {}).get("generation_sources") or []
    return bool((package or {}).get("llm_assisted")) or any(
        isinstance(item, str) and item.strip().lower().startswith("llm")
        for item in generation_sources
    )


def _mark_missing_llm_assistance(package):
    marked = dict(package or {})
    sources = [
        item
        for item in (marked.get("generation_sources") or [])
        if isinstance(item, str) and item.strip()
    ]
    marked["generation_sources"] = sources
    marked["llm_assisted"] = False
    marked["package_status"] = "generated"
    marked["package_confidence"] = min(float(marked.get("package_confidence", 0.0) or 0.0), 0.89)
    marked["review_required"] = True
    marked["exam_ready"] = False
    marked["package_summary"] = (
        "GGUF assistance is required for registration, but no usable LLM-generated package content was produced."
    )
    marked["llm_requirement_waived"] = False
    return marked


def _can_waive_llm_requirement(package):
    template_family = ((package or {}).get("template_family") or "").strip().lower()
    if not template_family or template_family == "python::model_answer_derived":
        return False
    if _is_internal_probe_question(package):
        return False
    if template_family.endswith("::generic") or template_family == "python::generic":
        return False
    return _is_fully_correct(package) and _has_required_case_coverage(package)


def _enforce_llm_requirement(package, force_llm=False):
    if force_llm and REGISTER_REQUIRE_LLM_ASSISTANCE and not _has_llm_assistance(package):
        if _can_waive_llm_requirement(package):
            waived = dict(package or {})
            waived["llm_requirement_waived"] = True
            return waived
        return _mark_missing_llm_assistance(package)
    return package


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


def _is_register_ready(package):
    if not REGISTER_STRICT_VALIDATE:
        return _is_fully_correct(package)
    status = (package or {}).get("package_status") or ""
    status = status.strip().lower()
    confidence = float((package or {}).get("package_confidence", 0.0) or 0.0)
    review_required = bool((package or {}).get("review_required", True))
    template_family = ((package or {}).get("template_family") or "").strip().lower()
    is_generic_family = template_family.endswith("::generic") or template_family == "python::generic"
    summary = ((package or {}).get("package_summary") or "").lower()
    return (
        status in {"validated", "live"}
        and not review_required
        and confidence >= float(REGISTER_STRICT_MIN_CONFIDENCE or 0.9)
        and (not REGISTER_REQUIRE_LLM_ASSISTANCE or _has_llm_assistance(package) or bool((package or {}).get("llm_requirement_waived")))
        and not is_generic_family
        and not _has_placeholder_tests(package)
        and not _has_fallback_feedback(package)
        and (not REQUIRE_PACKAGE_COVERAGE_FOR_REGISTRATION or _has_required_case_coverage(package))
        and "review is recommended" not in summary
    )


def _has_non_string_test_io(package):
    test_sets = (package or {}).get("test_sets") or {}
    for bucket in ("positive", "negative"):
        for item in test_sets.get(bucket) or []:
            if not isinstance(item, dict):
                return True
            if not isinstance(item.get("input"), str):
                return True
            if not isinstance(item.get("expected_output"), str):
                return True
    return False


def _has_redundant_oracle_positives(package):
    test_sets = (package or {}).get("test_sets") or {}
    positives = [item for item in (test_sets.get("positive") or []) if isinstance(item, dict)]
    if not positives:
        return False
    handcrafted = []
    oracle = []
    for item in positives:
        description = ((item.get("description") or "") if isinstance(item, dict) else "").strip().lower()
        if "auto-generated deterministic oracle test" in description:
            oracle.append(item)
        else:
            handcrafted.append(item)
    if not handcrafted:
        return False
    allowed_positive_count = max(3, len(handcrafted))
    return len(positives) > allowed_positive_count and len(oracle) > 0


def _should_auto_refresh(package):
    return bool(
        package
        and (
            not _is_fully_correct(package)
            or _has_non_string_test_io(package)
            or _has_redundant_oracle_positives(package)
        )
    )


def _refresh_pending_package(profile, force_llm=False):
    if not profile:
        return None
    approval_status = (profile.get("approval_status") or "pending").strip().lower()
    if approval_status == "approved":
        return profile
    if not force_llm and not _should_auto_refresh(profile):
        return profile
    refreshed = prepare_question_profiles([dict(profile)], force_llm=True, max_attempts=1)
    return refreshed[0] if refreshed else profile


def _generate_best_profile(prepared_base, force_llm=False, attempts=1):
    attempts = max(1, int(attempts or 1))
    best = None
    for _ in range(attempts):
        candidate = generate_question_package(dict(prepared_base), force_llm=force_llm)
        candidate = validate_question_package(candidate)
        if best is None or _candidate_rank(candidate) > _candidate_rank(best):
            best = candidate
        candidate_ready = _is_register_ready(candidate)
        if candidate_ready:
            best = candidate
            if not (force_llm and REGISTER_REQUIRE_LLM_ASSISTANCE and not _has_llm_assistance(candidate)):
                break
        if force_llm:
            repair_context = candidate.get("package_summary") or candidate.get("package_status") or ""
            repair = generate_question_package(
                dict(prepared_base),
                force_llm=True,
                repair_context=str(repair_context),
            )
            repair = validate_question_package(repair)
            if _candidate_rank(repair) > _candidate_rank(best):
                best = repair
            repair_ready = _is_register_ready(repair)
            if repair_ready:
                best = repair
                if not (REGISTER_REQUIRE_LLM_ASSISTANCE and not _has_llm_assistance(repair)):
                    break
        if force_llm and best:
            prepared_base = dict(best)
    return best


def prepare_question_profiles(question_payloads, force_llm=False, max_attempts=None):
    existing_profiles = list_question_profiles()
    saved_profiles = []

    for payload in question_payloads:
        prepared_base = reuse_existing_package_content(payload, existing_profiles)

        attempts = int(max_attempts or (QUESTION_REGISTER_LLM_MAX_ATTEMPTS if force_llm else 1) or 1)
        best = _generate_best_profile(prepared_base, force_llm=force_llm, attempts=attempts)
        best = _enforce_llm_requirement(best, force_llm=force_llm)

        stored = upsert_question_profile(best)
        saved_profiles.append(stored)
        existing_profiles.append(stored)

    return saved_profiles


def prepare_question_profiles_until_correct(question_payloads, force_llm=False, hard_max_attempts=None):
    existing_profiles = list_question_profiles()
    saved_profiles = []

    for payload in question_payloads:
        prepared_base = reuse_existing_package_content(payload, existing_profiles)
        if force_llm:
            attempts = int(hard_max_attempts or QUESTION_REGISTER_LLM_MAX_ATTEMPTS or 1)
            attempts = min(attempts, int(QUESTION_REGISTER_LLM_MAX_ATTEMPTS or 1))
        else:
            attempts = int(hard_max_attempts or QUESTION_REGISTER_HARD_MAX_ATTEMPTS or QUESTION_REGISTER_MAX_ATTEMPTS or 1)
            attempts = max(int(QUESTION_REGISTER_MAX_ATTEMPTS or 1), attempts)
        best = _generate_best_profile(prepared_base, force_llm=force_llm, attempts=attempts)
        best = _enforce_llm_requirement(best, force_llm=force_llm)

        stored = upsert_question_profile(best)
        saved_profiles.append(stored)
        existing_profiles.append(stored)

    return saved_profiles


def approve_registered_question(question_signature, approved_by="faculty", edits=None):
    return approve_question_package(question_signature, approved_by=approved_by, edits=edits)


def get_registered_question_package(question_signature, force_llm=False):
    profile = get_question_package(question_signature)
    return _refresh_pending_package(profile, force_llm=force_llm)


def list_pending_question_packages(force_llm=False):
    return [_refresh_pending_package(item, force_llm=force_llm) for item in list_pending_approval_packages()]


def refresh_pending_question_packages(force_llm=True):
    refreshed = []
    for item in list_pending_approval_packages():
        updated = _refresh_pending_package(item, force_llm=force_llm)
        if updated:
            refreshed.append(updated)
    return refreshed
