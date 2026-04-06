from evaluator.question_rule_generator import merge_with_existing_profiles


def reuse_existing_package_content(payload, existing_profiles):
    return merge_with_existing_profiles(payload, existing_profiles)
