from evaluator.question_rule_generator import enrich_question_profile


def generate_question_package(payload, force_llm=False):
    return enrich_question_profile(payload, force_llm=force_llm)
