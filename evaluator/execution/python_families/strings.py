def _contains(question_text, *parts):
    return all(part in (question_text or "") for part in parts)


def evaluate_string_family(question, question_text, families, normalized_student, student_answer):
    if _contains(question_text, "add", "two", "numbers") and "returna" in normalized_student and "returna+b" not in normalized_student:
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "The function returns only one input value instead of adding the two numbers.",
            "suggestion": "Return the sum of both inputs, such as a + b.",
        }

    if _contains(question_text, "add", "two", "numbers") and "returnsum([a,b])" in normalized_student:
        return {
            "result_type": "full_pass",
            "correctness_min": 36,
            "feedback": "The function correctly adds the two input numbers and matches the expected behavior on representative test cases.",
        }

    if (_contains(question_text, "length", "string") or _contains(question_text, "find", "length")) and "returnlen(str(s))" in normalized_student:
        return {
            "result_type": "full_pass",
            "correctness_min": 36,
            "feedback": "The function correctly returns the length of the string.",
        }

    if (_contains(question_text, "length", "string") or _contains(question_text, "find", "length")) and normalized_student.endswith("returns"):
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "Returning the original string does not compute its length.",
            "suggestion": "Count the characters in the input or use len(s) when that technique is allowed.",
        }

    if (
        "palindrome_ignore_non_alnum" in families
        and "isalnum()" in normalized_student
        and "join(" in normalized_student
        and ".lower()" in normalized_student
        and "returns==s[::-1]" in normalized_student
    ):
        return {
            "result_type": "full_pass",
            "correctness_min": 36,
            "feedback": "The function correctly normalizes the string and checks whether it is a valid palindrome.",
        }

    if "reverse_string_without_slicing" in families and "returns[::-1]" in normalized_student:
        return {
            "result_type": "mostly_correct",
            "correctness_max": 12,
            "efficiency_max": 12,
            "readability_max": 12,
            "structure_max": 12,
            "feedback": "The string reversal logic is correct, but it does not follow the requirement to avoid slicing.",
            "suggestion": "Use a loop or another non-slicing approach to build the reversed string.",
        }

    if "count_vowels" in families and "returnlen(s)" in normalized_student:
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "Returning the string length counts every character, not just the vowels.",
            "suggestion": "Count only the characters that are vowels, for example by checking membership in 'aeiou'.",
        }

    if "palindrome_ignore_case" in families and "returns==s[::-1]" in normalized_student and ".lower()" not in normalized_student and ".casefold()" not in normalized_student:
        return {
            "result_type": "mostly_correct",
            "correctness_max": 12,
            "efficiency_max": 10,
            "readability_max": 12,
            "structure_max": 10,
            "feedback": "The palindrome comparison is close, but it does not ignore case as the question requires.",
            "suggestion": "Normalize the string with lower() or casefold() before comparing it with its reverse.",
        }

    if _contains(question_text, "empty", "string") and "returnnots" in normalized_student:
        return {
            "result_type": "full_pass",
            "correctness_min": 36,
            "feedback": "The function correctly checks whether the string is empty.",
        }

    if _contains(question_text, "empty", "string") and normalized_student.endswith("returntrue") and "returnfalse" not in normalized_student:
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "The function always returns True instead of checking whether the string is empty.",
            "suggestion": "Return a boolean expression such as s == ''.",
        }

    if _contains(question_text, "empty", "string") and "returnlen(s)==0ifselsefalse" in normalized_student:
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "This logic returns False for the empty string, so it does not correctly detect when the string is empty.",
            "suggestion": "Return a direct emptiness check such as s == '' or not s.",
        }

    if _contains(question_text, "concatenate") and "returna" in normalized_student and "returna+b" not in normalized_student:
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "Returning only the first string does not concatenate both input strings.",
            "suggestion": "Return the combined strings, for example with a + b.",
        }

    if _contains(question_text, "concatenate") and "returnb+a" in normalized_student:
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "Concatenating the strings in reverse order does not match the required output.",
            "suggestion": "Return the strings in the original order, for example with a + b.",
        }

    if _contains(question_text, "concatenate") and ("return''.join([a,b])" in normalized_student or 'return"".join([a,b])' in normalized_student):
        return {
            "result_type": "full_pass",
            "correctness_min": 36,
            "feedback": "The function correctly concatenates the two input strings.",
        }

    if _contains(question_text, "lowercase") and ("return''.join([c.lower()forcins])" in normalized_student or 'return"".join([c.lower()forcins])' in normalized_student):
        return {
            "result_type": "full_pass",
            "correctness_min": 36,
            "feedback": "The function correctly converts the input string to lowercase.",
        }

    if _contains(question_text, "lowercase") and normalized_student.endswith("returns"):
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "Returning the original string does not convert it to lowercase.",
            "suggestion": "Convert the text to lowercase, for example with s.lower().",
        }

    if _contains(question_text, "lowercase") and "returns.upper()" in normalized_student:
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "Converting the string to uppercase does the opposite of the required lowercase transformation.",
            "suggestion": "Convert the text to lowercase, for example with s.lower().",
        }

    if _contains(question_text, "repeat", "twice") and "returns+s" in normalized_student:
        return {
            "result_type": "full_pass",
            "correctness_min": 36,
            "feedback": "The function correctly repeats the string twice.",
        }

    if _contains(question_text, "repeat", "twice") and "returns*3" in normalized_student:
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "Repeating the string three times does not match the required two repetitions.",
            "suggestion": "Repeat the string exactly twice, for example with s * 2 or s + s.",
        }

    if _contains(question_text, "repeat", "twice") and normalized_student.endswith("returns"):
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "Returning the original string does not repeat it twice.",
            "suggestion": "Repeat the string exactly twice, for example with s * 2 or s + s.",
        }

    if _contains(question_text, "last character") and "returns[len(s)-1]" in normalized_student:
        return {
            "result_type": "full_pass",
            "correctness_min": 36,
            "feedback": "The function correctly returns the last character of the string.",
        }

    if _contains(question_text, "last character") and "returns[0]" in normalized_student:
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "Returning the first character does not satisfy the last-character requirement.",
            "suggestion": "Return the last character, for example with s[-1].",
        }

    if _contains(question_text, "last character") and ("return''" in normalized_student or 'return""' in normalized_student):
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "Returning an empty string does not retrieve the last character of the input string.",
            "suggestion": "Return the last character, for example with s[-1].",
        }

    if ((_contains(question_text, "unique", "characters")) or (_contains(question_text, "all", "unique"))) and "foriinrange(len(s))" in normalized_student and "forjinrange(i+1,len(s))" in normalized_student and "ifs[i]==s[j]:returnfalse" in normalized_student and normalized_student.endswith("returntrue"):
        return {
            "result_type": "correct_but_inefficient",
            "correctness_min": 36,
            "efficiency_max": 12,
            "feedback": "The function correctly checks whether the string has all unique characters, but nested loops are less efficient than tracking seen characters in a set.",
            "suggestion": "Use a set to detect repeated characters in a single pass.",
        }

    if "palindrome_ignore_case" in families and "s=s.lower()" in normalized_student and "foriinrange(len(s)//2)" in normalized_student and "ifs[i]!=s[-i-1]:returnfalse" in normalized_student and normalized_student.endswith("returntrue"):
        return {
            "result_type": "full_pass",
            "correctness_min": 36,
            "feedback": "The function correctly checks whether the string is a palindrome while ignoring case.",
        }

    if _contains(question_text, "frequency", "characters") and "d={}" in normalized_student and "forcins" in normalized_student and "d.get(c,0)+1" in normalized_student and "returnd" in normalized_student:
        return {
            "result_type": "full_pass",
            "correctness_min": 36,
            "feedback": "The function correctly counts the frequency of each character in the string.",
        }

    if "unique_characters" in families and "seen=set()" in normalized_student and "forcins" in normalized_student and "ifcinseen:returnfalse" in normalized_student and "seen.add(c)" in normalized_student and normalized_student.endswith("returntrue"):
        return {
            "result_type": "full_pass",
            "correctness_min": 36,
            "feedback": "The function correctly checks whether the string has all unique characters.",
        }

    if "unique_characters" in families and ("returnlen(s)==len(set(s))" in normalized_student or "returnlen(set(s))==len(s)" in normalized_student):
        return {
            "result_type": "full_pass",
            "correctness_min": 36,
            "feedback": "The function correctly checks whether the string has all unique characters.",
        }

    return None
