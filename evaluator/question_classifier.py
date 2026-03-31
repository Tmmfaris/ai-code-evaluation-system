def classify_question(question, language):
    question_text = (question or "").lower()
    language = (language or "").lower()

    profile = {
        "language": language or "general",
        "category": "general",
        "task_type": "unknown",
        "risk": "medium",
        "markers": [],
    }

    def mark(category, task_type, risk, *markers):
        profile["category"] = category
        profile["task_type"] = task_type
        profile["risk"] = risk
        profile["markers"] = [marker for marker in markers if marker]
        return profile

    if any(token in question_text for token in ("read a file", "count number of lines", "count number of words", "csv", "json", "xml")):
        task = "parsing" if any(token in question_text for token in ("json", "xml", "csv")) else "file_io"
        return mark("io_parsing", task, "high", "file", "parsing")

    if any(token in question_text for token in ("create a class", "abstract class", "extends", "student", "employee", "shape", "circle", "stack using array")):
        return mark("oop_design", "class_design", "high", "class", "oop")

    if any(token in question_text for token in ("exception", "safely", "safe", "try/catch", "try/except")):
        return mark("error_handling", "safety", "high", "exception", "safety")

    if any(token in question_text for token in ("set", "map", "dictionary", "hashmap", "hashset", "stream")):
        return mark("collections", "required_technique", "high", "collections", "required_technique")

    if any(token in question_text for token in ("binary search", "sort", "top 2", "second largest", "minimum", "maximum", "min", "max")):
        return mark("arrays_search_sort", "search_sort", "medium", "arrays", "search_sort")

    if any(token in question_text for token in ("reverse", "palindrome", "vowel", "lowercase", "uppercase", "empty", "digits", "numeric", "anagram", "email")):
        return mark("strings", "string_processing", "low", "strings")

    if any(token in question_text for token in ("array", "list", "flatten", "common elements", "duplicates", "frequency", "sum of array", "average of array")):
        return mark("arrays_lists", "data_processing", "medium", "arrays", "lists")

    if any(token in question_text for token in ("factorial", "prime", "power of 2", "power of two", "positive", "even", "sum of digits", "add two numbers", "cube", "square")):
        return mark("basics_math", "basic_logic", "low", "math", "basics")

    if "method" in question_text or "function" in question_text:
        return mark("general_code", "function_logic", "medium", "general")

    return profile
