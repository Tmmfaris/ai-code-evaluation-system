from evaluator.question_profile_store import list_question_profiles, upsert_question_profile
from evaluator.question_package.approvals import (
    approve_question_package,
    get_question_package,
    list_pending_approval_packages,
)
from evaluator.question_package.generator import generate_question_package
from evaluator.question_package.reuser import reuse_existing_package_content
from evaluator.question_package.validator import validate_question_package


def prepare_question_profiles(question_payloads):
    existing_profiles = list_question_profiles()
    saved_profiles = []

    for payload in question_payloads:
        prepared = reuse_existing_package_content(payload, existing_profiles)
        prepared = generate_question_package(prepared)
        prepared = validate_question_package(prepared)
        stored = upsert_question_profile(prepared)
        saved_profiles.append(stored)
        existing_profiles.append(stored)

    return saved_profiles


def approve_registered_question(question_id, approved_by="faculty"):
    return approve_question_package(question_id, approved_by=approved_by)


def get_registered_question_package(question_id):
    return get_question_package(question_id)


def list_pending_question_packages():
    return list_pending_approval_packages()
