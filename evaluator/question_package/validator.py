from evaluator.question_rule_generator import finalize_question_profile


def validate_question_package(payload):
    return finalize_question_profile(payload)
