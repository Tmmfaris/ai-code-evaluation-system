from evaluator.question_profile_store import get_question_profile, list_question_profiles, upsert_question_profile
from evaluator.question_package.validator import validate_question_package


def approve_question_package(question_signature, approved_by="faculty", edits=None):
    profile = get_question_profile(question_signature)
    if not profile:
        return None

    if edits:
        profile = dict(profile)
        profile.update(edits)

    profile["approval_status"] = "approved"
    profile["approved_by"] = approved_by
    prepared = validate_question_package(profile)
    prepared["approval_status"] = "approved"
    prepared["approved_by"] = approved_by
    prepared["review_required"] = False
    return upsert_question_profile(prepared)


def get_question_package(question_signature):
    return get_question_profile(question_signature)


def list_pending_approval_packages():
    pending = []
    for profile in list_question_profiles():
        if (profile.get("approval_status") or "pending").strip().lower() != "approved":
            pending.append(profile)
    return pending
