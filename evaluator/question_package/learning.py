from evaluator.question_learning_store import list_recent_learning_signals


def list_question_package_learning(limit=100):
    return list_recent_learning_signals(limit=limit)
