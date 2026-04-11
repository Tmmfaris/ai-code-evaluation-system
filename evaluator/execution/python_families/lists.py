def _contains(question_text, *parts):
    return all(part in (question_text or "") for part in parts)


def evaluate_list_family(question, question_text, families, normalized_student, student_answer):
    if (
        ((_contains(question_text, "maximum") or _contains(question_text, "max")))
        and (_contains(question_text, "list") or _contains(question_text, "array"))
        and ("returnmax(lst)" in normalized_student or "returnmax(arr)" in normalized_student)
    ):
        return {
            "result_type": "full_pass",
            "correctness_min": 36,
            "feedback": "The function correctly returns the maximum value in the collection.",
        }

    if (
        ((_contains(question_text, "maximum") or _contains(question_text, "max")))
        and (_contains(question_text, "list") or _contains(question_text, "array"))
        and (
            "returnsorted(lst)[-1]" in normalized_student
            or "returnsorted(arr)[-1]" in normalized_student
        )
    ):
        return {
            "result_type": "correct_but_inefficient",
            "correctness_min": 36,
            "efficiency_max": 12,
            "feedback": "The function correctly finds the maximum value, but sorting the whole collection is less efficient than a direct maximum scan.",
            "suggestion": "Use max(lst) or a single-pass comparison instead of sorting the entire collection.",
        }

    if (_contains(question_text, "maximum") or _contains(question_text, "max")) and _contains(question_text, "list") and "returnlst[0]" in normalized_student:
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "Returning only the first element works only when the maximum happens to be at the front of the list.",
            "suggestion": "Scan the whole list or use max(lst) to return the largest value.",
        }

    if (_contains(question_text, "maximum") or _contains(question_text, "max")) and _contains(question_text, "array") and "returnarr[0]" in normalized_student:
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "Returning only the first element works only when the maximum happens to be at the front of the array.",
            "suggestion": "Scan the whole array or use max(arr) to return the largest value.",
        }

    if _contains(question_text, "majority", "element") and "forxinlst" in normalized_student and "lst.count(x)>len(lst)//2" in normalized_student and "returnx" in normalized_student:
        return {
            "result_type": "correct_but_inefficient",
            "correctness_min": 36,
            "efficiency_max": 12,
            "feedback": "The function correctly identifies the majority element, but repeated count checks make it less efficient than counting frequencies once.",
            "suggestion": "Use a frequency map or Boyer-Moore majority vote to avoid repeated full-list scans.",
        }

    if "group_anagrams" in families and "return[strs]" in normalized_student:
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "Returning [strs] puts every string into one group instead of grouping words by shared anagram signature.",
            "suggestion": "Group the strings by a normalized key such as sorted characters, then return the grouped lists.",
        }

    if "frequency_elements" in families and normalized_student.endswith("return{}"):
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "Returning an empty dictionary does not count the frequency of the list elements.",
            "suggestion": "Count how many times each value appears and return those counts in a dictionary.",
        }

    if "frequency_elements" in families and "d={}" in normalized_student and "forxinlst" in normalized_student and "d[x]=1" in normalized_student and "+=1" not in normalized_student and ".get(x,0)+1" not in normalized_student:
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "Assigning 1 for every element does not count repeated values correctly.",
            "suggestion": "Increase the stored count when a value appears again, for example with d[x] = d.get(x, 0) + 1.",
        }

    if _contains(question_text, "sum", "even", "numbers") and _contains(question_text, "list") and normalized_student.endswith("return0"):
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "Returning 0 does not calculate the sum of the even numbers in the list.",
            "suggestion": "Add only the values where x % 2 == 0, for example with sum(x for x in lst if x % 2 == 0).",
        }

    if (_contains(question_text, "average") or _contains(question_text, "mean")) and (_contains(question_text, "list") or _contains(question_text, "array")):
        if "returnsum(lst)/len(lst)" in normalized_student or "returnsum(arr)/len(arr)" in normalized_student:
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": "The function correctly computes the average of the collection.",
            }
        if "returnsum(lst)" in normalized_student or "returnsum(arr)" in normalized_student:
            return {
                "result_type": "zero_pass",
                "correctness_max": 5,
                "efficiency_max": 5,
                "feedback": "Returning the sum alone does not compute the average.",
                "suggestion": "Divide the sum by the number of elements to get the average.",
            }
        if normalized_student.endswith("return0"):
            return {
                "result_type": "zero_pass",
                "correctness_max": 5,
                "efficiency_max": 5,
                "feedback": "Returning 0 does not compute the average of the list.",
                "suggestion": "Sum the list and divide by the number of elements.",
            }

    if _contains(question_text, "remove", "duplicates") and _contains(question_text, "list") and "preserve order" in (question or "").lower() and normalized_student.endswith("returnlst"):
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "Returning the original list does not remove duplicate values.",
            "suggestion": "Track seen values and build a new list that keeps only the first occurrence of each item.",
        }

    if _contains(question_text, "remove", "duplicates") and _contains(question_text, "list") and "preserve order" in (question or "").lower() and "returnlist(set(lst))" in normalized_student:
        return {
            "result_type": "zero_pass",
            "correctness_max": 8,
            "efficiency_max": 8,
            "feedback": "Using set removes duplicates but does not preserve the original order of the list.",
            "suggestion": "Use an ordered approach such as dict.fromkeys(...) or a loop with a seen set.",
        }

    if _contains(question_text, "first", "element") and normalized_student.endswith("returnnone"):
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "Returning None does not retrieve the first element of the list.",
            "suggestion": "Return the first list item, for example with lst[0].",
        }

    if _contains(question_text, "first", "element") and "returnlst[-1]" in normalized_student:
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "Returning the last element does not satisfy the first-element requirement.",
            "suggestion": "Return the first list item, for example with lst[0].",
        }

    if _contains(question_text, "first", "element") and "returnlst.pop(0)" in normalized_student:
        return {
            "result_type": "mostly_correct",
            "correctness_max": 18,
            "efficiency_max": 12,
            "readability_max": 12,
            "structure_max": 12,
            "feedback": "The function returns the first element, but it mutates the original list by removing that element.",
            "suggestion": "Use indexing like lst[0] so you return the first element without changing the list.",
        }

    if _contains(question_text, "last", "element") and normalized_student.endswith("returnnone"):
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "Returning None does not retrieve the last element of the list.",
            "suggestion": "Return the last list item, for example with lst[-1].",
        }

    if _contains(question_text, "last", "element") and "returnlst[len(lst)-1]" in normalized_student:
        return {
            "result_type": "full_pass",
            "correctness_min": 36,
            "feedback": "The function correctly returns the last element of the list.",
        }

    if _contains(question_text, "last", "element") and "returnlst[0]" in normalized_student:
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "Returning the first element does not satisfy the last-element requirement.",
            "suggestion": "Return the last list item, for example with lst[-1].",
        }

    if _contains(question_text, "count", "elements") and _contains(question_text, "list") and "returnsum(1for_inlst)" in normalized_student:
        return {
            "result_type": "full_pass",
            "correctness_min": 36,
            "feedback": "The function correctly counts the elements in the list.",
        }

    if _contains(question_text, "count", "elements") and _contains(question_text, "list") and "returnlen(set(lst))" in normalized_student:
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "Counting unique values with set(lst) does not return the total number of elements in the list.",
            "suggestion": "Count every element in the list, for example with len(lst).",
        }

    if _contains(question_text, "count", "elements") and _contains(question_text, "list") and normalized_student.endswith("return0"):
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "Returning 0 does not count the number of elements in the list.",
            "suggestion": "Count every element in the list, for example with len(lst).",
        }

    if (_contains(question_text, "length", "list") or _contains(question_text, "get", "length", "list")) and "returnsum(1for_inlst)" in normalized_student:
        return {
            "result_type": "full_pass",
            "correctness_min": 36,
            "feedback": "The function correctly returns the length of the list.",
        }

    if (_contains(question_text, "length", "list") or _contains(question_text, "get", "length", "list")) and "returnlen(set(lst))" in normalized_student:
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "Counting unique values with set(lst) does not return the full length of the list.",
            "suggestion": "Count every element in the list, for example with len(lst).",
        }

    if (_contains(question_text, "length", "list") or _contains(question_text, "get", "length", "list")) and normalized_student.endswith("return1"):
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "Returning 1 does not calculate the length of the list.",
            "suggestion": "Return the number of elements in the list, for example with len(lst).",
        }

    if (_contains(question_text, "empty", "list") or _contains(question_text, "empty", "array")):
        if "returnnotlst" in normalized_student or "returnlen(lst)==0" in normalized_student:
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": "The function correctly checks whether the collection is empty.",
            }
        if normalized_student.endswith("returntrue") and "returnfalse" not in normalized_student:
            return {
                "result_type": "zero_pass",
                "correctness_max": 5,
                "efficiency_max": 5,
                "feedback": "The function always returns True instead of checking whether the collection is empty.",
                "suggestion": "Return True only when the collection has no elements.",
            }
        if normalized_student.endswith("returnfalse") and "returntrue" not in normalized_student:
            return {
                "result_type": "zero_pass",
                "correctness_max": 5,
                "efficiency_max": 5,
                "feedback": "The function always returns False instead of checking whether the collection is empty.",
                "suggestion": "Return True only when the collection has no elements.",
            }

    if _contains(question_text, "append item to list") and "returnlst+[x]" in normalized_student:
        return {
            "result_type": "mostly_correct",
            "correctness_max": 18,
            "efficiency_max": 12,
            "readability_max": 12,
            "structure_max": 12,
            "feedback": "The function returns a new list with the item appended, but it does not modify the original list in place like the reference solution.",
            "suggestion": "If in-place modification is required, append to the original list and return that same list.",
        }

    if _contains(question_text, "append item to list") and "lst.append(x)" in (student_answer or "") and "returnlst" not in normalized_student:
        return {
            "result_type": "mostly_correct",
            "correctness_max": 18,
            "efficiency_max": 12,
            "readability_max": 12,
            "structure_max": 12,
            "feedback": "The function appends the item, but it does not return the updated list as the task expects.",
            "suggestion": "Return the modified list after appending the new item.",
        }

    if _contains(question_text, "append item to list") and normalized_student.endswith("returnlst"):
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "Returning the original list does not append the new item.",
            "suggestion": "Append the item to the list before returning it.",
        }

    if _contains(question_text, "list is empty") and "returnnotlst" in normalized_student:
        return {
            "result_type": "full_pass",
            "correctness_min": 36,
            "feedback": "The function correctly checks whether the list is empty.",
        }

    if _contains(question_text, "list is empty") and "returnlst==[]iflstelsefalse" in normalized_student:
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "This logic returns False for the empty list, so it does not correctly detect when the list is empty.",
            "suggestion": "Return a direct emptiness check such as len(lst) == 0 or not lst.",
        }

    if _contains(question_text, "list is empty") and normalized_student.endswith("returnfalse") and "returntrue" not in normalized_student:
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "The function always returns False instead of checking whether the list is empty.",
            "suggestion": "Return True only when the list has no elements.",
        }

    if _contains(question_text, "list", "sorted") and "foriinrange(len(lst)-1)" in normalized_student and "iflst[i]>lst[i+1]:returnfalse" in normalized_student and normalized_student.endswith("returntrue"):
        return {
            "result_type": "full_pass",
            "correctness_min": 36,
            "feedback": "The function correctly checks whether the list is sorted.",
        }

    if "frequency_elements" in families and "d={}" in normalized_student and "forxinlst" in normalized_student and "ifxind" in normalized_student and "d[x]+=1" in normalized_student and "else:d[x]=1" in normalized_student and "returnd" in normalized_student:
        return {
            "result_type": "full_pass",
            "correctness_min": 36,
            "feedback": "The function correctly counts the frequency of each element in the list.",
        }

    if "frequency_elements" in families and "return{x:lst.count(x)forxinlst}" in normalized_student:
        return {
            "result_type": "correct_but_inefficient",
            "correctness_min": 36,
            "efficiency_max": 12,
            "feedback": "The function correctly counts the frequency of each element, but repeatedly calling lst.count(x) scans the list many times.",
            "suggestion": "Build the counts in one pass with a dictionary so repeated full-list scans are avoided.",
        }

    if _contains(question_text, "sum", "even", "numbers") and _contains(question_text, "list") and "total=0" in normalized_student and "forxinlst" in normalized_student and "ifx%2==0" in normalized_student and "total+=x" in normalized_student and normalized_student.endswith("returntotal"):
        return {
            "result_type": "full_pass",
            "correctness_min": 36,
            "feedback": "The function correctly calculates the sum of the even numbers in the list.",
        }

    if _contains(question_text, "sum", "even", "numbers") and _contains(question_text, "list") and "returnsum([xforxinlstifx%2==0])" in normalized_student:
        return {
            "result_type": "full_pass",
            "correctness_min": 36,
            "feedback": "The function correctly calculates the sum of the even numbers in the list.",
        }

    if _contains(question_text, "remove", "duplicates") and _contains(question_text, "list") and "preserve order" in (question or "").lower() and "res=[]" in normalized_student and "forxinlst" in normalized_student and "ifxnotinres:res.append(x)" in normalized_student and "returnres" in normalized_student:
        return {
            "result_type": "full_pass",
            "correctness_min": 36,
            "feedback": "The function correctly removes duplicates from the list while preserving the original order.",
        }

    if _contains(question_text, "remove", "duplicates") and _contains(question_text, "list") and "preserve order" in (question or "").lower() and "seen=set()" in normalized_student and "res=[]" in normalized_student and "forxinlst" in normalized_student and "ifxnotinseen:" in normalized_student and "seen.add(x)" in normalized_student and "res.append(x)" in normalized_student and "returnres" in normalized_student:
        return {
            "result_type": "full_pass",
            "correctness_min": 36,
            "feedback": "The function correctly removes duplicates from the list while preserving the original order.",
        }

    if _contains(question_text, "contains", "duplicates") and "seen=set()" in normalized_student and "ifxinseen:returntrue" in normalized_student and "seen.add(x)" in normalized_student and normalized_student.endswith("returnfalse"):
        return {
            "result_type": "full_pass",
            "correctness_min": 36,
            "feedback": "The function correctly checks whether the list contains duplicate values.",
        }

    if _contains(question_text, "intersection") and _contains(question_text, "list") and "res=[]" in normalized_student and "forxina" in normalized_student and "ifxinbandxnotinres:res.append(x)" in normalized_student and "returnres" in normalized_student:
        return {
            "result_type": "full_pass",
            "correctness_min": 36,
            "feedback": "The function correctly returns the intersection of the two lists without duplicate values.",
        }

    if _contains(question_text, "intersection") and _contains(question_text, "list") and normalized_student.endswith("returna"):
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "The function returns the first list instead of returning the shared elements from both lists.",
            "suggestion": "Return only the values that appear in both input lists.",
        }

    if _contains(question_text, "second largest") and "lst=list(set(lst))" in normalized_student and "lst.remove(max(lst))" in normalized_student and normalized_student.endswith("returnmax(lst)"):
        return {
            "result_type": "full_pass",
            "correctness_min": 36,
            "feedback": "The function correctly returns the second distinct largest value in the list.",
        }

    if _contains(question_text, "second largest") and "returnmax(lst)" in normalized_student:
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "Returning the maximum value does not solve the second-largest-number problem.",
            "suggestion": "Track the largest and second distinct largest values, or sort the distinct values and return the second last one.",
        }

    if _contains(question_text, "second largest") and "sorted(lst)[-2]" in normalized_student and "set(lst)" not in normalized_student:
        return {
            "result_type": "mostly_correct",
            "correctness_max": 24,
            "efficiency_max": 12,
            "readability_max": 12,
            "structure_max": 12,
            "feedback": "Sorting the list and taking the second last element works for many inputs, but it can return the largest value again when duplicates are present.",
            "suggestion": "Remove duplicates first, or track the two largest distinct values explicitly.",
        }

    return None
