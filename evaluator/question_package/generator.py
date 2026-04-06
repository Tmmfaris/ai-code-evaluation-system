from evaluator.question_rule_generator import enrich_question_profile


def generate_question_package(payload):
    return enrich_question_profile(payload)
