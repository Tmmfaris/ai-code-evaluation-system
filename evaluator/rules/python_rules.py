from . import shared


def analyze_python_submission_rules(question, student_answer):
    return shared.analyze_submission_rules(question, student_answer, "python")
