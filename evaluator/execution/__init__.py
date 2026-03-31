from .java_execution import analyze_java_execution
from .python_execution import analyze_python_execution


def analyze_execution(question, sample_answer, student_answer, language):
    language = (language or "").lower()

    if language == "python":
        return analyze_python_execution(question, sample_answer, student_answer)
    if language == "java":
        return analyze_java_execution(question, sample_answer, student_answer)
    return None
