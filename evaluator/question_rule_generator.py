import json
import re

from config import (
    AUTO_ACTIVATE_VALIDATED_QUESTIONS,
    AUTO_GENERATE_MAX_ALTERNATIVES,
    AUTO_GENERATE_MAX_HIDDEN_TESTS,
    AUTO_GENERATE_QUESTION_RULES,
    MIN_PACKAGE_CONFIDENCE_FOR_EXAM,
    ORACLE_TEST_CASES_BASE,
    ORACLE_TEST_CASES_EXPANDED,
    QUESTION_REGISTER_LLM_REPAIR_ATTEMPTS,
    REQUIRE_FACULTY_APPROVAL_FOR_LIVE,
)
from analysis.syntax_checker.css_checker import check_css_syntax
from analysis.syntax_checker.html_checker import check_html_syntax
from analysis.syntax_checker.javascript_checker import check_javascript_syntax
from analysis.syntax_checker.mongodb_checker import check_mongodb_syntax
from analysis.syntax_checker.mysql_checker import check_mysql_syntax
from analysis.syntax_checker.react_checker import check_react_syntax
from evaluator.execution.shared import (
    _extract_first_function_name,
    _run_code_with_timeout,
    _smart_outputs_equal,
    _wrap_python_snippet,
    evaluate_java_hidden_tests,
    evaluate_javascript_hidden_tests,
)
from evaluator.question_learning_store import list_recent_learning_signals
from llm.llm_engine import call_llm
from utils.helpers import normalize_python_structure


def _extract_first_json_object(text):
    if not text:
        return None
    cleaned = str(text).strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    decoder = json.JSONDecoder()
    for start, char in enumerate(cleaned):
        if char not in "{[":
            continue
        try:
            parsed, _ = decoder.raw_decode(cleaned[start:])
            if isinstance(parsed, list):
                return {"incorrect_patterns": parsed}
            return parsed
        except json.JSONDecodeError:
            continue
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return None


def _is_registration_package_json(parsed):
    if not isinstance(parsed, dict):
        return False
    package_keys = {"accepted_solutions", "test_sets", "incorrect_patterns"}
    if not any(key in parsed for key in package_keys):
        return False
    if "score" in parsed and "rubric" in parsed and "feedback" in parsed:
        return False
    if "accepted_solutions" in parsed and not isinstance(parsed.get("accepted_solutions"), list):
        return False
    if "incorrect_patterns" in parsed and not isinstance(parsed.get("incorrect_patterns"), list):
        return False
    if "test_sets" in parsed and not isinstance(parsed.get("test_sets"), dict):
        return False
    return True


def _normalize_question_signature(question, language):
    normalized_question = re.sub(r"\s+", " ", (question or "").strip().lower())
    normalized_question = re.sub(r"[^a-z0-9 ]", "", normalized_question)
    return f"{(language or '').strip().lower()}::{normalized_question}"


_CARDINAL_NUMBER_WORDS = {
    "zero": 0,
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
}

_ORDINAL_NUMBER_WORDS = {
    "first": 1,
    "second": 2,
    "third": 3,
    "fourth": 4,
    "fifth": 5,
    "sixth": 6,
    "seventh": 7,
    "eighth": 8,
    "ninth": 9,
    "tenth": 10,
}


def _parse_small_int_token(token):
    if token is None:
        return None
    cleaned = str(token).strip().lower()
    if re.fullmatch(r"-?\d+", cleaned):
        return int(cleaned)
    if cleaned in _CARDINAL_NUMBER_WORDS:
        return _CARDINAL_NUMBER_WORDS[cleaned]
    if cleaned in _ORDINAL_NUMBER_WORDS:
        return _ORDINAL_NUMBER_WORDS[cleaned]
    return None


def _extract_character_prefix_count(question_text):
    normalized = (question_text or "").strip().lower()
    match = re.search(r"first\s+([a-z0-9-]+)\s+characters?", normalized)
    if not match:
        return None
    return _parse_small_int_token(match.group(1))


def _extract_last_n_characters_count(question_text):
    normalized = (question_text or "").strip().lower()
    match = re.search(r"last\s+([a-z0-9-]+)\s+characters?", normalized)
    if not match:
        return None
    return _parse_small_int_token(match.group(1))


def _mentions_first_and_last_character(question_text):
    normalized = (question_text or "").strip().lower()
    return bool(
        ("first and last character" in normalized)
        or ("first & last character" in normalized)
        or (
            "first" in normalized
            and "last" in normalized
            and "character" in normalized
        )
    )


def _extract_list_contains_constant(question_text):
    normalized = (question_text or "").strip().lower()
    match = re.search(r"(?:list|array).*(?:contains?|has)\s+(?:value\s+)?(-?\d+)", normalized)
    if not match:
        match = re.search(r"(?:contains?|has)\s+(?:value\s+)?(-?\d+).*(?:list|array)", normalized)
    if not match:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None


def _extract_list_length_comparison(question_text):
    normalized = (question_text or "").strip().lower()
    patterns = [
        (r"(?:length|size)\s*(?:is|of)?\s*(?:less than|<)\s*([a-z0-9-]+)", "<"),
        (r"(?:length|size)\s*(?:is|of)?\s*(?:greater than|more than|>)\s*([a-z0-9-]+)", ">"),
        (r"(?:length|size)\s*(?:is|of)?\s*(?:less than or equal to|<=)\s*([a-z0-9-]+)", "<="),
        (r"(?:length|size)\s*(?:is|of)?\s*(?:greater than or equal to|>=)\s*([a-z0-9-]+)", ">="),
        (r"less than\s+([a-z0-9-]+)\s+(?:elements|items)", "<"),
        (r"more than\s+([a-z0-9-]+)\s+(?:elements|items)", ">"),
    ]
    for pattern, operator in patterns:
        match = re.search(pattern, normalized)
        if match:
            val = _parse_small_int_token(match.group(1))
            if val is not None:
                return {"operator": operator, "value": val}
    return None


def _extract_element_position(question_text):
    normalized = (question_text or "").strip().lower()
    ordinal_words = "|".join(sorted(_ORDINAL_NUMBER_WORDS.keys(), key=len, reverse=True))
    ordinal_match = re.search(rf"\b({ordinal_words}|\d+(?:st|nd|rd|th))\s+element\b", normalized)
    if ordinal_match:
        token = ordinal_match.group(1)
        numeric_match = re.fullmatch(r"(\d+)(?:st|nd|rd|th)", token)
        if numeric_match:
            return int(numeric_match.group(1))
        return _parse_small_int_token(token)
    index_match = re.search(r"index\s+(-?\d+)", normalized)
    if index_match:
        return int(index_match.group(1)) + 1
    return None


def _infer_template_family(question, language):
    question_text = (question or "").lower()
    language = (language or "").strip().lower()
    if "factorial" in question_text:
        return f"{language}::factorial"
    if "recursive" in question_text or "recursion" in question_text:
        return f"{language}::recursion"
    if _contains_all(question_text, "add", "two", "numbers"):
        return f"{language}::add_two_numbers"
    if _contains_all(question_text, "subtract", "two", "numbers") or _contains_all(question_text, "subtract", "numbers"):
        return f"{language}::subtract_two_numbers"
    if _contains_all(question_text, "multiply", "two", "numbers") or _contains_all(question_text, "product", "two", "numbers"):
        return f"{language}::multiply_two_numbers"
    if _contains_all(question_text, "divide", "two", "numbers") or _contains_all(question_text, "division", "two", "numbers"):
        return f"{language}::divide_two_numbers"
    if "cube of a number" in question_text or "return cube of a number" in question_text or _contains_all(question_text, "cube", "number"):
        return f"{language}::cube_number"
    if "square of a number" in question_text or "return square of a number" in question_text or _contains_all(question_text, "square", "number"):
        return f"{language}::square_number"
    if "absolute" in question_text and "value" in question_text:
        return f"{language}::absolute_value"
    if "length of string" in question_text or "find length of string" in question_text:
        return f"{language}::string_length"
    if _contains_all(question_text, "reverse", "string"):
        return f"{language}::reverse_string"
    if _contains_all(question_text, "reverse", "words"):
        return f"{language}::reverse_words"
    if (
        _contains_all(question_text, "reverse", "list")
        or _contains_all(question_text, "reverse", "array")
        or _contains_all(question_text, "list", "reverse")
        or _contains_all(question_text, "array", "reverse")
    ):
        return f"{language}::reverse_list"

    if "uppercase" in question_text and "string" in question_text:
        return f"{language}::uppercase_string"
    if (
        _contains_all(question_text, "check", "lowercase")
        or _contains_all(question_text, "string", "lowercase")
        and ("check" in question_text or "is " in question_text or " if " in question_text)
    ):
        return f"{language}::lowercase_check"
    if "lowercase" in question_text and "string" in question_text:
        return f"{language}::lowercase_string"
    if "palindrome" in question_text:
        return f"{language}::palindrome"
    if "ipv4" in question_text or _contains_all(question_text, "ip", "address"):
        return f"{language}::ipv4"
    if _contains_all(question_text, "valid", "json"):
        return f"{language}::valid_json"
    if _contains_all(question_text, "exception", "handling") and "division" in question_text:
        return f"{language}::safe_divide_exception"
    if _contains_all(question_text, "convert", "string", "integer", "safely"):
        return f"{language}::safe_parse_int"
    if "nullpointerexception" in question_text or (_contains_all(question_text, "null") and _contains_all(question_text, "string", "length")):
        return f"{language}::null_safe_length"
    if _contains_all(question_text, "valid", "email"):
        return f"{language}::valid_email"
    if _contains_all(question_text, "valid", "url"):
        return f"{language}::valid_url"
    if _contains_all(question_text, "count", "vowel") and "string" in question_text:
        return f"{language}::count_vowels"
    if (_contains_all(question_text, "unique", "characters")) or (_contains_all(question_text, "all", "unique")):
        return f"{language}::unique_characters"
    if _mentions_first_and_last_character(question_text):
        return f"{language}::first_and_last_character"
    character_prefix_count = _extract_character_prefix_count(question_text)
    if character_prefix_count == 2:
        return f"{language}::first_two_characters"
    if character_prefix_count and character_prefix_count > 0:
        return f"{language}::prefix_characters_constant"

    suffix_character_count = _extract_last_n_characters_count(question_text)
    if suffix_character_count and suffix_character_count > 0 and not _mentions_first_and_last_character(question_text):
        return f"{language}::suffix_characters_constant"
    if _contains_all(question_text, "middle", "character") and "string" in question_text:
        return f"{language}::middle_character"
    if (
        _contains_all(question_text, "first", "character")
        and not (
            _contains_all(question_text, "last", "character")
            or "first and last character" in question_text
            or "first & last character" in question_text
        )
    ):
        return f"{language}::first_character"
    if (
        _contains_all(question_text, "last", "character")
        and not (
            _contains_all(question_text, "first", "character")
            or "first and last character" in question_text
            or "first & last character" in question_text
        )
    ):
        return f"{language}::last_character"
    if _contains_all(question_text, "count", "words"):
        return f"{language}::count_words"
    if _contains_all(question_text, "remove", "spaces"):
        return f"{language}::remove_spaces"
    if "starts with" in question_text and "string" in question_text:
        return f"{language}::string_startswith"
    if ("ends with" in question_text or "endswith" in question_text or "suffix" in question_text) and "string" in question_text:
        return f"{language}::string_endswith"
    if _contains_all(question_text, "only", "digits") or "numeric" in question_text:
        return f"{language}::only_digits"
    if _contains_all(question_text, "only", "alphabets") or _contains_all(question_text, "only", "alphabet"):
        return f"{language}::only_alphabets"
    if _contains_all(question_text, "convert", "string", "integer"):
        return f"{language}::convert_string_to_integer"
    if "balanced parentheses" in question_text or (_contains_all(question_text, "balanced") and "parentheses" in question_text):
        return f"{language}::balanced_parentheses"
    if "anagram" in question_text:
        return f"{language}::anagram"
    if "armstrong" in question_text:
        return f"{language}::armstrong"
    if "leap year" in question_text:
        return f"{language}::leap_year"
    if "gcd" in question_text or "greatest common divisor" in question_text:
        return f"{language}::gcd"
    if "lcm" in question_text or "least common multiple" in question_text:
        return f"{language}::lcm"
    if "power of 2" in question_text or "power of two" in question_text:
        return f"{language}::power_of_two"
    if "power of 3" in question_text or "power of three" in question_text:
        return f"{language}::power_of_three"
    if (
        _contains_all(question_text, "number", "zero")
        or "is zero" in question_text
        or "equal to zero" in question_text
        or "equals zero" in question_text
    ):
        return f"{language}::zero_check"
    if _contains_all(question_text, "number", "negative") or "negative number" in question_text or "is negative" in question_text:
        return f"{language}::negative_number"
    if _contains_all(question_text, "number", "positive") or "positive number" in question_text or "is positive" in question_text:
        return f"{language}::positive_number"
    if (
        "number" in question_text
        and re.search(r"greater than\s+-?\d+", question_text)
    ):
        return f"{language}::greater_than_threshold"
    if "number" in question_text and re.search(r"divisible by\s+-?\d+", question_text):
        return f"{language}::divisible_by_constant"
    if "odd" in question_text and "number" in question_text:
        return f"{language}::odd_check"
    if "double" in question_text and "number" in question_text:
        return f"{language}::double_number"
    if _contains_all(question_text, "reverse", "number") or _contains_all(question_text, "reverse", "a", "number"):
        return f"{language}::reverse_number"
    if "concatenate" in question_text and "string" in question_text:
        return f"{language}::concatenate_strings"
    if (
        ("average" in question_text or "mean" in question_text)
        and ("list" in question_text or "array" in question_text)
    ):
        return f"{language}::average_collection"
    element_position = _extract_element_position(question_text)
    if element_position == 2 and ("list" in question_text or "array" in question_text):
        return f"{language}::second_element"
    if element_position == 1 and ("list" in question_text or "array" in question_text):
        return f"{language}::first_element"
    if element_position and element_position > 2 and ("list" in question_text or "array" in question_text):
        return f"{language}::element_at_index_constant"
    if (
        ("list" in question_text or "array" in question_text or "collection" in question_text)
        and (
            "at least one element" in question_text
            or "has items" in question_text
            or "has any" in question_text
            or "not empty" in question_text
            or "non-empty" in question_text
            or "non empty" in question_text
        )
    ):
        return f"{language}::non_empty_collection_check"
    if _contains_all(question_text, "empty", "list") or _contains_all(question_text, "empty", "array") or _contains_all(question_text, "list", "empty") or _contains_all(question_text, "array", "empty"):
        return f"{language}::empty_collection_check"
    if _contains_all(question_text, "empty", "string"):
        return f"{language}::empty_string_check"
    if language == "mysql":
        if "join" in question_text:
            return "mysql::sql_join"
        if "having" in question_text:
            return "mysql::sql_having"
        if "distinct" in question_text:
            return "mysql::sql_distinct"
        if "limit" in question_text:
            return "mysql::sql_limit"
        if "group by" in question_text or "count" in question_text or "sum" in question_text or "avg" in question_text or "aggregate" in question_text:
            return "mysql::sql_group_aggregate"
        if "order by" in question_text or "sort" in question_text:
            return "mysql::sql_order"
        if "insert" in question_text:
            return "mysql::sql_insert"
        if "update" in question_text:
            return "mysql::sql_update"
        if "delete" in question_text:
            return "mysql::sql_delete"
        if "select" in question_text or "where" in question_text or "filter" in question_text:
            return "mysql::sql_select"
        return "mysql::static_template"
    if language == "mongodb" and ("aggregate" in question_text or "$group" in question_text):
        return "mongodb::aggregation"
    if language == "react":
        if "usestate" in question_text or "state management" in question_text or ("state" in question_text and "react" in question_text):
            return "react::use_state"
        if "useeffect" in question_text or "fetch api" in question_text or "fetch data" in question_text or ("effect" in question_text and "react" in question_text):
            return "react::use_effect"
        if "props" in question_text:
            return "react::props_component"
        if "list" in question_text and ("render" in question_text or "map" in question_text):
            return "react::list_render"
        if "form" in question_text or "authentication" in question_text or "login" in question_text or "signup" in question_text:
            return "react::form_component"
        if "conditional" in question_text or "show" in question_text or "hide" in question_text:
            return "react::conditional_render"
        if "click" in question_text or "button" in question_text or "event" in question_text:
            return "react::event_handler"
        if "hook" in question_text:
            return "react::hooks"
        if "component-driven" in question_text or "component driven" in question_text:
            return "react::component"
        return "react::component"
    if language == "css":
        if "flex" in question_text:
            return "css::flex_layout"
        if "grid" in question_text:
            return "css::grid_layout"
        if "responsive" in question_text or "bootstrap" in question_text:
            return "css::layout"
        if "font" in question_text or "typography" in question_text or "text-align" in question_text or "text align" in question_text:
            return "css::typography"
        if "margin" in question_text or "padding" in question_text or "spacing" in question_text:
            return "css::spacing"
        if "border" in question_text or "radius" in question_text or "rounded" in question_text:
            return "css::border_style"
        if "width" in question_text or "height" in question_text or "size" in question_text:
            return "css::sizing"
        if "display" in question_text or "inline" in question_text or "block" in question_text or "position" in question_text:
            return "css::display"
        if "background" in question_text:
            return "css::background_style"
        if "color" in question_text and "background" not in question_text:
            return "css::text_color"
        if "hover" in question_text:
            return "css::hover_style"
        if "button" in question_text:
            return "css::button_style"
        if "card" in question_text:
            return "css::card_style"
        if "center" in question_text:
            return "css::center_alignment"
        if "layout" in question_text:
            return "css::layout"
        return "css::static_template"
    if language == "html":
        if "form" in question_text:
            return "html::form"
        if "responsive" in question_text or "bootstrap" in question_text:
            return "html::semantic_layout"
        if "table" in question_text:
            return "html::table"
        if "image" in question_text or "img" in question_text:
            return "html::image"
        if "audio" in question_text or "video" in question_text or "media" in question_text:
            return "html::media"
        if "link" in question_text or "anchor" in question_text:
            return "html::link"
        if "unordered list" in question_text or "ordered list" in question_text or "list item" in question_text:
            return "html::list"
        if "heading" in question_text or "h1" in question_text:
            return "html::heading"
        if "paragraph" in question_text:
            return "html::paragraph"
        if "input" in question_text or "textarea" in question_text or "select" in question_text or "dropdown" in question_text or "label" in question_text:
            return "html::input_form_controls"
        if "div" in question_text or "container" in question_text or "span" in question_text:
            return "html::container"
        if "button" in question_text:
            return "html::button"
        if "semantic" in question_text or "header" in question_text or "footer" in question_text or "nav" in question_text or "section" in question_text:
            return "html::semantic_layout"
        return "html::static_template"
    if language == "mongodb":
        if "crud" in question_text or "collection" in question_text or "nosql" in question_text or "database" in question_text:
            return "mongodb::find_query"
        if "aggregate" in question_text or "$group" in question_text:
            return "mongodb::aggregation"
        if "insert" in question_text:
            return "mongodb::insert_query"
        if "delete" in question_text or "remove" in question_text:
            return "mongodb::delete_query"
        if "count" in question_text:
            return "mongodb::count_query"
        if "limit" in question_text:
            return "mongodb::limit_query"
        if "distinct" in question_text:
            return "mongodb::distinct_query"
        if "sort" in question_text:
            return "mongodb::sort_query"
        if "project" in question_text or "projection" in question_text:
            return "mongodb::projection"
        if "update" in question_text or "$set" in question_text:
            return "mongodb::update"
        if "find" in question_text:
            return "mongodb::find_query"
        return "mongodb::static_template"
    if "even" in question_text:
        return f"{language}::even_check"
    if "prime" in question_text:
        return f"{language}::prime_check"
    if _contains_all(question_text, "sum", "digits"):
        return f"{language}::sum_of_digits"
    if _contains_all(question_text, "split", "dataset") and _contains_all(question_text, "train") and _contains_all(question_text, "test"):
        return f"{language}::train_test_split"
    if _contains_all(question_text, "stratified", "train", "test", "split") or _contains_all(question_text, "stratified", "train-test", "split"):
        return f"{language}::stratified_train_test_split"
    if _contains_all(question_text, "shuffle", "dataset") and _contains_all(question_text, "features", "labels", "aligned"):
        return f"{language}::shuffle_dataset_aligned"
    if _contains_all(question_text, "shuffle", "dataset"):
        return f"{language}::shuffle_dataset"
    if _contains_all(question_text, "accuracy") and _contains_all(question_text, "predictions") and _contains_all(question_text, "labels"):
        return f"{language}::classification_accuracy"
    if _contains_all(question_text, "precision", "score"):
        return f"{language}::precision_score"
    if _contains_all(question_text, "recall", "score"):
        return f"{language}::recall_score"
    if _contains_all(question_text, "f1", "score"):
        return f"{language}::f1_score"
    if _contains_all(question_text, "confusion", "matrix"):
        return f"{language}::confusion_matrix"
    if _contains_all(question_text, "k-fold", "cross", "validation") or _contains_all(question_text, "k", "fold", "cross", "validation"):
        return f"{language}::kfold_cross_validation"
    if "roc-auc" in question_text or _contains_all(question_text, "roc", "auc"):
        return f"{language}::roc_auc_score"
    if _contains_all(question_text, "log", "loss"):
        return f"{language}::log_loss"
    if _contains_all(question_text, "mean", "squared", "error"):
        return f"{language}::mean_squared_error"
    if "rmse" in question_text or _contains_all(question_text, "root", "mean", "squared", "error"):
        return f"{language}::rmse"
    if _contains_all(question_text, "missing", "values") and "none" in question_text:
        return f"{language}::has_missing_values"
    if _contains_all(question_text, "drop", "rows") and _contains_all(question_text, "missing", "values"):
        return f"{language}::drop_missing_rows"
    if _contains_all(question_text, "label", "encoding"):
        return f"{language}::label_encoding"
    if _contains_all(question_text, "one-hot", "encoding") or _contains_all(question_text, "one", "hot", "encoding"):
        return f"{language}::one_hot_encoding"
    if "labelencoder" in question_text or (_contains_all(question_text, "encode", "labels") and "sklearn" in question_text):
        return f"{language}::label_encoder"
    if _contains_all(question_text, "fill", "missing") and "mean" in question_text:
        return f"{language}::fill_missing_with_mean"
    if _contains_all(question_text, "fill", "missing") and "median" in question_text:
        return f"{language}::fill_missing_with_median"
    if ("min-max" in question_text or "min max" in question_text) and ("normalize" in question_text or "normalization" in question_text):
        return f"{language}::min_max_normalize"
    if "minmaxscaler" in question_text or (_contains_all(question_text, "scale", "features") and "minmax" in question_text):
        return f"{language}::minmax_scaler"
    if _contains_all(question_text, "mean", "normalization"):
        return f"{language}::mean_normalization"
    if "z-score" in question_text or "z score" in question_text or "standardize" in question_text or "standardization" in question_text:
        return f"{language}::zscore_standardize"
    if _contains_all(question_text, "remove", "outliers") and ("z-score" in question_text or "z score" in question_text):
        return f"{language}::zscore_outlier_removal"
    if _contains_all(question_text, "outliers") and "iqr" in question_text:
        return f"{language}::iqr_outliers"
    if _contains_all(question_text, "split", "features") and _contains_all(question_text, "labels"):
        return f"{language}::split_features_labels"
    if _contains_all(question_text, "linear", "regression", "prediction") or "y = mx + c" in question_text:
        return f"{language}::linear_regression_predict"
    if _contains_all(question_text, "train", "logistic", "regression"):
        return f"{language}::train_logistic_regression"
    if _contains_all(question_text, "fit", "logistic", "regression"):
        return f"{language}::train_logistic_regression"
    if _contains_all(question_text, "train", "decision", "tree"):
        return f"{language}::train_decision_tree"
    if _contains_all(question_text, "fit", "decision", "tree"):
        return f"{language}::train_decision_tree"
    if _contains_all(question_text, "train", "knn") or _contains_all(question_text, "train", "k", "nn"):
        return f"{language}::train_knn"
    if _contains_all(question_text, "fit", "knn") or _contains_all(question_text, "fit", "k", "nn"):
        return f"{language}::train_knn"
    if _contains_all(question_text, "train", "svm"):
        return f"{language}::train_svm"
    if _contains_all(question_text, "fit", "svm"):
        return f"{language}::train_svm"
    if _contains_all(question_text, "train", "random", "forest") or _contains_all(question_text, "train", "randomforest"):
        return f"{language}::train_random_forest"
    if _contains_all(question_text, "fit", "random", "forest") or _contains_all(question_text, "fit", "randomforest"):
        return f"{language}::train_random_forest"
    if _contains_all(question_text, "correlation", "matrix"):
        return f"{language}::correlation_matrix"
    if _contains_all(question_text, "correlated", "features"):
        return f"{language}::top_correlated_features"
    if "multicollinearity" in question_text or (_contains_all(question_text, "correlation") and "0.9" in question_text):
        return f"{language}::multicollinearity_check"
    if _contains_all(question_text, "sort", "dataframe") and "descending" in question_text:
        return f"{language}::sort_dataframe_desc"
    if _contains_all(question_text, "datetime", "column", "year") and "pandas" in question_text:
        return f"{language}::datetime_to_year"
    if _contains_all(question_text, "sigmoid", "function") or _contains_all(question_text, "implement", "sigmoid"):
        return f"{language}::sigmoid_function"
    if _contains_all(question_text, "softmax", "function") or _contains_all(question_text, "implement", "softmax"):
        return f"{language}::softmax_function"
    if _contains_all(question_text, "binary", "cross", "entropy"):
        return f"{language}::binary_cross_entropy"
    if _contains_all(question_text, "gradient", "descent", "step"):
        return f"{language}::gradient_descent_step"
    if ("maximum" in question_text or "max" in question_text) and ("array" in question_text or "list" in question_text):
        return f"{language}::maximum_array"
    if ("minimum" in question_text or "min" in question_text) and ("array" in question_text or "list" in question_text):
        return f"{language}::minimum_array"
    if (_contains_all(question_text, "sum", "array")) or (_contains_all(question_text, "sum", "list")):
        return f"{language}::sum_collection"
    if _contains_all(question_text, "sum", "even", "numbers") and "list" in question_text:
        return f"{language}::sum_even_numbers"
    if (_contains_all(question_text, "first", "element")) and ("list" in question_text or "array" in question_text):
        return f"{language}::first_element"
    if (_contains_all(question_text, "last", "element")) and ("list" in question_text or "array" in question_text):
        return f"{language}::last_element"
    if ("list is empty" in question_text) or ("empty list" in question_text):
        return f"{language}::list_is_empty"
    if _contains_all(question_text, "remove", "duplicates") and "list" in question_text and "preserve order" in question_text:
        return f"{language}::remove_duplicates_preserve_order"
    if _contains_all(question_text, "contains", "duplicates"):
        return f"{language}::contains_duplicates"
    contains_value = _extract_list_contains_constant(question_text)
    if contains_value is not None:
        return f"{language}::list_contains_constant"
    if _contains_all(question_text, "list", "sorted"):
        return f"{language}::list_sorted"
    if _contains_all(question_text, "frequency", "elements") and "list" in question_text:
        return f"{language}::frequency_elements"
    if (
        "more than 3" in question_text
    ):
        return f"{language}::list_length_gt3"
    if (
        (
            re.search(r"(?:list|array)\s+length\s+(?:equals|equal to|is)\s+-?\d+", question_text)
            or re.search(r"(?:length|size)\s+(?:equals|equal to|is)\s+-?\d+", question_text)
            or re.search(r"(?:length|size).*(?:exactly)\s+([a-z0-9-]+)", question_text)
            or re.search(r"(?:exactly)\s+([a-z0-9-]+).*(?:length|size)", question_text)
            or re.search(r"(?:length|size)\s+(?:is\s+)?exactly\s+([a-z0-9-]+)", question_text)
        )
        and ("list" in question_text or "array" in question_text or "elements" in question_text)
    ):
        return f"{language}::list_length_equals_constant"
    list_length_comp = _extract_list_length_comparison(question_text)
    if (
        list_length_comp
        and ("list" in question_text or "array" in question_text or "elements" in question_text)
    ):
        return f"{language}::list_length_comparison_constant"
    if (
        (_contains_all(question_text, "length", "list"))
        or (_contains_all(question_text, "get", "length", "list"))
        or (_contains_all(question_text, "count", "elements") and "list" in question_text)
        or (_contains_all(question_text, "number", "elements") and "list" in question_text)
        or ("number of elements in list" in question_text)
    ):
        return f"{language}::list_length"
    if "array is empty" in question_text:
        return f"{language}::array_is_empty"
    if "array" in question_text:
        return f"{language}::array_ops"
    if "string" in question_text:
        return f"{language}::string_ops"
    if language in {"html", "css", "react", "mysql", "mongodb"}:
        return f"{language}::static_template"
    return f"{language}::generic"


def _infer_template_family_from_model_answer(model_answer, language):
    language = (language or "").strip().lower()
    answer = (model_answer or "").strip()
    compact = re.sub(r"\s+", "", answer.lower())

    if not answer or language != "python":
        return ""

    if ".upper()" in compact:
        return f"{language}::uppercase_string"
    if ".lower()" in compact:
        return f"{language}::lowercase_string"
    if ".endswith(" in compact:
        return f"{language}::string_endswith"
    if ".startswith(" in compact:
        return f"{language}::string_startswith"
    if "abs(" in compact:
        return f"{language}::absolute_value"
    prefix_slice_match = re.search(r"return[a-z_][a-z0-9_]*\[:(-?\d+)\]", compact) or re.search(r"return[a-z_][a-z0-9_]*\[0:(-?\d+)\]", compact)
    if prefix_slice_match:
        prefix_count = int(prefix_slice_match.group(1))
        if prefix_count == 2:
            return f"{language}::first_two_characters"
        if prefix_count > 0:
            return f"{language}::prefix_characters_constant"
    suffix_slice_match = re.search(r"return[a-z_][a-z0-9_]*\[(-?\d+):\]", compact)
    if suffix_slice_match:
        suffix_count = -int(suffix_slice_match.group(1))
        if suffix_count > 0:
            return f"{language}::suffix_characters_constant"
    if "returns[len(s)//2]" in compact:
        return f"{language}::middle_character"
    if "returns[:2]" in compact or "returns[0:2]" in compact:
        return f"{language}::first_two_characters"
    if re.search(r"returns\[0\]\+s\[-1\]", compact) or re.search(r"return[a-z_][a-z0-9_]*\[0\]\+[a-z_][a-z0-9_]*\[-1\]", compact):
        return f"{language}::first_and_last_character"
    if re.search(r"return(-?\d+)inlst", compact):
        return f"{language}::list_contains_constant"
    list_length_comp_match = re.search(r"len\(lst\)\s*([<>=!]+)\s*(-?\d+)", compact)
    if list_length_comp_match:
        operator = list_length_comp_match.group(1)
        if operator == "==":
            return f"{language}::list_length_equals_constant"
        return f"{language}::list_length_comparison_constant"
    if "len(lst)>0" in compact or "len(lst)!=0" in compact or "returnbool(lst)" in compact:
        return f"{language}::non_empty_collection_check"
    if "len(lst)==0" in compact or "returnnotlst" in compact:
        return f"{language}::empty_collection_check"
    if re.search(r"len\(lst\)==-?\d+", compact):
        return f"{language}::list_length_equals_constant"
    if "len(lst)" in compact:
        return f"{language}::list_length"
    if "n%2!=0" in compact or "n%2==1" in compact or "(n&1)==1" in compact:
        return f"{language}::odd_check"
    if "n==0" in compact or "returnnotn" in compact:
        return f"{language}::zero_check"
    if re.search(r"return[a-z_][a-z0-9_]*%(-?\d+)==0", compact) or re.search(r"returnn%(-?\d+)==0", compact):
        return f"{language}::divisible_by_constant"
    if re.search(r"return[a-z_][a-z0-9_]*>(-?\d+)", compact) or re.search(r"returnn>(-?\d+)", compact):
        return f"{language}::greater_than_threshold"
    if "returnlst[1]" in compact:
        return f"{language}::second_element"
    element_match = re.search(r"returnlst\[(-?\d+)\]", compact)
    if element_match:
        index = int(element_match.group(1))
        if index == 1:
            return f"{language}::second_element"
        if index == 0:
            return f"{language}::first_element"
        if index > 1:
            return f"{language}::element_at_index_constant"
    if "returnlst[0]" in compact:
        return f"{language}::first_element"
    if "returnlst[-1]" in compact or "returnlst[len(lst)-1]" in compact:
        return f"{language}::last_element"
    return ""


def _infer_best_template_family(question, model_answer, language):
    inferred = _infer_template_family(question, language)
    if _is_specific_template_family(inferred):
        return inferred
    from_model_answer = _infer_template_family_from_model_answer(model_answer, language)
    if from_model_answer:
        return from_model_answer
    if (language or "").strip().lower() == "python" and _extract_declared_callable_name(model_answer):
        return "python::model_answer_derived"
    return inferred


def _infer_template_family_with_llm(question, language):
    prompt = f"""
Return ONLY JSON in this exact shape:
{{"template_family":"{(language or '').strip().lower()}::..."}}

Rules:
- Use a specific family when possible (avoid ::generic, ::array_ops, ::string_ops).
- Use the given language prefix.
- If uncertain, return an empty string for template_family.

Question:
{question}
""".strip()
    raw = call_llm(prompt)
    parsed = _extract_first_json_object(raw)
    if not isinstance(parsed, dict):
        return None
    family = (parsed.get("template_family") or "").strip().lower()
    if not family:
        return None
    if not family.startswith(f"{(language or '').strip().lower()}::"):
        return None
    if family.endswith("::generic") or family.endswith("::array_ops") or family.endswith("::string_ops"):
        return None
    return family


def _normalize_test_case(item):
    if not isinstance(item, dict):
        return None
    raw_input = item.get("input")
    raw_expected = item.get("expected_output")
    if isinstance(raw_input, str):
        normalized_input = raw_input
        try:
            normalized_input = json.dumps(json.loads(raw_input), separators=(",", ":"))
        except Exception:
            pass
    else:
        normalized_input = json.dumps(raw_input, separators=(",", ":")) if raw_input is not None else None

    if isinstance(raw_expected, str):
        normalized_expected = raw_expected
        try:
            normalized_expected = json.dumps(json.loads(raw_expected), separators=(",", ":"))
        except Exception:
            pass
    else:
        normalized_expected = json.dumps(raw_expected, separators=(",", ":")) if raw_expected is not None else None

    return {
        "input": normalized_input,
        "expected_output": normalized_expected,
        "description": item.get("description"),
        "kind": (item.get("kind") or "normal").strip().lower() if isinstance(item.get("kind"), str) else "normal",
        "weight": float(item.get("weight", 1.0) or 1.0),
        "required": bool(item.get("required", False)),
    }


def _dedupe_tests_by_io(test_cases):
    deduped = []
    for item in test_cases:
        normalized = _normalize_test_case(item)
        if not normalized:
            continue
        key = (normalized.get("input"), normalized.get("expected_output"))
        existing = next((case for case in deduped if (case.get("input"), case.get("expected_output")) == key), None)
        if not existing:
            deduped.append(normalized)
            continue
        existing["required"] = existing.get("required", False) or normalized.get("required", False)
        existing["weight"] = max(existing.get("weight", 1.0), normalized.get("weight", 1.0))
        existing_kind = existing.get("kind", "normal")
        new_kind = normalized.get("kind", "normal")
        if existing_kind == "normal" and new_kind in {"edge", "trap"}:
            existing["kind"] = new_kind
        existing_desc = (existing.get("description") or "").strip()
        new_desc = (normalized.get("description") or "").strip()
        if (
            (not existing_desc and new_desc)
            or ("auto-generated deterministic oracle test" in existing_desc.lower() and new_desc)
        ):
            existing["description"] = normalized.get("description")
    return deduped


def _trim_oracle_positive_tests(test_cases):
    normalized_cases = [_normalize_test_case(item) for item in test_cases if _normalize_test_case(item)]
    if not normalized_cases:
        return []

    handcrafted = []
    oracle = []
    for item in normalized_cases:
        description = (item.get("description") or "").strip().lower()
        if "auto-generated deterministic oracle test" in description:
            oracle.append(item)
        else:
            handcrafted.append(item)

    if not handcrafted:
        return normalized_cases[:AUTO_GENERATE_MAX_HIDDEN_TESTS]

    target_count = max(3, len(handcrafted))
    trimmed = list(handcrafted)
    for item in oracle:
        if len(trimmed) >= min(target_count, AUTO_GENERATE_MAX_HIDDEN_TESTS):
            break
        trimmed.append(item)
    return trimmed[:AUTO_GENERATE_MAX_HIDDEN_TESTS]


def _normalize_incorrect_pattern(item):
    if not isinstance(item, dict):
        return None
    pattern = (item.get("pattern") or "").strip()
    if not pattern:
        return None
    return {
        "pattern": pattern,
        "match_type": (item.get("match_type") or "contains").strip().lower(),
        "feedback": (item.get("feedback") or "").strip(),
        "suggestion": (item.get("suggestion") or "").strip(),
        "score_cap": int(item.get("score_cap", 20) or 20),
    }


def _sanitize_incorrect_patterns_for_family(incorrect_patterns, template_family, question_text):
    sanitized = []
    normalized_family = (template_family or "").strip().lower()
    normalized_question = (question_text or "").strip().lower()

    for raw_item in incorrect_patterns or []:
        item = dict(raw_item)
        pattern_text = (item.get("pattern") or "").strip()
        compact_pattern = pattern_text.replace(" ", "").replace("\t", "").lower()

        if normalized_family == "python::lowercase_string" or "lowercase" in normalized_question:
            if compact_pattern in {"deflower(s):returns.lower", "deflower_text(s):returns.lower"} or "returns.lower" in compact_pattern:
                item["feedback"] = (
                    "Returning the lower method itself does not convert the input string. Call s.lower() to return the lowercase string."
                )
                item["suggestion"] = "Call s.lower() before returning the result."
                item["score_cap"] = int(item.get("score_cap", 20) or 20)
            elif (
                compact_pattern.startswith("deflower(")
                and 'return"' in compact_pattern
            ) or (
                compact_pattern.startswith("deflower_text(")
                and 'return"' in compact_pattern
            ):
                item["feedback"] = "Returning a constant string does not convert the input string to lowercase."
                item["suggestion"] = "Return the lowercase version of the provided input, for example with s.lower()."
                item["score_cap"] = int(item.get("score_cap", 20) or 20)

        if normalized_family == "python::second_element" or "second element" in normalized_question:
            if "returnlst[0]" in compact_pattern:
                item["feedback"] = (
                    "Returning the first element does not satisfy the second-element requirement. The task asks for the item at index 1, not the item at index 0."
                )
                item["suggestion"] = "Return the item at index 1, for example with lst[1]."
                item["score_cap"] = int(item.get("score_cap", 20) or 20)
            elif "returnlst[-1]" in compact_pattern:
                item["feedback"] = (
                    "Returning the last element does not satisfy the second-element requirement. The task asks for the item at index 1, not the final item in the list."
                )
                item["suggestion"] = "Return the item at index 1, for example with lst[1]."
                item["score_cap"] = int(item.get("score_cap", 20) or 20)
            elif compact_pattern in {"defsecond(lst):returnlst", "returnlst"}:
                item["feedback"] = (
                    "Returning the whole list does not return the second element. The task asks for a single item, so the function should return the value at index 1 instead of the entire list."
                )
                item["suggestion"] = "Return the item at index 1, for example with lst[1]."
                item["score_cap"] = int(item.get("score_cap", 20) or 20)

        sanitized.append(item)
    return sanitized


def _build_generation_prompt(question, model_answer, language, repair_context=None):
    repair_note = ""
    if repair_context:
        repair_note = f" Previous issue: {str(repair_context)[:180]}"
    return (
        "Return ONLY compact valid JSON for a coding-question evaluation package. "
        "No markdown. No explanation. If unsure, use empty arrays. "
        "Required schema: "
        '{"accepted_solutions":[],"test_sets":{"positive":[],"negative":[]},"incorrect_patterns":[]}. '
        "Each incorrect pattern object must use keys: pattern, match_type, feedback, suggestion, score_cap. "
        f"Limits: accepted_solutions <= {AUTO_GENERATE_MAX_ALTERNATIVES}; "
        f"positive tests <= {AUTO_GENERATE_MAX_HIDDEN_TESTS}; negative tests <= {AUTO_GENERATE_MAX_HIDDEN_TESTS}. "
        f"Language: {language}. Question: {question}. Model answer: {model_answer}.{repair_note}"
    ).strip()


def _build_generation_repair_prompt(raw_response):
    raw = re.sub(r"\s+", " ", str(raw_response or "")).strip()[:700]
    return (
        "Convert this response into ONLY compact valid JSON for this exact schema: "
        '{"accepted_solutions":[],"test_sets":{"positive":[],"negative":[]},"incorrect_patterns":[]}. '
        "Do not include score, rubric, feedback-only review, markdown, or explanation. "
        "If the response cannot be converted safely, return exactly "
        '{"accepted_solutions":[],"test_sets":{"positive":[],"negative":[]},"incorrect_patterns":[]}. '
        f"Response: {raw}"
    )


def _call_llm_for_registration_package(prompt):
    raw = call_llm(prompt)
    parsed = _extract_first_json_object(raw)
    if _is_registration_package_json(parsed):
        return parsed, "llm_generation"

    repair_attempts = max(0, int(QUESTION_REGISTER_LLM_REPAIR_ATTEMPTS or 0))
    for _ in range(repair_attempts):
        repaired_raw = call_llm(_build_generation_repair_prompt(raw))
        repaired = _extract_first_json_object(repaired_raw)
        if _is_registration_package_json(repaired):
            return repaired, "llm_generation_repair"
        raw = repaired_raw

    return None, None


def _dedupe_strings(items, limit=None):
    results = []
    for item in items or []:
        if isinstance(item, str):
            cleaned = item.strip()
            if cleaned and cleaned not in results:
                results.append(cleaned)
    return results[:limit] if limit else results


def _build_case(input_value, expected_output, description, kind="normal", weight=1.0, required=False):
    return {
        "input": json.dumps(input_value, separators=(",", ":")) if not isinstance(input_value, str) else input_value,
        "expected_output": json.dumps(expected_output, separators=(",", ":")) if not isinstance(expected_output, str) else expected_output,
        "description": description,
        "kind": kind,
        "weight": weight,
        "required": required,
    }


def _contains_all(text, *parts):
    lowered = (text or "").lower()
    return all(part in lowered for part in parts)


def _java_for_list_or_array(question_text, list_expr="", array_expr=""):
    lowered = (question_text or "").lower()
    if "list" in lowered and list_expr:
        return list_expr
    if "array" in lowered and array_expr:
        return array_expr
    return list_expr or array_expr or ""


def _javascript_for_collection(question_text, array_expr="", list_expr=""):
    lowered = (question_text or "").lower()
    if "array" in lowered and array_expr:
        return array_expr
    if "list" in lowered and list_expr:
        return list_expr
    return array_expr or list_expr or ""


def _html_expected_markers(question_text):
    lowered = (question_text or "").lower()
    markers = []
    if "html" in lowered:
        markers.append("<html")
    if "title" in lowered:
        markers.append("<title")
    if "heading" in lowered or "h1" in lowered:
        markers.append("<h1")
    if "button" in lowered:
        markers.append("<button")
    if "form" in lowered:
        markers.append("<form")
    if "input" in lowered:
        markers.append("<input")
    if "label" in lowered:
        markers.append("<label")
    if "textarea" in lowered:
        markers.append("<textarea")
    if "select" in lowered or "dropdown" in lowered:
        markers.append("<select")
    if "option" in lowered:
        markers.append("<option")
    if "table" in lowered:
        markers.append("<table")
    if "image" in lowered or "img" in lowered:
        markers.append("<img")
    if "audio" in lowered:
        markers.append("<audio")
    if "video" in lowered:
        markers.append("<video")
    if "link" in lowered or "anchor" in lowered:
        markers.append("<a")
    if "unordered list" in lowered or "ul" in lowered:
        markers.append("<ul")
    if "ordered list" in lowered or "ol" in lowered:
        markers.append("<ol")
    if "list item" in lowered or " li" in lowered:
        markers.append("<li")
    if "paragraph" in lowered or "<p" in lowered:
        markers.append("<p")
    if "div" in lowered or "container" in lowered:
        markers.append("<div")
    if "span" in lowered:
        markers.append("<span")
    if "br" in lowered or "line break" in lowered:
        markers.append("<br")
    if "semantic" in lowered or "header" in lowered or "footer" in lowered or "nav" in lowered or "section" in lowered:
        for marker in ("<header", "<nav", "<main", "<section", "<footer"):
            if marker not in markers:
                markers.append(marker)
    deduped = []
    for marker in markers:
        if marker not in deduped:
            deduped.append(marker)
    return deduped


def _css_expected_bits(question_text):
    lowered = (question_text or "").lower()
    bits = []
    if "red" in lowered:
        bits.append("red")
    if "blue" in lowered:
        bits.append("blue")
    if "green" in lowered:
        bits.append("green")
    if "color" in lowered:
        bits.append("color")
    if "background" in lowered:
        bits.append("background")
    if "font-size" in lowered or "font size" in lowered:
        bits.append("font-size")
    if "font-family" in lowered or "font family" in lowered:
        bits.append("font-family")
    if "font-weight" in lowered or "bold" in lowered:
        bits.append("font-weight")
    if "text-align" in lowered or "text align" in lowered:
        bits.append("text-align")
    if "text-decoration" in lowered or "underline" in lowered:
        bits.append("text-decoration")
    if "margin" in lowered:
        bits.append("margin")
    if "padding" in lowered:
        bits.append("padding")
    if "border" in lowered:
        bits.append("border")
    if "width" in lowered:
        bits.append("width")
    if "height" in lowered:
        bits.append("height")
    if "display" in lowered:
        bits.append("display")
    if "inline" in lowered:
        bits.append("inline")
    if "block" in lowered:
        bits.append("block")
    if "position" in lowered:
        bits.append("position")
    if "radius" in lowered or "rounded" in lowered:
        bits.append("border-radius")
    if "center" in lowered:
        bits.append("center")
    if "flex" in lowered:
        bits.append("display:flex")
    if "grid" in lowered:
        bits.append("display:grid")
    if "justify-content" in lowered or "justify content" in lowered:
        bits.append("justify-content")
    if "align-items" in lowered or "align items" in lowered:
        bits.append("align-items")
    if "hover" in lowered:
        bits.append(":hover")
    deduped = []
    for bit in bits:
        if bit not in deduped:
            deduped.append(bit)
    return deduped


def _react_expected_markers(question_text):
    lowered = (question_text or "").lower()
    markers = []
    if "usestate" in lowered or "state" in lowered:
        markers.append("useState")
    if "useeffect" in lowered or "effect" in lowered:
        markers.append("useEffect")
    if "props" in lowered:
        markers.append("props")
    if "list" in lowered and ("render" in lowered or "map" in lowered):
        markers.append(".map(")
    if "form" in lowered:
        markers.extend(["<form", "onSubmit"])
    if "input" in lowered:
        markers.append("<input")
    if "button" in lowered:
        markers.append("<button")
    if "click" in lowered or "event" in lowered or "button" in lowered:
        markers.append("onClick")
    if "conditional" in lowered or "show" in lowered or "hide" in lowered:
        markers.append("{")
    deduped = []
    for marker in markers:
        if marker not in deduped:
            deduped.append(marker)
    return deduped


def _mongodb_expected_markers(question_text):
    lowered = (question_text or "").lower()
    markers = []
    if "aggregate" in lowered or "$group" in lowered:
        markers.append("aggregate")
        if "$group" in lowered or "group" in lowered:
            markers.append("$group")
    if "find" in lowered:
        markers.append("find")
    if "sort" in lowered:
        markers.append("sort")
    if "project" in lowered or "projection" in lowered:
        markers.append("$project")
    if "match" in lowered or "filter" in lowered:
        markers.append("$match")
    if "update" in lowered or "$set" in lowered:
        markers.append("update")
    if "insert" in lowered:
        markers.append("insert")
    if "delete" in lowered:
        markers.append("delete")
    if "count" in lowered:
        markers.append("count")
    if "limit" in lowered:
        markers.append("limit")
    if "distinct" in lowered:
        markers.append("distinct")
    deduped = []
    for marker in markers:
        if marker not in deduped:
            deduped.append(marker)
    return deduped


def _mysql_expected_markers(question_text):
    lowered = (question_text or "").lower()
    markers = []
    if "select" in lowered or "find" in lowered or "show" in lowered:
        markers.append("select")
    if "where" in lowered or "filter" in lowered:
        markers.append("where")
    if "join" in lowered:
        markers.append("join")
    if "group by" in lowered or "count" in lowered or "sum" in lowered or "avg" in lowered or "aggregate" in lowered:
        markers.append("group by")
    if "order by" in lowered or "sort" in lowered:
        markers.append("order by")
    if "limit" in lowered:
        markers.append("limit")
    if "distinct" in lowered:
        markers.append("distinct")
    if "insert" in lowered:
        markers.append("insert")
    if "update" in lowered:
        markers.append("update")
    if "delete" in lowered:
        markers.append("delete")
    if "having" in lowered:
        markers.append("having")
    deduped = []
    for marker in markers:
        if marker not in deduped:
            deduped.append(marker)
    return deduped


def _extract_declared_callable_name(code):
    text = (code or "").strip()
    if not text:
        return None

    python_name = _extract_first_function_name(text)
    if python_name:
        return python_name

    javascript_match = re.search(
        r"\bfunction\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(",
        text,
    )
    if javascript_match:
        return javascript_match.group(1)

    java_match = re.search(
        r"\b(?:public|private|protected)?\s*(?:static\s+)?[A-Za-z_][A-Za-z0-9_<>\[\]]*\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(",
        text,
    )
    if java_match:
        return java_match.group(1)

    return None


def _is_answer_aligned_with_model(raw_answer, model_answer):
    answer_name = _extract_declared_callable_name(raw_answer)
    model_name = _extract_declared_callable_name(model_answer)
    if answer_name and model_name:
        return answer_name == model_name
    if not isinstance(raw_answer, str) or not isinstance(model_answer, str):
        return True

    model_params = []
    model_match = re.search(r"def\s+[A-Za-z_][A-Za-z0-9_]*\s*\(([^)]*)\)", model_answer)
    if model_match:
        params_text = model_match.group(1)
        for bit in params_text.split(","):
            name = bit.strip().split("=")[0].strip()
            if name:
                model_params.append(name)

    if model_params and "def " not in raw_answer and "function " not in raw_answer and "class " not in raw_answer:
        tokens = re.findall(r"\b[A-Za-z_][A-Za-z0-9_]*\b", raw_answer)
        keywords = {
            "return",
            "for",
            "in",
            "if",
            "else",
            "elif",
            "and",
            "or",
            "not",
            "true",
            "false",
            "none",
        }
        builtins = {
            "max",
            "min",
            "sum",
            "len",
            "sorted",
            "abs",
            "all",
            "any",
            "map",
            "filter",
            "list",
            "set",
            "dict",
            "tuple",
            "range",
            "enumerate",
            "reversed",
            "zip",
        }
        for token in tokens:
            lower = token.lower()
            if lower in keywords or lower in builtins:
                continue
            if token not in model_params:
                return False

    return True


def _is_pattern_aligned_with_model(pattern, model_answer):
    return _is_answer_aligned_with_model(pattern, model_answer)


def _deterministic_code_baselines(question, language):
    question_text = (question or "").lower()

    # High-frequency phrasing support. These used to short-circuit into empty baselines
    # and rely on model-answer parsing. That made registration brittle for new topics
    # (especially Java/JS) when the model answer didn't match a known pattern.
    if language in {"python", "java", "javascript"}:
        suffix_n = _extract_last_n_characters_count(question_text)
        if suffix_n and suffix_n > 0 and not _mentions_first_and_last_character(question_text):
            accepted = []
            if language == "python":
                accepted = [f"return s[-{suffix_n}:]"]
            elif language == "java":
                accepted = [f"return s.substring(Math.max(0, s.length() - {suffix_n}));"]
            elif language == "javascript":
                accepted = [f"return s.slice(-{suffix_n});"]
            return {
                "accepted_solutions": accepted,
                "test_sets": {
                    "positive": [
                        _build_case(["abcdefg"], "abcdefg"[-suffix_n:], f"basic last {suffix_n} characters", kind="normal", weight=1.0, required=True),
                        _build_case(["a"], "a"[-suffix_n:], "single character input stays safe", kind="edge", weight=1.1, required=True),
                    ],
                    "negative": [
                        _build_case([""], "", "empty string stays empty", kind="edge", weight=1.2, required=True),
                    ],
                },
                "incorrect_patterns": [
                    {
                        "pattern": "return s",
                        "match_type": "contains",
                        "feedback": "Returning the full string does not extract the requested suffix.",
                        "suggestion": f"Return only the last {suffix_n} characters, for example with slicing from the end.",
                        "score_cap": 20,
                    },
                    {
                        "pattern": "return s[:",
                        "match_type": "contains",
                        "feedback": "Returning a prefix does not satisfy a last-characters (suffix) requirement.",
                        "suggestion": f"Slice from the end to return the last {suffix_n} characters.",
                        "score_cap": 20,
                    },
                ],
            }

        llc = _extract_list_length_comparison(question_text)
        if llc and llc.get("value") is not None:
            op = llc.get("operator")
            val = int(llc.get("value"))
            accepted = []
            if language == "python":
                accepted = [f"return len(lst) {op} {val}"]
            elif language == "java":
                accepted = [f"return lst.length {op} {val};"]
            elif language == "javascript":
                accepted = [f"return lst.length {op} {val};"]
            def _cmp(length, operator, target):
                if operator == "<":
                    return length < target
                if operator == "<=":
                    return length <= target
                if operator == ">":
                    return length > target
                if operator == ">=":
                    return length >= target
                return False

            # Build one passing and one failing list deterministically.
            if op == "<":
                pass_len, fail_len = max(0, val - 1), val + 1
            elif op == "<=":
                pass_len, fail_len = max(0, val), val + 1
            elif op == ">":
                pass_len, fail_len = val + 1, max(0, val - 1)
            elif op == ">=":
                pass_len, fail_len = max(0, val), max(0, val - 1)
            else:
                pass_len, fail_len = max(0, val), val + 1

            passing_list = list(range(pass_len))
            failing_list = list(range(fail_len))
            return {
                "accepted_solutions": accepted,
                "test_sets": {
                    "positive": [
                        _build_case([passing_list], True, f"list length satisfies len(lst) {op} {val}", kind="normal", weight=1.0, required=True),
                        _build_case([[]], _cmp(0, op, val), "empty list edge case", kind="edge", weight=1.1, required=False),
                    ],
                    "negative": [
                        _build_case([failing_list], False, f"list length does not satisfy len(lst) {op} {val}", kind="normal", weight=1.0, required=True),
                    ],
                },
                "incorrect_patterns": [
                    {
                        "pattern": f"return len(lst) == {val}",
                        "match_type": "contains",
                        "feedback": "Using equality checks for an exact length, but the question requires a comparison.",
                        "suggestion": f"Compare the length with {op}, for example with len(lst) {op} {val}.",
                        "score_cap": 20,
                    },
                    {
                        "pattern": f"return len(lst) != {val}",
                        "match_type": "contains",
                        "feedback": "Using inequality does not match the required comparison in the question.",
                        "suggestion": f"Use len(lst) {op} {val} to match the requirement.",
                        "score_cap": 20,
                    },
                ],
            }

        multi_match = re.search(r"\bmultiple\s+of\s+(-?\d+)\b", question_text)
        if (
            multi_match
            and ("check" in question_text or "whether" in question_text or "is" in question_text)
            and not re.search(r"divisible\s+by\s+\d+", question_text)
        ):
            divisor = int(multi_match.group(1))
            accepted = []
            if language == "python":
                accepted = [f"return n % {divisor} == 0", f"return not n % {divisor}"]
            elif language == "java":
                accepted = [f"return n % {divisor} == 0;"]
            elif language == "javascript":
                accepted = [f"return n % {divisor} === 0;"]
            return {
                "accepted_solutions": accepted,
                "test_sets": {
                    "positive": [
                        _build_case([0], True, "zero is a multiple of the constant", kind="edge", weight=1.1, required=True),
                        _build_case([abs(divisor)], True, "exact multiple of constant", kind="normal", weight=1.0, required=True),
                    ],
                    "negative": [
                        _build_case([abs(divisor) + 1], False, "non-multiple of constant", kind="normal", weight=1.0, required=True),
                    ],
                },
                "incorrect_patterns": [
                    {
                        "pattern": f"return n % {divisor} != 0",
                        "match_type": "contains",
                        "feedback": f"Checking for a non-zero remainder solves the opposite problem. The function should return True only when the number is a multiple of {divisor}.",
                        "suggestion": f"Use n % {divisor} == 0 to check whether it is a multiple.",
                        "score_cap": 20,
                    },
                    {
                        "pattern": f"return n % {divisor} == 1",
                        "match_type": "contains",
                        "feedback": f"Checking whether the remainder is 1 does not determine whether the number is a multiple of {divisor}.",
                        "suggestion": f"Use n % {divisor} == 0 to check whether it is a multiple.",
                        "score_cap": 20,
                    },
                ],
            }

    divisible_match = re.search(r"divisible by\s+(-?\d+)", question_text)

    if divisible_match:
        divisor = int(divisible_match.group(1))
        accepted = []
        if language == "python":
            accepted = [f"return n % {divisor} == 0", f"return not n % {divisor}"]
        elif language == "java":
            accepted = [f"return n % {divisor} == 0;"]
        elif language == "javascript":
            accepted = [f"return n % {divisor} === 0;"]
        baseline = {
            "accepted_solutions": accepted,
            "test_sets": {
                "positive": [
                    _build_case([0], True, "zero is divisible by the divisor", kind="edge", weight=1.1, required=True),
                    _build_case([abs(divisor)], True, "exact multiple of divisor", kind="normal", weight=1.0, required=True),
                ],
                "negative": [
                    _build_case([abs(divisor) + 1], False, "non-multiple of divisor", kind="normal", weight=1.0, required=True),
                    _build_case([1], False, "value with remainder 1", kind="trap", weight=1.1, required=False),
                ],
            },
            "incorrect_patterns": [
                {
                    "pattern": f"return n % {divisor} != 0",
                    "match_type": "contains",
                    "feedback": f"Checking for a non-zero remainder solves the opposite problem. The function should return True only when the number is divisible by {divisor}.",
                    "suggestion": f"Use n % {divisor} == 0 to check divisibility.",
                    "score_cap": 20,
                },
                {
                    "pattern": f"return n % {divisor} == 1",
                    "match_type": "contains",
                    "feedback": f"Checking whether the remainder is 1 does not determine whether the number is divisible by {divisor}.",
                    "suggestion": f"Use n % {divisor} == 0 to check divisibility.",
                    "score_cap": 20,
                },
            ],
        }
        if divisor % 2 == 0 and abs(divisor) > 2:
            baseline["incorrect_patterns"].append(
                {
                    "pattern": "return n % 2 == 0",
                    "match_type": "contains",
                    "feedback": f"Checking divisibility by 2 includes extra even numbers that are not necessarily divisible by {divisor}.",
                    "suggestion": f"Use n % {divisor} == 0 so the divisor matches the question exactly.",
                    "score_cap": 20,
                }
            )
        return baseline

    if "factorial" in question_text:
        inverted_op = {"<": ">", ">": "<", "<=": ">=", ">=": "<=", "==": "!=", "!=": "=="}.get(op, op)
        return {
            "accepted_solutions": [
                "def fact(n):\n    if n == 0:\n        return 1\n    return n * fact(n - 1)" if language == "python" else "",
                "function fact(n){ if(n===0) return 1; return n * fact(n-1); }" if language == "javascript" else "",
                "if (n == 0) return 1; return n * fact(n - 1);" if language == "java" else "",
                "if(n <= 1) return 1; return n * fact(n - 1);" if language == "javascript" else "",
            ],
            "test_sets": {
                "positive": [
                    _build_case([0], 1, "base case", kind="edge", weight=1.5, required=True),
                    _build_case([1], 1, "small positive", kind="normal", weight=1.0),
                    _build_case([5], 120, "representative positive", kind="normal", weight=1.2, required=True),
                ],
                "negative": [
                    _build_case([3], 6, "non-trivial recursive or iterative case", kind="trap", weight=1.1),
                    _build_case([6], 720, "larger positive case", kind="edge", weight=1.2),
                ],
            },
            "incorrect_patterns": [
                {
                    "pattern": "return 1;",
                    "match_type": "contains",
                    "feedback": "Returning 1 for every input does not compute factorial values.",
                    "suggestion": "Handle the base case and multiply by smaller values for n > 1.",
                    "score_cap": 20,
                }
            ],
        }

    if _contains_all(question_text, "add", "two", "numbers"):
        return {
            "accepted_solutions": [
                "def add(a,b): return a + b" if language == "python" else "",
                "return a + b;" if language in {"javascript", "java"} else "",
                "return (a+b);" if language in {"javascript", "java"} else "",
                "def add(a,b): return a+b" if language == "python" else "",
            ],
            "test_sets": {
                "positive": [
                    _build_case([1, 2], 3, "small positive integers", kind="normal", weight=1.0, required=True),
                    _build_case([0, 5], 5, "zero plus positive", kind="edge", weight=1.1),
                ],
                "negative": [
                    _build_case([-2, 3], 1, "mixed sign values", kind="edge", weight=1.2, required=True),
                    _build_case([10, 15], 25, "larger integers", kind="normal", weight=1.0),
                    _build_case([100, -100], 0, "sum to zero", kind="trap", weight=1.1),
                ],
            },
            "incorrect_patterns": [
                {
                    "pattern": "return a;",
                    "match_type": "contains",
                    "feedback": "Returning only the first argument does not add the two inputs.",
                    "suggestion": "Return the sum of both input values.",
                    "score_cap": 20,
                },
                {
                    "pattern": "return b;",
                    "match_type": "contains",
                    "feedback": "Returning only the second argument does not add the two inputs.",
                    "suggestion": "Return the sum of both input values.",
                    "score_cap": 20,
                },
            ],
        }

    if _contains_all(question_text, "subtract", "two", "numbers") or _contains_all(question_text, "subtract", "numbers"):
        return {
            "accepted_solutions": ["return a - b;", "return (a-b);"],
            "test_sets": {
                "positive": [
                    _build_case([5, 2], 3, "basic subtraction", kind="normal", weight=1.0, required=True),
                    _build_case([2, 5], -3, "negative result subtraction", kind="edge", weight=1.1, required=True),
                ],
                "negative": [
                    _build_case([0, 7], -7, "zero minus positive", kind="trap", weight=1.0),
                ],
            },
            "incorrect_patterns": [
                {
                    "pattern": "return a + b",
                    "match_type": "contains",
                    "feedback": "Adding the two values does not perform subtraction.",
                    "suggestion": "Return a - b to compute the difference.",
                    "score_cap": 20,
                },
                {
                    "pattern": "return b - a",
                    "match_type": "contains",
                    "feedback": "Reversing the operands changes the subtraction result.",
                    "suggestion": "Subtract the second number from the first: a - b.",
                    "score_cap": 20,
                },
            ],
        }

    if _contains_all(question_text, "multiply", "two", "numbers") or _contains_all(question_text, "product", "two", "numbers"):
        return {
            "accepted_solutions": ["return a * b;", "return (a*b);"],
            "test_sets": {
                "positive": [
                    _build_case([3, 4], 12, "basic multiplication", kind="normal", weight=1.0, required=True),
                    _build_case([-2, 5], -10, "negative times positive", kind="edge", weight=1.1, required=True),
                ],
                "negative": [
                    _build_case([0, 7], 0, "zero multiplication", kind="trap", weight=1.0),
                ],
            },
            "incorrect_patterns": [
                {
                    "pattern": "return a + b",
                    "match_type": "contains",
                    "feedback": "Adding the numbers does not compute their product.",
                    "suggestion": "Use multiplication: a * b.",
                    "score_cap": 20,
                },
                {
                    "pattern": "return a - b",
                    "match_type": "contains",
                    "feedback": "Subtracting the numbers does not compute their product.",
                    "suggestion": "Use multiplication: a * b.",
                    "score_cap": 20,
                },
            ],
        }

    if _contains_all(question_text, "divide", "two", "numbers") or _contains_all(question_text, "division", "two", "numbers"):
        return {
            "accepted_solutions": ["return a / b;", "return (a/b);"],
            "test_sets": {
                "positive": [
                    _build_case([6, 3], 2, "basic division", kind="normal", weight=1.0, required=True),
                    _build_case([-8, 4], -2, "negative division", kind="edge", weight=1.1, required=True),
                ],
                "negative": [
                    _build_case([10, 5], 2, "exact division trap", kind="trap", weight=1.0),
                ],
            },
            "incorrect_patterns": [
                {
                    "pattern": "return a * b",
                    "match_type": "contains",
                    "feedback": "Multiplication does not compute the quotient.",
                    "suggestion": "Use division: a / b.",
                    "score_cap": 20,
                },
                {
                    "pattern": "return a + b",
                    "match_type": "contains",
                    "feedback": "Adding the numbers does not compute the quotient.",
                    "suggestion": "Use division: a / b.",
                    "score_cap": 20,
                },
            ],
        }

    if "cube of a number" in question_text or "return cube of a number" in question_text or _contains_all(question_text, "cube", "number"):
        return {
            "accepted_solutions": [
                "return n ** 3" if language == "python" else "",
                "return n*n*n" if language == "python" else "",
                "return n * n * n" if language == "python" else "",
                "return n * n * n;" if language == "java" else "",
                "return n * n * n;" if language == "javascript" else "",
                "return Math.pow(n, 3);" if language == "javascript" else "",
            ],
            "test_sets": {
                "positive": [
                    _build_case([2], 8, "positive cube case", kind="normal", weight=1.0, required=True),
                    _build_case([-3], -27, "negative cube case", kind="edge", weight=1.2, required=True),
                    _build_case([0], 0, "zero cube case", kind="edge", weight=1.1, required=True),
                ],
                "negative": [
                    _build_case([1], 1, "identity value trap", kind="trap", weight=0.8),
                    _build_case([4], 64, "distinguishes cube from square", kind="trap", weight=1.2, required=True),
                    _build_case([-2], -8, "preserves sign for odd power", kind="trap", weight=1.1, required=True),
                ],
            },
            "incorrect_patterns": [
                {
                    "pattern": "return n * n",
                    "match_type": "contains",
                    "feedback": "Multiplying the number by itself only computes the square, not the cube.",
                    "suggestion": "Multiply the number by itself three times, for example with n * n * n or n ** 3.",
                    "score_cap": 20,
                },
                {
                    "pattern": "return n + n + n",
                    "match_type": "contains",
                    "feedback": "Adding the number three times does not compute the cube.",
                    "suggestion": "Multiply the number by itself three times, for example with n * n * n or n ** 3.",
                    "score_cap": 20,
                },
                {
                    "pattern": "return abs(n) * abs(n) * abs(n)",
                    "match_type": "contains",
                    "feedback": "Using absolute values removes the negative sign, so negative inputs produce the wrong cube.",
                    "suggestion": "Cube the original value directly so negative inputs stay negative.",
                    "score_cap": 20,
                },
            ],
        }

    if "square of a number" in question_text or "return square of a number" in question_text or _contains_all(question_text, "square", "number"):
        return {
            "accepted_solutions": [
                "return n * n" if language == "python" else "",
                "return n ** 2" if language == "python" else "",
                "return n * n;" if language == "java" else "",
                "return n * n;" if language == "javascript" else "",
                "return Math.pow(n, 2);" if language == "javascript" else "",
                "return n ** 2;" if language == "javascript" else "",
            ],
            "test_sets": {
                "positive": [
                    _build_case([2], 4, "positive square case", kind="normal", weight=1.0, required=True),
                    _build_case([-3], 9, "negative square case", kind="edge", weight=1.3, required=True),
                    _build_case([0], 0, "zero square case", kind="edge", weight=1.2, required=True),
                ],
                "negative": [
                    _build_case([5], 25, "non-trivial square trap", kind="trap", weight=1.1),
                ],
            },
            "incorrect_patterns": [
                {
                    "pattern": "return n + n;",
                    "match_type": "contains",
                    "feedback": "Adding the number to itself does not compute its square.",
                    "suggestion": "Multiply the number by itself, for example with n * n.",
                    "score_cap": 20,
                }
            ],
        }

    if _contains_all(question_text, "reverse", "string"):
        return {
            "accepted_solutions": [
                "return s[::-1]" if language == "python" else "",
                "return ''.join(reversed(s))" if language == "python" else "",
                "return s.split('').reverse().join('')" if language == "javascript" else "",
                "return new StringBuilder(s).reverse().toString();" if language == "java" else "",
            ],
            "test_sets": {
                "positive": [
                    _build_case(["abc"], "cba", "simple lowercase string", kind="normal", weight=1.0, required=True),
                    _build_case(["racecar"], "racecar", "palindrome string", kind="edge", weight=1.0),
                ],
                "negative": [
                    _build_case(["hello world"], "dlrow olleh", "string with space", kind="normal", weight=1.2, required=True),
                    _build_case([""], "", "empty string", kind="edge", weight=1.3),
                    _build_case(["a"], "a", "single character string", kind="trap", weight=0.9),
                ],
            },
            "incorrect_patterns": [
                {
                    "pattern": "return s;",
                    "match_type": "contains",
                    "feedback": "Returning the original string does not reverse it.",
                    "suggestion": "Reverse the character order before returning the result.",
                    "score_cap": 20,
                }
            ],
        }

    if _contains_all(question_text, "reverse", "list") or _contains_all(question_text, "reverse", "array"):
        return {
            "accepted_solutions": [
                "return lst[::-1]" if language == "python" else "",
                "return list(reversed(lst))" if language == "python" else "",
                "Collections.reverse(list); return list;" if language == "java" else "",
                "List<Integer> rev = new ArrayList<>(list); Collections.reverse(rev); return rev;" if language == "java" else "",
                "return lst.slice().reverse();" if language == "javascript" else "",
                "return [...lst].reverse();" if language == "javascript" else "",
            ],
            "test_sets": {
                "positive": [
                    _build_case([[1, 2, 3]], [3, 2, 1], "basic list reversal", kind="normal", weight=1.0, required=True),
                    _build_case([[]], [], "empty list reversal", kind="edge", weight=1.2, required=True),
                ],
                "negative": [
                    _build_case([[5]], [5], "single element list", kind="edge", weight=1.0),
                    _build_case([[1, 1, 2]], [2, 1, 1], "list with duplicates", kind="trap", weight=1.1),
                ],
            },
            "incorrect_patterns": [
                {
                    "pattern": "return lst;",
                    "match_type": "contains",
                    "feedback": "Returning the original list does not reverse its order.",
                    "suggestion": "Reverse the list order before returning it.",
                    "score_cap": 20,
                },
                {
                    "pattern": "return sorted(",
                    "match_type": "contains",
                    "feedback": "Sorting the list is not the same as reversing its order.",
                    "suggestion": "Reverse the list instead of sorting it.",
                    "score_cap": 20,
                },
                {
                    "pattern": "return lst.sort",
                    "match_type": "contains",
                    "feedback": "Calling sort returns the list in sorted order, not reversed order.",
                    "suggestion": "Use a reverse operation such as slicing or reversed(...).",
                    "score_cap": 20,
                },
            ],
        }

    if _contains_all(question_text, "reverse", "words"):
        return {
            "accepted_solutions": [
                "return ' '.join(s.split()[::-1])" if language == "python" else "",
                'String[] parts = s.split(" "); Collections.reverse(Arrays.asList(parts)); return String.join(" ", parts);' if language == "java" else "",
                "return s.split(' ').reverse().join(' ');" if language == "javascript" else "",
            ],
            "test_sets": {
                "positive": [
                    _build_case(["hello world"], "world hello", "basic two-word reversal", kind="normal", weight=1.0, required=True),
                    _build_case(["one"], "one", "single word input", kind="edge", weight=1.0, required=True),
                ],
                "negative": [
                    _build_case(["a b c"], "c b a", "three-word reversal", kind="trap", weight=1.1),
                ],
            },
            "incorrect_patterns": [
                {
                    "pattern": "return s",
                    "match_type": "contains",
                    "feedback": "Returning the original string does not reverse the word order.",
                    "suggestion": "Split the sentence into words, reverse their order, then join them back together.",
                    "score_cap": 20,
                }
            ],
        }

    if _mentions_first_and_last_character(question_text):
        return {
            "accepted_solutions": [
                "return s[0] + s[-1]" if language == "python" else "",
                "return String.valueOf(s.charAt(0)) + s.charAt(s.length() - 1);" if language == "java" else "",
                "return s[0] + s[s.length - 1];" if language == "javascript" else "",
            ],
            "test_sets": {
                "positive": [
                    _build_case(["python"], "pn", "basic first and last character extraction", kind="normal", weight=1.0, required=True),
                    _build_case(["ab"], "ab", "two-character string returns both characters", kind="edge", weight=1.1, required=True),
                    _build_case(["x"], "xx", "single character is both first and last", kind="edge", weight=1.2, required=True),
                ],
                "negative": [
                    _build_case(["hello"], "ho", "catches first-character-only or last-character-only logic", kind="trap", weight=1.1, required=True),
                    _build_case(["code"], "ce", "catches middle-slice confusion", kind="trap", weight=1.0, required=False),
                ],
            },
            "incorrect_patterns": [
                {
                    "pattern": "return s[0]",
                    "match_type": "contains",
                    "feedback": "Returning only the first character does not satisfy the requirement to return both the first and last characters.",
                    "suggestion": "Combine the first and last characters, for example with s[0] + s[-1].",
                    "score_cap": 20,
                },
                {
                    "pattern": "return s[-1]",
                    "match_type": "contains",
                    "feedback": "Returning only the last character does not satisfy the requirement to return both the first and last characters.",
                    "suggestion": "Combine the first and last characters, for example with s[0] + s[-1].",
                    "score_cap": 20,
                },
                {
                    "pattern": "return s[:2]",
                    "match_type": "contains",
                    "feedback": "Returning the first two characters is different from returning the first and last characters.",
                    "suggestion": "Combine the first and last characters instead of slicing the prefix.",
                    "score_cap": 20,
                },
            ],
        }

    return {"accepted_solutions": [], "test_sets": {"positive": [], "negative": []}, "incorrect_patterns": []}


def _deterministic_markup_baselines(question, language):
    question_text = (question or "").lower()
    if language == "html":
        expected_markers = _html_expected_markers(question_text)
        positive_tests = [
            {"input": "static", "expected_output": "valid_html", "description": "well-formed html structure"},
            {"input": "static", "expected_output": "balanced_html", "description": "balanced opening and closing tags"},
        ]
        negative_tests = [
            {"input": "static", "expected_output": "required_markers", "description": "contains expected html tags from the question"},
            {"input": "static", "expected_output": "question_text_alignment", "description": "matches the requested html intent"},
        ]
        if "form" in question_text:
            positive_tests.append({"input": "static", "expected_output": "form_structure", "description": "contains form wrapper and controls"})
        if "table" in question_text:
            positive_tests.append({"input": "static", "expected_output": "table_structure", "description": "contains table rows and cells"})
        if "image" in question_text or "img" in question_text:
            positive_tests.append({"input": "static", "expected_output": "image_tag", "description": "contains an image element"})
            negative_tests.append({"input": "static", "expected_output": "alt_text", "description": "image includes alt text"})
        if "audio" in question_text:
            positive_tests.append({"input": "static", "expected_output": "audio_tag", "description": "contains an audio element"})
        if "video" in question_text:
            positive_tests.append({"input": "static", "expected_output": "video_tag", "description": "contains a video element"})
        if "link" in question_text or "anchor" in question_text:
            positive_tests.append({"input": "static", "expected_output": "anchor_tag", "description": "contains a hyperlink"})
            negative_tests.append({"input": "static", "expected_output": "href_attribute", "description": "link includes href attribute"})
        if "unordered list" in question_text or "ordered list" in question_text or "list item" in question_text:
            positive_tests.append({"input": "static", "expected_output": "list_structure", "description": "contains list wrapper and items"})
        if "button" in question_text:
            positive_tests.append({"input": "static", "expected_output": "button_tag", "description": "contains a button element"})
        if "heading" in question_text or "h1" in question_text:
            positive_tests.append({"input": "static", "expected_output": "heading_tag", "description": "contains a heading element"})
        if "paragraph" in question_text:
            positive_tests.append({"input": "static", "expected_output": "paragraph_tag", "description": "contains a paragraph element"})
        if "input" in question_text or "textarea" in question_text or "select" in question_text or "dropdown" in question_text or "label" in question_text:
            positive_tests.append({"input": "static", "expected_output": "input_structure", "description": "contains the requested input controls"})
        if "div" in question_text or "container" in question_text or "span" in question_text:
            positive_tests.append({"input": "static", "expected_output": "container_structure", "description": "contains basic container elements"})
        if "semantic" in question_text or "header" in question_text or "footer" in question_text or "nav" in question_text or "section" in question_text:
            positive_tests.append({"input": "static", "expected_output": "semantic_layout", "description": "uses semantic layout tags"})
        return {
            "accepted_solutions": [],
            "test_sets": {
                "positive": positive_tests,
                "negative": negative_tests,
            },
            "incorrect_patterns": [
                {
                    "pattern": marker,
                    "match_type": "contains",
                    "feedback": f"The submission is missing the expected HTML marker {marker}.",
                    "suggestion": "Use the semantic tag requested by the question.",
                    "score_cap": 40,
                }
                for marker in expected_markers
            ],
        }

    if language == "css":
        expected_bits = _css_expected_bits(question_text)
        positive_tests = [
            {"input": "static", "expected_output": "valid_css", "description": "valid css rule block"},
            {"input": "static", "expected_output": "balanced_css", "description": "balanced selector/declaration structure"},
        ]
        negative_tests = [
            {"input": "static", "expected_output": "required_properties", "description": "contains requested properties"},
            {"input": "static", "expected_output": "question_style_intent", "description": "matches the requested css intent"},
        ]
        if "flex" in question_text:
            positive_tests.append({"input": "static", "expected_output": "flex_layout", "description": "uses flex layout properties"})
        if "grid" in question_text:
            positive_tests.append({"input": "static", "expected_output": "grid_layout", "description": "uses grid layout properties"})
        if "font" in question_text or "typography" in question_text or "text-align" in question_text or "text align" in question_text:
            positive_tests.append({"input": "static", "expected_output": "typography_style", "description": "uses the requested typography properties"})
        if "margin" in question_text or "padding" in question_text or "spacing" in question_text:
            positive_tests.append({"input": "static", "expected_output": "spacing_style", "description": "uses spacing-related properties"})
        if "border" in question_text or "radius" in question_text or "rounded" in question_text:
            positive_tests.append({"input": "static", "expected_output": "border_style", "description": "uses border-related properties"})
        if "width" in question_text or "height" in question_text or "size" in question_text:
            positive_tests.append({"input": "static", "expected_output": "sizing_style", "description": "uses sizing properties"})
        if "display" in question_text or "inline" in question_text or "block" in question_text or "position" in question_text:
            positive_tests.append({"input": "static", "expected_output": "display_style", "description": "uses display or positioning properties"})
        if "hover" in question_text:
            positive_tests.append({"input": "static", "expected_output": "hover_rule", "description": "includes a hover state rule"})
        if "button" in question_text:
            positive_tests.append({"input": "static", "expected_output": "button_style", "description": "styles a button selector"})
        if "card" in question_text:
            positive_tests.append({"input": "static", "expected_output": "card_style", "description": "styles a card-like container"})
        if "center" in question_text:
            negative_tests.append({"input": "static", "expected_output": "center_alignment", "description": "uses an appropriate centering technique"})
        return {
            "accepted_solutions": [],
            "test_sets": {
                "positive": positive_tests,
                "negative": negative_tests,
            },
            "incorrect_patterns": [
                {
                    "pattern": bit,
                    "match_type": "contains",
                    "feedback": f"The stylesheet appears to miss the requested CSS detail '{bit}'.",
                    "suggestion": "Include the required selector/property/value from the question.",
                    "score_cap": 45,
                }
                for bit in expected_bits
            ],
        }

    if language == "react":
        expected_markers = _react_expected_markers(question_text)
        positive_tests = [
            {"input": "static", "expected_output": "valid_react", "description": "valid component syntax"},
            {"input": "static", "expected_output": "component_render", "description": "component renders valid JSX"},
        ]
        negative_tests = [
            {"input": "static", "expected_output": "jsx_return", "description": "returns JSX or equivalent UI output"},
            {"input": "static", "expected_output": "question_ui_intent", "description": "matches the requested react intent"},
        ]
        if "hook" in question_text or "usestate" in question_text or "useeffect" in question_text:
            positive_tests.append({"input": "static", "expected_output": "hook_usage", "description": "uses the requested React hook"})
            negative_tests.append({"input": "static", "expected_output": "hook_alignment", "description": "hook usage matches the requested behavior"})
        if "props" in question_text:
            positive_tests.append({"input": "static", "expected_output": "props_usage", "description": "component uses props"})
        if "list" in question_text and ("render" in question_text or "map" in question_text):
            positive_tests.append({"input": "static", "expected_output": "list_render", "description": "renders a list from data"})
            negative_tests.append({"input": "static", "expected_output": "key_usage", "description": "list items use stable keys"})
        if "form" in question_text:
            positive_tests.append({"input": "static", "expected_output": "form_structure", "description": "contains form and controlled inputs"})
            negative_tests.append({"input": "static", "expected_output": "form_event_path", "description": "form handles change or submit events"})
        if "conditional" in question_text or "show" in question_text or "hide" in question_text:
            positive_tests.append({"input": "static", "expected_output": "conditional_render", "description": "includes conditional UI logic"})
        if "click" in question_text or "button" in question_text or "event" in question_text:
            positive_tests.append({"input": "static", "expected_output": "event_handler", "description": "includes the requested event handler"})
        return {
            "accepted_solutions": [],
            "test_sets": {
                "positive": positive_tests,
                "negative": negative_tests,
            },
            "incorrect_patterns": [
                {
                    "pattern": marker,
                    "match_type": "contains",
                    "feedback": f"The component appears to miss the expected React marker '{marker}'.",
                    "suggestion": "Include the requested hook, JSX structure, props, or event path from the question.",
                    "score_cap": 45,
                }
                for marker in expected_markers
            ],
        }

    if language == "mysql":
        expected_markers = _mysql_expected_markers(question_text)
        positive_tests = [
            {"input": "static", "expected_output": "valid_sql", "description": "recognizable sql statement"},
            {"input": "static", "expected_output": "balanced_sql", "description": "balanced query structure"},
        ]
        negative_tests = [
            {"input": "static", "expected_output": "question_intent", "description": "contains key sql clauses from the question intent"},
            {"input": "static", "expected_output": "operation_alignment", "description": "matches the requested SQL operation"},
        ]
        if "join" in question_text:
            positive_tests.append({"input": "seeded", "expected_output": "joined_rows", "description": "returns expected joined rows"})
            positive_tests.append({"input": "seeded", "expected_output": "column_projection", "description": "returns requested join columns"})
            negative_tests.append({"input": "seeded", "expected_output": "join_condition", "description": "uses an appropriate join condition"})
            negative_tests.append({"input": "seeded", "expected_output": "row_count_alignment", "description": "does not duplicate or drop expected rows"})
        if "group by" in question_text or "count" in question_text or "sum" in question_text or "avg" in question_text or "aggregate" in question_text:
            positive_tests.append({"input": "seeded", "expected_output": "group_aggregate", "description": "uses grouping or aggregation correctly"})
        if "order by" in question_text or "sort" in question_text:
            positive_tests.append({"input": "seeded", "expected_output": "order_clause", "description": "includes ordering behavior"})
        if "having" in question_text:
            positive_tests.append({"input": "seeded", "expected_output": "having_clause", "description": "uses a having clause after grouping"})
        if "distinct" in question_text:
            positive_tests.append({"input": "seeded", "expected_output": "distinct_clause", "description": "uses a distinct selection"})
        if "limit" in question_text:
            positive_tests.append({"input": "seeded", "expected_output": "limit_clause", "description": "uses a limit clause"})
        if "insert" in question_text:
            positive_tests.append({"input": "seeded", "expected_output": "insert_statement", "description": "uses an insert statement"})
        if "update" in question_text:
            positive_tests.append({"input": "seeded", "expected_output": "update_statement", "description": "uses an update statement"})
        if "delete" in question_text:
            positive_tests.append({"input": "seeded", "expected_output": "delete_statement", "description": "uses a delete statement"})
        if "select" in question_text or "where" in question_text or "filter" in question_text:
            positive_tests.append({"input": "seeded", "expected_output": "select_query", "description": "uses a select/filter query"})
        return {
            "accepted_solutions": [],
            "test_sets": {
                "positive": positive_tests,
                "negative": negative_tests,
            },
            "incorrect_patterns": [
                {
                    "pattern": marker,
                    "match_type": "contains",
                    "feedback": f"The SQL query appears to miss the expected clause '{marker}'.",
                    "suggestion": "Include the required SQL clause or operation from the question.",
                    "score_cap": 45,
                }
                for marker in expected_markers
            ],
        }

    if language == "mongodb":
        expected_markers = _mongodb_expected_markers(question_text)
        positive_tests = [
            {"input": "static", "expected_output": "valid_mongodb", "description": "recognizable mongodb command"},
            {"input": "static", "expected_output": "balanced_mongodb", "description": "balanced mongodb query structure"},
        ]
        negative_tests = [
            {"input": "static", "expected_output": "question_intent", "description": "contains key mongodb operations from the question intent"},
            {"input": "static", "expected_output": "operation_alignment", "description": "matches the requested mongodb operation"},
        ]
        if "aggregate" in question_text or "$group" in question_text:
            positive_tests.append({"input": "seeded", "expected_output": "aggregation_result", "description": "returns expected aggregation result"})
            positive_tests.append({"input": "seeded", "expected_output": "pipeline_shape", "description": "uses the requested pipeline shape"})
            negative_tests.append({"input": "seeded", "expected_output": "group_stage", "description": "includes grouping or aggregation logic"})
            negative_tests.append({"input": "seeded", "expected_output": "field_alignment", "description": "matches requested mongodb fields"})
        if "find" in question_text:
            positive_tests.append({"input": "seeded", "expected_output": "find_query", "description": "uses a mongodb find query"})
        if "insert" in question_text:
            positive_tests.append({"input": "seeded", "expected_output": "insert_clause", "description": "uses an insert operation"})
        if "sort" in question_text:
            positive_tests.append({"input": "seeded", "expected_output": "sort_clause", "description": "includes sort behavior"})
        if "project" in question_text or "projection" in question_text:
            positive_tests.append({"input": "seeded", "expected_output": "projection_fields", "description": "projects the requested fields"})
        if "update" in question_text or "$set" in question_text:
            positive_tests.append({"input": "seeded", "expected_output": "update_clause", "description": "includes update behavior"})
        if "delete" in question_text or "remove" in question_text:
            positive_tests.append({"input": "seeded", "expected_output": "delete_clause", "description": "uses a delete operation"})
        if "count" in question_text:
            positive_tests.append({"input": "seeded", "expected_output": "count_clause", "description": "uses a count operation"})
        if "limit" in question_text:
            positive_tests.append({"input": "seeded", "expected_output": "limit_clause", "description": "uses a limit operation"})
        if "distinct" in question_text:
            positive_tests.append({"input": "seeded", "expected_output": "distinct_clause", "description": "uses a distinct operation"})
        return {
            "accepted_solutions": [],
            "test_sets": {
                "positive": positive_tests,
                "negative": negative_tests,
            },
            "incorrect_patterns": [
                {
                    "pattern": marker,
                    "match_type": "contains",
                    "feedback": f"The MongoDB command appears to miss the expected marker '{marker}'.",
                    "suggestion": "Include the required MongoDB stage or operation from the question.",
                    "score_cap": 45,
                }
                for marker in expected_markers
            ],
        }

    return {"accepted_solutions": [], "test_sets": {"positive": [], "negative": []}, "incorrect_patterns": []}


def _build_python_oracle_baseline_from_model_answer(model_answer):
    answer = (model_answer or "").strip()
    if not answer:
        return {"accepted_solutions": [], "test_sets": {"positive": [], "negative": []}, "incorrect_patterns": []}

    fn_name = _extract_first_function_name(answer)
    wrapped_code, wrapped_name = _wrap_python_snippet(answer, "")
    function_name = wrapped_name or fn_name
    if not wrapped_code or not function_name:
        return {"accepted_solutions": [], "test_sets": {"positive": [], "negative": []}, "incorrect_patterns": []}

    signature_match = re.search(r"def\s+[A-Za-z_][A-Za-z0-9_]*\s*\(([^)]*)\)", answer)
    params = []
    if signature_match:
        for bit in signature_match.group(1).split(","):
            name = bit.strip().split("=")[0].strip()
            if name:
                params.append(name)
    param_count = len(params)
    primary = params[0] if params else "x"

    sample_inputs = []
    if param_count == 1:
        sample_inputs = [
            (0,),
            (1,),
            (2,),
            (-1,),
            ("",),
            ("Ab",),
            ("hello",),
            ([1, 2, 3],),
            ([],),
            (True,),
            (False,),
        ]
    elif param_count == 2:
        sample_inputs = [
            (0, 0),
            (1, 2),
            (2, 3),
            (-1, 4),
            ("a", "B"),
            ("hello", ""),
            ([1, 2], [3]),
            (True, False),
        ]
    else:
        return {
            "accepted_solutions": [answer],
            "test_sets": {"positive": [], "negative": []},
            "incorrect_patterns": [
                {
                    "pattern": "return True",
                    "match_type": "contains",
                    "feedback": "Always returning True does not implement the required logic for this question.",
                    "suggestion": "Use the input and the faculty model answer pattern to compute the expected result.",
                    "score_cap": 20,
                },
                {
                    "pattern": f"return {primary}",
                    "match_type": "contains",
                    "feedback": "Returning the input directly does not implement the required transformation or check for this question.",
                    "suggestion": "Compute the result from the input instead of returning it unchanged.",
                    "score_cap": 20,
                },
            ],
        }

    result = _run_code_with_timeout(wrapped_code, function_name, sample_inputs)
    outputs = (result or {}).get("outputs") or []
    positives = []
    seen_io = set()

    for args, output in zip(sample_inputs, outputs):
        if not isinstance(output, dict) or not output.get("ok"):
            continue
        rendered_input = list(args)
        expected = output.get("result")
        key = (json.dumps(rendered_input, sort_keys=True, default=str), json.dumps(expected, sort_keys=True, default=str))
        if key in seen_io:
            continue
        seen_io.add(key)
        positives.append(
            _build_case(
                rendered_input,
                expected,
                "Oracle-derived faculty model answer test",
                kind="normal" if len(positives) == 0 else "edge",
                weight=1.0 if len(positives) == 0 else 1.1,
                required=len(positives) < 2,
            )
        )
        if len(positives) >= 3:
            break

    return {
        "accepted_solutions": [answer],
        "test_sets": {"positive": positives, "negative": []},
        "incorrect_patterns": [
            {
                "pattern": "return True",
                "match_type": "contains",
                "feedback": "Always returning True does not implement the required logic for this question.",
                "suggestion": "Use the input and the faculty model answer pattern to compute the expected result.",
                "score_cap": 20,
            },
            {
                "pattern": f"return {primary}",
                "match_type": "contains",
                "feedback": "Returning the input directly does not implement the required transformation or check for this question.",
                "suggestion": "Compute the result from the input instead of returning it unchanged.",
                "score_cap": 20,
            },
        ],
    }


def _python_model_answer_baselines(model_answer, question_text=None, language="python"):
    compact = re.sub(r"\s+", "", (model_answer or "").lower())
    if not compact:
        return {"accepted_solutions": [], "test_sets": {"positive": [], "negative": []}, "incorrect_patterns": []}

    prefix_match = re.search(r"return[a-z_][a-z0-9_]*\[:(-?\d+)\]", compact) or re.search(r"return[a-z_][a-z0-9_]*\[0:(-?\d+)\]", compact)
    if prefix_match:
        prefix_count = int(prefix_match.group(1))
        if prefix_count > 0 and prefix_count != 2:
            return {
                "accepted_solutions": [f"return s[:{prefix_count}]"],
                "test_sets": {
                    "positive": [
                        _build_case(["abcdef"], "abcdef"[:prefix_count], f"basic first {prefix_count} characters", kind="normal", weight=1.0, required=True),
                        _build_case(["ab"], "ab"[:prefix_count], "shorter string input", kind="edge", weight=1.1, required=True),
                        _build_case([""], "", "empty string stays empty", kind="edge", weight=1.2, required=True),
                    ],
                    "negative": [
                        _build_case(["xyzuvw"], "xyzuvw"[:prefix_count], "catches off-by-one prefix logic", kind="trap", weight=1.0, required=True),
                    ],
                },
                "incorrect_patterns": [
                    {
                        "pattern": f"return s[:{max(1, prefix_count - 1)}]",
                        "match_type": "contains",
                        "feedback": f"Returning fewer than {prefix_count} characters does not satisfy the requirement to return the first {prefix_count} characters of the string.",
                        "suggestion": f"Return a slice of the first {prefix_count} characters, for example with s[:{prefix_count}].",
                        "score_cap": 20,
                    },
                    {
                        "pattern": f"return s[:{prefix_count + 1}]",
                        "match_type": "contains",
                        "feedback": f"Returning more than {prefix_count} characters does not satisfy the requirement to return exactly the first {prefix_count} characters.",
                        "suggestion": f"Return a slice of the first {prefix_count} characters, for example with s[:{prefix_count}].",
                        "score_cap": 20,
                    },
                ],
            }

    if "returns[:2]" in compact:
        return {
            "accepted_solutions": ["return s[:2]"],
            "test_sets": {
                "positive": [
                    _build_case(["abcd"], "ab", "basic first two characters", kind="normal", weight=1.0, required=True),
                    _build_case(["a"], "a", "single character input", kind="edge", weight=1.1, required=True),
                    _build_case([""], "", "empty string stays empty", kind="edge", weight=1.2, required=True),
                ],
                "negative": [
                    _build_case(["xyz"], "xy", "catches first-character-only logic", kind="trap", weight=1.0, required=True),
                    _build_case(["hello"], "he", "catches returning too many characters", kind="trap", weight=1.0, required=False),
                ],
            },
            "incorrect_patterns": [
                {
                    "pattern": "return s[0]",
                    "match_type": "contains",
                    "feedback": "Returning only the first character does not satisfy the requirement to return the first two characters of the string.",
                    "suggestion": "Return a slice of the first two characters, for example with s[:2].",
                    "score_cap": 20,
                },
                {
                    "pattern": "return s[:1]",
                    "match_type": "contains",
                    "feedback": "Returning only one character does not satisfy the requirement to return the first two characters of the string.",
                    "suggestion": "Return a slice of the first two characters, for example with s[:2].",
                    "score_cap": 20,
                },
                {
                    "pattern": "return s[:3]",
                    "match_type": "contains",
                    "feedback": "Returning three characters does not satisfy the requirement to return exactly the first two characters.",
                    "suggestion": "Return a slice of the first two characters, for example with s[:2].",
                    "score_cap": 20,
                },
            ],
        }

    if "returns[len(s)//2]" in compact:
        return {
            "accepted_solutions": ["return s[len(s)//2]"],
            "test_sets": {
                "positive": [
                    _build_case(["abc"], "b", "basic odd-length string middle character", kind="normal", weight=1.0, required=True),
                    _build_case(["hello"], "l", "longer odd-length string", kind="edge", weight=1.1, required=True),
                    _build_case(["x"], "x", "single-character string", kind="edge", weight=1.2, required=True),
                ],
                "negative": [
                    _build_case(["radar"], "d", "catches first/last-character confusion", kind="trap", weight=1.0, required=True),
                ],
            },
            "incorrect_patterns": [
                {
                    "pattern": "return s[0]",
                    "match_type": "contains",
                    "feedback": "Returning the first character does not satisfy the requirement to return the middle character of the string.",
                    "suggestion": "Index into the center of the string, for example with s[len(s)//2].",
                    "score_cap": 20,
                },
                {
                    "pattern": "return s[-1]",
                    "match_type": "contains",
                    "feedback": "Returning the last character does not satisfy the requirement to return the middle character of the string.",
                    "suggestion": "Index into the center of the string, for example with s[len(s)//2].",
                    "score_cap": 20,
                },
                {
                    "pattern": "return s",
                    "match_type": "contains",
                    "feedback": "Returning the whole string does not extract the middle character.",
                    "suggestion": "Return only the center character, for example with s[len(s)//2].",
                    "score_cap": 20,
                },
            ],
        }

    if ".lower()" in compact:
        return {
            "accepted_solutions": ["return s.lower()"],
            "test_sets": {
                "positive": [
                    _build_case(["AB"], "ab", "uppercase to lowercase", kind="normal", weight=1.0, required=True),
                    _build_case([""], "", "empty string lowercase", kind="edge", weight=1.2, required=True),
                ],
                "negative": [
                    _build_case(["Ab"], "ab", "mixed-case normalization", kind="trap", weight=1.1, required=False),
                ],
            },
            "incorrect_patterns": [
                {
                    "pattern": "return s",
                    "match_type": "contains",
                    "feedback": "Returning the original string does not convert it to lowercase.",
                    "suggestion": "Call s.lower() before returning the result.",
                    "score_cap": 20,
                }
            ],
        }

    threshold_match = re.search(r"return[a-z_][a-z0-9_]*>(-?\d+)|returnn>(-?\d+)", compact)
    if threshold_match:
        threshold_text = threshold_match.group(1) or threshold_match.group(2)
        threshold = int(threshold_text)
        return {
            "accepted_solutions": [f"return n > {threshold}"],
            "test_sets": {
                "positive": [
                    _build_case([threshold + 1], True, "value above threshold", kind="normal", weight=1.0, required=True),
                    _build_case([threshold + 5], True, "larger value above threshold", kind="edge", weight=1.1, required=False),
                ],
                "negative": [
                    _build_case([threshold], False, "threshold itself is not greater", kind="edge", weight=1.2, required=True),
                    _build_case([threshold - 1], False, "value below threshold", kind="normal", weight=1.0, required=True),
                ],
            },
            "incorrect_patterns": [
                {
                    "pattern": f"return n >= {threshold}",
                    "match_type": "contains",
                    "feedback": f"Using >= includes {threshold}, so the function also returns True for the threshold itself. The question requires numbers strictly greater than {threshold}, so use a strict greater-than comparison.",
                    "suggestion": f"Use n > {threshold} so the threshold value itself returns False.",
                    "score_cap": 20,
                },
                {
                    "pattern": f"return n < {threshold}",
                    "match_type": "contains",
                    "feedback": f"Checking whether the value is less than {threshold} solves the opposite problem. The question asks you to identify values greater than {threshold}, not smaller ones.",
                    "suggestion": f"Use n > {threshold} so only values above the threshold return True.",
                    "score_cap": 20,
                },
            ],
        }

    divisor_match = re.search(r"return[a-z_][a-z0-9_]*%(-?\d+)==0|returnn%(-?\d+)==0", compact)
    if divisor_match:
        divisor_text = divisor_match.group(1) or divisor_match.group(2)
        divisor = int(divisor_text)
        baseline = {
            "accepted_solutions": [f"return n % {divisor} == 0"],
            "test_sets": {
                "positive": [
                    _build_case([0], True, "zero is divisible by the divisor", kind="edge", weight=1.1, required=True),
                    _build_case([abs(divisor)], True, "exact multiple of divisor", kind="normal", weight=1.0, required=True),
                ],
                "negative": [
                    _build_case([abs(divisor) + 1], False, "non-multiple of divisor", kind="normal", weight=1.0, required=True),
                    _build_case([1], False, "value with remainder 1", kind="trap", weight=1.1, required=False),
                ],
            },
            "incorrect_patterns": [
                {
                    "pattern": f"return n % {divisor} != 0",
                    "match_type": "contains",
                    "feedback": f"Checking for a non-zero remainder solves the opposite problem. The function should return True only when the number is divisible by {divisor}.",
                    "suggestion": f"Use n % {divisor} == 0 to check divisibility.",
                    "score_cap": 20,
                },
                {
                    "pattern": f"return n % {divisor} == 1",
                    "match_type": "contains",
                    "feedback": f"Checking whether the remainder is 1 does not determine whether the number is divisible by {divisor}.",
                    "suggestion": f"Use n % {divisor} == 0 to check divisibility.",
                    "score_cap": 20,
                },
            ],
        }
        if divisor % 2 == 0 and abs(divisor) > 2:
            baseline["incorrect_patterns"].append(
                {
                    "pattern": "return n % 2 == 0",
                    "match_type": "contains",
                    "feedback": f"Checking divisibility by 2 includes extra even numbers that are not necessarily divisible by {divisor}.",
                    "suggestion": f"Use n % {divisor} == 0 so the divisor matches the question exactly.",
                    "score_cap": 20,
                }
            )
        return baseline

    equals_length_match = re.search(r"len\(lst\)==(-?\d+)", compact)
    if equals_length_match:
        target_length = int(equals_length_match.group(1))
        lower_length = target_length - 1 if target_length > 0 else 1
        upper_length = target_length + 1
        exact_list = list(range(target_length)) if target_length >= 0 else []
        higher_list = list(range(upper_length))
        lower_list = list(range(lower_length)) if lower_length >= 0 else []
        return {
            "accepted_solutions": [f"return len(lst) == {target_length}"],
            "test_sets": {
                "positive": [
                    _build_case([exact_list], True, f"list length equals {target_length}", kind="normal", weight=1.1, required=True),
                    _build_case([list(reversed(exact_list))], True, f"different list with length {target_length}", kind="normal", weight=1.0, required=False),
                ],
                "negative": [
                    _build_case([lower_list], False, f"list length below {target_length}", kind="edge", weight=1.2, required=True),
                    _build_case([higher_list], False, f"list length above {target_length}", kind="edge", weight=1.2, required=True),
                ],
            },
            "incorrect_patterns": [
                {
                    "pattern": f"return len(lst) > {target_length}",
                    "match_type": "contains",
                    "feedback": f"Checking whether the list length is greater than {target_length} solves a different problem. This task requires the length to be exactly {target_length}.",
                    "suggestion": f"Use len(lst) == {target_length} to require the exact length.",
                    "score_cap": 20,
                },
                {
                    "pattern": f"return len(lst) >= {target_length}",
                    "match_type": "contains",
                    "feedback": f"Using >= allows lists longer than {target_length}, but this task requires the length to be exactly {target_length}.",
                    "suggestion": f"Use len(lst) == {target_length} to require the exact length.",
                    "score_cap": 20,
                },
                {
                    "pattern": "return len(lst)",
                    "match_type": "contains",
                    "feedback": "Returning the list length itself does not answer the yes-or-no question. The function should return a boolean indicating whether the length matches the required value.",
                    "suggestion": f"Compare the length to {target_length}, for example with len(lst) == {target_length}.",
                    "score_cap": 20,
                },
            ],
        }

    element_match = re.search(r"returnlst\[(-?\d+)\]", compact)
    if element_match:
        index = int(element_match.group(1))
        if index > 1:
            position = index + 1
            first_list = list(range(1, max(4, position + 3)))
            second_list = list(range(10, 10 + max(4, position + 3)))
            return {
                "accepted_solutions": [f"return lst[{index}]"],
                "test_sets": {
                    "positive": [
                        _build_case([first_list], first_list[index], f"basic element at position {position}", kind="normal", weight=1.0, required=True),
                        _build_case([second_list], second_list[index], "different values same position", kind="edge", weight=1.1, required=True),
                    ],
                    "negative": [
                        _build_case([list(range(20, 20 + max(4, position + 3)))], list(range(20, 20 + max(4, position + 3)))[index], "catches neighboring index confusion", kind="trap", weight=1.0, required=True),
                    ],
                },
                "incorrect_patterns": [
                    {
                        "pattern": f"return lst[{max(0, index - 1)}]",
                        "match_type": "contains",
                        "feedback": f"Returning the item at index {max(0, index - 1)} does not satisfy the requirement to return the element at position {position}.",
                        "suggestion": f"Return the item at index {index}, for example with lst[{index}].",
                        "score_cap": 20,
                    },
                    {
                        "pattern": f"return lst[{index + 1}]",
                        "match_type": "contains",
                        "feedback": f"Returning the item after the required position does not satisfy the requirement to return the element at position {position}.",
                        "suggestion": f"Return the item at index {index}, for example with lst[{index}].",
                        "score_cap": 20,
                    },
                ],
            }

    if "returnlst[1]" in compact:
        return {
            "accepted_solutions": ["return lst[1]"],
            "test_sets": {
                "positive": [
                    _build_case([[1, 2, 3]], 2, "basic second element", kind="normal", weight=1.0, required=True),
                    _build_case([[7, 9]], 9, "two-element list", kind="edge", weight=1.1, required=True),
                ],
                "negative": [
                    _build_case([[9, 3, 1]], 3, "catches first-element confusion", kind="trap", weight=1.0, required=True),
                    _build_case([[4, 5, 6, 1]], 5, "catches last-element confusion", kind="trap", weight=1.1, required=False),
                ],
            },
            "incorrect_patterns": [
                {
                    "pattern": "return lst[0]",
                    "match_type": "contains",
                    "feedback": "Returning the first element does not satisfy the second-element requirement. The task asks for the item at index 1, not the item at index 0.",
                    "suggestion": "Return the item at index 1, for example with lst[1].",
                    "score_cap": 20,
                },
                {
                    "pattern": "return lst[-1]",
                    "match_type": "contains",
                    "feedback": "Returning the last element does not satisfy the second-element requirement. The task asks for the item at index 1, not the final item in the list.",
                    "suggestion": "Return the item at index 1, for example with lst[1].",
                    "score_cap": 20,
                },
            ],
        }

    suffix_character_count = _extract_last_n_characters_count(question_text)
    if suffix_character_count and suffix_character_count > 0:
        return {
            "accepted_solutions": [
                f"return s[-{suffix_character_count}:]" if language == "python" else "",
                f"return s.substring(Math.max(0, s.length() - {suffix_character_count}));" if language == "java" else "",
                f"return s.slice(-{suffix_character_count});" if language == "javascript" else "",
            ],
            "test_sets": {
                "positive": [
                    _build_case(["abcdefg"], "abcdefg"[-suffix_character_count:], f"basic last {suffix_character_count} characters", kind="normal", weight=1.0, required=True),
                    _build_case(["a"], "a"[-suffix_character_count:], "single character input stays safe", kind="edge", weight=1.1, required=True),
                    _build_case(["ab"], "ab"[-suffix_character_count:], "exact-length string input", kind="edge", weight=1.0, required=True),
                    _build_case([""], "", "empty string stays empty", kind="edge", weight=1.2, required=True),
                ],
                "negative": [
                    _build_case(["xyzuvw"], "xyzuvw"[-suffix_character_count:], "catches off-by-one suffix logic", kind="trap", weight=1.0, required=True),
                ],
            },
            "incorrect_patterns": [
                {
                    "pattern": f"return s[:{suffix_character_count}]",
                    "match_type": "contains",
                    "feedback": f"Returning the first {suffix_character_count} characters does not satisfy the requirement to return the last {suffix_character_count} characters of the string.",
                    "suggestion": f"Return a slice of the last {suffix_character_count} characters, for example with s[-{suffix_character_count}:].",
                    "score_cap": 20,
                },
                {
                    "pattern": f"return s[-1:]",
                    "match_type": "contains",
                    "feedback": f"Returning only the last character does not satisfy the requirement to return the last {suffix_character_count} characters of the string.",
                    "suggestion": f"Return a slice of the last {suffix_character_count} characters, for example with s[-{suffix_character_count}:].",
                    "score_cap": 20,
                },
                {
                    "pattern": f"return s[:-{suffix_character_count}]",
                    "match_type": "contains",
                    "feedback": f"Returning everything except the last {suffix_character_count} characters does not satisfy the requirement to return the suffix itself.",
                    "suggestion": f"Return the last {suffix_character_count} characters with a suffix slice such as s[-{suffix_character_count}:].",
                    "score_cap": 20,
                },
                {
                    "pattern": "return s",
                    "match_type": "contains",
                    "feedback": f"Returning the whole string does not limit the result to the last {suffix_character_count} characters.",
                    "suggestion": f"Slice the input to the last {suffix_character_count} characters before returning it.",
                    "score_cap": 20,
                },
            ],
        }

    contains_value_match = re.search(r"return(-?\d+)inlst", compact)
    if contains_value_match:
        target = int(contains_value_match.group(1))
        return {
            "accepted_solutions": [f"return {target} in lst"],
            "test_sets": {
                "positive": [
                    _build_case([[target, 3, 1]], True, f"list contains {target}", kind="normal", weight=1.0, required=True),
                    _build_case([[1, target, 2]], True, f"{target} appears in the middle of the list", kind="edge", weight=1.1, required=True),
                ],
                "negative": [
                    _build_case([[1, 2, 3]], False, f"list does not contain {target}", kind="normal", weight=1.0, required=True),
                    _build_case([[]], False, "empty list does not contain the value", kind="edge", weight=1.1, required=True),
                ],
            },
            "incorrect_patterns": [
                {
                    "pattern": "return True",
                    "match_type": "contains",
                    "feedback": f"Always returning True does not check whether the list actually contains {target}.",
                    "suggestion": f"Test membership directly, for example with {target} in lst.",
                    "score_cap": 20,
                },
                {
                    "pattern": "return lst",
                    "match_type": "contains",
                    "feedback": "Returning the list itself does not answer the yes-or-no membership question.",
                    "suggestion": f"Return a boolean membership check, for example with {target} in lst.",
                    "score_cap": 20,
                },
                {
                    "pattern": f"return lst[0] == {target}",
                    "match_type": "contains",
                    "feedback": f"Checking only the first element does not determine whether {target} appears anywhere in the list.",
                    "suggestion": f"Check membership across the whole list, for example with {target} in lst.",
                    "score_cap": 20,
                },
            ],
        }

    list_length_comp = _extract_list_length_comparison(question_text)
    if list_length_comp and list_length_comp["value"] is not None:
        op = list_length_comp["operator"]
        val = list_length_comp["value"]
        inverted_op = {"<": ">", ">": "<", "<=": ">=", ">=": "<=", "==": "!=", "!=": "=="}.get(op, op)
        if op == "<":
            passing_list = list(range(val - 1)) if val > 0 else []
            failing_list = list(range(val + 1))
        elif op == ">":
            passing_list = list(range(val + 1))
            failing_list = list(range(max(0, val - 1)))
        elif op == "<=":
            passing_list = list(range(val))
            failing_list = list(range(val + 1))
        elif op == ">=":
            passing_list = list(range(val))
            failing_list = list(range(max(0, val - 1)))
        else:
            passing_list = list(range(val))
            shorter = list(range(max(0, val - 1)))
            failing_list = shorter
        return {
            "accepted_solutions": [f"return len(lst) {op} {val}"],
            "test_sets": {
                "positive": [
                    _build_case([passing_list], True, f"list length satisfies len(lst) {op} {val}", kind="normal", weight=1.0, required=True),
                    _build_case([[]], len([]) < val if op == "<" else len([]) > val if op == ">" else len([]) == val if op == "==" else True, "empty list edge case", kind="edge", weight=1.1, required=False),
                ],
                "negative": [
                    _build_case([failing_list], False, f"list length does not satisfy len(lst) {op} {val}", kind="normal", weight=1.0, required=True),
                ],
            },
            "incorrect_patterns": [
                {
                    "pattern": f"return len(lst) {inverted_op} {val}",
                    "match_type": "contains",
                    "feedback": f"This comparison is inverted. The question asks for len(lst) {op} {val}.",
                    "suggestion": f"Use len(lst) {op} {val} to match the required condition.",
                    "score_cap": 20,
                },
                {
                    "pattern": f"return len(lst) == {val}",
                    "match_type": "contains",
                    "feedback": f"Using equality (==) checks for an exact length, but the question requires a {op} comparison.",
                    "suggestion": f"Compare the length with {op}, for example with len(lst) {op} {val}.",
                    "score_cap": 20,
                },
            ],
        }

    function_match = re.search(r"def\s+[A-Za-z_][A-Za-z0-9_]*\s*\(([^)]*)\)", model_answer or "")
    params = []
    if function_match:
        for bit in function_match.group(1).split(","):
            name = bit.strip().split("=")[0].strip()
            if name:
                params.append(name)
    primary = params[0] if params else "x"

    oracle_baseline = _build_python_oracle_baseline_from_model_answer(model_answer)
    fallback_patterns = oracle_baseline.get("incorrect_patterns") or [
        {
            "pattern": "return True",
            "match_type": "contains",
            "feedback": "Always returning True does not implement the required logic for this question.",
            "suggestion": "Use the input and the model answer pattern to compute the expected result.",
            "score_cap": 20,
        },
        {
            "pattern": f"return {primary}",
            "match_type": "contains",
            "feedback": "Returning the input directly does not implement the required transformation or check for this question.",
            "suggestion": "Compute the result from the input instead of returning it unchanged.",
            "score_cap": 20,
        },
    ]
    return {
        "accepted_solutions": oracle_baseline.get("accepted_solutions") or [],
        "test_sets": oracle_baseline.get("test_sets") or {"positive": [], "negative": []},
        "incorrect_patterns": fallback_patterns,
    }


def _build_deterministic_baseline_package(question, model_answer, language):
    language = (language or "").strip().lower()
    if language in {"python", "java", "javascript"}:
        baseline = _deterministic_code_baselines(question, language)
        if language == "python":
            baseline = _merge_generated_package(baseline, _python_model_answer_baselines(model_answer, question_text=question, language=language))
        return baseline
    return _deterministic_markup_baselines(question, language)


def _is_specific_template_family(template_family):
    family = (template_family or "").strip().lower()
    broad_suffixes = {
        "::generic",
        "::array_ops",
        "::string_ops",
        "::static_template",
    }
    return bool(family) and not any(family.endswith(suffix) for suffix in broad_suffixes)


def _prune_placeholder_tests(test_sets, template_family):
    if not _is_specific_template_family(template_family):
        return test_sets

    normalized_family = (template_family or "").strip().lower()
    cleaned = {"positive": [], "negative": []}
    for bucket in ("positive", "negative"):
        normalized_items = [
            _normalize_test_case(item)
            for item in (test_sets or {}).get(bucket, [])
        ]
        has_exact_expected_output = any(
            item and item.get("expected_output") != "null"
            for item in normalized_items
        )
        for normalized in normalized_items:
            if not normalized:
                continue
            if normalized_family == "python::non_empty_collection_check":
                try:
                    parsed_input = json.loads(normalized.get("input") or "")
                    parsed_expected = json.loads(normalized.get("expected_output") or "")
                except (TypeError, json.JSONDecodeError):
                    continue
                if (
                    not isinstance(parsed_input, list)
                    or not parsed_input
                    or not isinstance(parsed_input[0], list)
                    or not isinstance(parsed_expected, bool)
                ):
                    continue
            if normalized_family == "python::list_length":
                try:
                    parsed_input = json.loads(normalized.get("input") or "")
                    parsed_expected = json.loads(normalized.get("expected_output") or "")
                except (TypeError, json.JSONDecodeError):
                    continue
                if (
                    not isinstance(parsed_input, list)
                    or not parsed_input
                    or not isinstance(parsed_input[0], list)
                    or not isinstance(parsed_expected, int)
                    or isinstance(parsed_expected, bool)
                ):
                    continue
            if normalized_family == "python::first_and_last_character":
                try:
                    parsed_input = json.loads(normalized.get("input") or "")
                except (TypeError, json.JSONDecodeError):
                    continue

                parsed_expected = normalized.get("expected_output")
                if isinstance(parsed_expected, str):
                    # expected_output may be a raw string (e.g. pn) or a JSON-encoded string (e.g. "pn")
                    try:
                        unwrapped = json.loads(parsed_expected)
                        if isinstance(unwrapped, str):
                            parsed_expected = unwrapped
                    except Exception:
                        pass
                if (
                    not isinstance(parsed_input, list)
                    or len(parsed_input) != 1
                    or not isinstance(parsed_input[0], str)
                    or not isinstance(parsed_expected, str)
                    or len(parsed_input[0]) < 1
                    or parsed_expected != (parsed_input[0][:1] + parsed_input[0][-1:])
                ):
                    continue
            if normalized_family == "python::list_length_equals_constant":
                try:
                    parsed_input = json.loads(normalized.get("input") or "")
                    parsed_expected = json.loads(normalized.get("expected_output") or "")
                except (TypeError, json.JSONDecodeError):
                    continue
                if (
                    not isinstance(parsed_input, list)
                    or not parsed_input
                    or not isinstance(parsed_input[0], list)
                    or not isinstance(parsed_expected, bool)
                ):
                    continue
            if normalized_family == "python::prefix_characters_constant":
                try:
                    parsed_input = json.loads(normalized.get("input") or "")
                except (TypeError, json.JSONDecodeError):
                    continue
                parsed_expected = normalized.get("expected_output")
                if (
                    not isinstance(parsed_input, list)
                    or not parsed_input
                    or not isinstance(parsed_input[0], str)
                    or not isinstance(parsed_expected, str)
                ):
                    continue
            if normalized_family == "python::middle_character":
                try:
                    parsed_input = json.loads(normalized.get("input") or "")
                except (TypeError, json.JSONDecodeError):
                    continue
                parsed_expected = normalized.get("expected_output")
                if isinstance(parsed_expected, str):
                    try:
                        unwrapped = json.loads(parsed_expected)
                        if isinstance(unwrapped, str):
                            parsed_expected = unwrapped
                    except Exception:
                        pass
                if (
                    not isinstance(parsed_input, list)
                    or len(parsed_input) != 1
                    or not isinstance(parsed_input[0], str)
                    or len(parsed_input[0]) % 2 == 0
                    or not isinstance(parsed_expected, str)
                    or len(parsed_expected) != 1
                ):
                    continue
            if normalized_family == "python::list_contains_constant":
                try:
                    parsed_input = json.loads(normalized.get("input") or "")
                    parsed_expected = json.loads(normalized.get("expected_output") or "")
                except (TypeError, json.JSONDecodeError):
                    continue
                if (
                    not isinstance(parsed_input, list)
                    or len(parsed_input) != 1
                    or not isinstance(parsed_input[0], list)
                    or not isinstance(parsed_expected, bool)
                ):
                    continue
            if normalized_family == "python::element_at_index_constant":
                try:
                    parsed_input = json.loads(normalized.get("input") or "")
                except (TypeError, json.JSONDecodeError):
                    continue
                if (
                    not isinstance(parsed_input, list)
                    or not parsed_input
                    or not isinstance(parsed_input[0], list)
                ):
                    continue
            expected_output = normalized.get("expected_output")
            description = (normalized.get("description") or "").strip().lower()
            if expected_output == "null" and (
                has_exact_expected_output
                or "baseline" in description
                or "representative" in description
                or "edge-case" in description
                or "edge case" in description
                or "single-character" in description
                or "single element" in description
                or "mixed-sign" in description
                or "string containing space" in description
            ):
                continue
            cleaned[bucket].append(normalized)
    return cleaned


def _canonicalize_family_test_descriptions(test_sets, template_family, question_text):
    normalized_family = (template_family or "").strip().lower()
    normalized_question = (question_text or "").strip().lower()
    canonicalized = {"positive": [], "negative": []}

    if normalized_family == "python::first_and_last_character":
        for bucket in ("positive", "negative"):
            for item in (test_sets or {}).get(bucket, []):
                normalized = _normalize_test_case(item)
                if not normalized:
                    continue
                try:
                    parsed_input = json.loads(normalized.get("input") or "")
                    parsed_expected = json.loads(normalized.get("expected_output") or "")
                except (TypeError, json.JSONDecodeError):
                    parsed_input = None
                    parsed_expected = None

                if (
                    isinstance(parsed_input, list)
                    and len(parsed_input) == 1
                    and isinstance(parsed_input[0], str)
                    and isinstance(parsed_expected, str)
                ):
                    source = parsed_input[0]
                    if bucket == "positive":
                        if len(source) == 1:
                            normalized["description"] = "single character is both first and last"
                        elif len(source) == 2:
                            normalized["description"] = "two-character string returns both characters"
                        else:
                            normalized["description"] = "basic first and last character extraction"
                    else:
                        if len(source) >= 2:
                            normalized["description"] = "catches first-character-only or last-character-only logic"
                canonicalized[bucket].append(normalized)
        return canonicalized

    if normalized_family == "python::list_length_equals_constant":
        target_length = None
        match = re.search(r"(?:exactly|equal to|equals|is)\s+([a-z0-9-]+)", normalized_question)
        if match:
            target_length = _parse_small_int_token(match.group(1))
        for bucket in ("positive", "negative"):
            for item in (test_sets or {}).get(bucket, []):
                normalized = _normalize_test_case(item)
                if not normalized:
                    continue
                try:
                    parsed_input = json.loads(normalized.get("input") or "")
                    parsed_expected = json.loads(normalized.get("expected_output") or "")
                except (TypeError, json.JSONDecodeError):
                    parsed_input = None
                    parsed_expected = None

                if (
                    isinstance(parsed_input, list)
                    and len(parsed_input) == 1
                    and isinstance(parsed_input[0], list)
                    and isinstance(parsed_expected, bool)
                ):
                    source = parsed_input[0]
                    if bucket == "positive":
                        if target_length is not None:
                            normalized["description"] = f"list length equals {target_length}"
                    else:
                        if target_length is not None:
                            if len(source) < target_length:
                                normalized["description"] = f"list length below {target_length}"
                            elif len(source) > target_length:
                                normalized["description"] = f"list length above {target_length}"
                canonicalized[bucket].append(normalized)
        return canonicalized

    if normalized_family == "python::suffix_characters_constant":
        suffix_count = _extract_last_n_characters_count(normalized_question)
        for bucket in ("positive", "negative"):
            for item in (test_sets or {}).get(bucket, []):
                normalized = _normalize_test_case(item)
                if not normalized:
                    continue
                try:
                    parsed_input = json.loads(normalized.get("input") or "")
                except (TypeError, json.JSONDecodeError):
                    parsed_input = None

                if (
                    suffix_count
                    and isinstance(parsed_input, list)
                    and len(parsed_input) == 1
                    and isinstance(parsed_input[0], str)
                    and bucket == "positive"
                ):
                    source = parsed_input[0]
                    if source == "":
                        normalized["description"] = "empty string stays empty"
                    elif len(source) == 1:
                        normalized["description"] = "single character input stays safe"
                    elif len(source) == suffix_count:
                        normalized["description"] = "exact-length string input"
                canonicalized[bucket].append(normalized)
        return canonicalized

    if normalized_family == "python::middle_character":
        for bucket in ("positive", "negative"):
            for item in (test_sets or {}).get(bucket, []):
                normalized = _normalize_test_case(item)
                if not normalized:
                    continue
                try:
                    parsed_input = json.loads(normalized.get("input") or "")
                except (TypeError, json.JSONDecodeError):
                    parsed_input = None

                if (
                    isinstance(parsed_input, list)
                    and len(parsed_input) == 1
                    and isinstance(parsed_input[0], str)
                ):
                    source = parsed_input[0]
                    if bucket == "positive":
                        if len(source) == 1:
                            normalized["description"] = "single-character string"
                        elif len(source) == 3:
                            normalized["description"] = "basic odd-length string middle character"
                        else:
                            normalized["description"] = "longer odd-length string"
                    elif bucket == "negative":
                        normalized["description"] = "catches first/last-character confusion"
                canonicalized[bucket].append(normalized)
        return canonicalized

    if normalized_family == "python::list_contains_constant":
        target = _extract_list_contains_constant(normalized_question)
        for bucket in ("positive", "negative"):
            for item in (test_sets or {}).get(bucket, []):
                normalized = _normalize_test_case(item)
                if not normalized:
                    continue
                try:
                    parsed_input = json.loads(normalized.get("input") or "")
                except (TypeError, json.JSONDecodeError):
                    parsed_input = None

                if (
                    target is not None
                    and isinstance(parsed_input, list)
                    and len(parsed_input) == 1
                    and isinstance(parsed_input[0], list)
                ):
                    source = parsed_input[0]
                    if bucket == "positive":
                        if source and target in source and source[0] == target:
                            normalized["description"] = f"list contains {target}"
                        else:
                            normalized["description"] = f"{target} appears in the middle of the list"
                    else:
                        normalized["description"] = (
                            "empty list does not contain the value"
                            if source == []
                            else f"list does not contain {target}"
                        )
                canonicalized[bucket].append(normalized)
        return canonicalized

    return test_sets


def _merge_generated_package(base_payload, generated_payload):
    merged = dict(base_payload or {})
    merged.setdefault("accepted_solutions", [])
    merged.setdefault("incorrect_patterns", [])
    merged.setdefault("test_sets", {"positive": [], "negative": []})

    merged["accepted_solutions"] = _dedupe_strings(
        [*merged.get("accepted_solutions", []), *(generated_payload.get("accepted_solutions", []) or [])],
        limit=AUTO_GENERATE_MAX_ALTERNATIVES,
    )

    existing_patterns = list(merged.get("incorrect_patterns", []) or [])
    for item in generated_payload.get("incorrect_patterns", []) or []:
        normalized = _normalize_incorrect_pattern(item)
        if normalized and normalized not in existing_patterns:
            existing_patterns.append(normalized)
    merged["incorrect_patterns"] = existing_patterns

    existing_tests = merged.get("test_sets") or {"positive": [], "negative": []}
    combined_tests = {"positive": [], "negative": []}
    for bucket in ("positive", "negative"):
        combined = (existing_tests.get(bucket) or []) + (generated_payload.get("test_sets", {}).get(bucket) or [])
        combined_tests[bucket] = _dedupe_tests_by_io(combined)[:AUTO_GENERATE_MAX_HIDDEN_TESTS]
    merged["test_sets"] = _prune_placeholder_tests(
        combined_tests,
        merged.get("template_family") or generated_payload.get("template_family"),
    )
    return merged


def _is_internal_reuse_question(question_text):
    lowered = (question_text or "").strip().lower()
    internal_markers = (
        "guardrail probe",
        "scoring fallback probe",
        "llm repair package",
        "fenced llm json",
        "fallback not package",
    )
    return any(marker in lowered for marker in internal_markers)


def _extract_family_variant(template_family, question_text, model_answer):
    normalized_family = (template_family or "").strip().lower()
    normalized_question = (question_text or "").strip().lower()
    compact_answer = re.sub(r"\s+", "", (model_answer or "").lower())

    if normalized_family == "python::greater_than_threshold":
        question_match = re.search(r"greater than\s+(-?\d+)", normalized_question)
        answer_match = re.search(r"return[a-z_][a-z0-9_]*>(-?\d+)|returnn>(-?\d+)", compact_answer)
        threshold = (
            (question_match.group(1) if question_match else None)
            or (answer_match.group(1) if answer_match else None)
            or (answer_match.group(2) if answer_match else None)
        )
        return threshold

    if normalized_family == "python::divisible_by_constant":
        question_match = re.search(r"divisible by\s+(-?\d+)", normalized_question)
        answer_match = re.search(r"return[a-z_][a-z0-9_]*%(-?\d+)==0|returnn%(-?\d+)==0", compact_answer)
        divisor = (
            (question_match.group(1) if question_match else None)
            or (answer_match.group(1) if answer_match else None)
            or (answer_match.group(2) if answer_match else None)
        )
        return divisor

    if normalized_family == "python::list_length_equals_constant":
        question_match = re.search(r"length\s+(?:equals|equal to|is)\s+(-?\d+)", normalized_question)
        answer_match = re.search(r"len\(lst\)==(-?\d+)", compact_answer)
        target_length = (
            (question_match.group(1) if question_match else None)
            or (answer_match.group(1) if answer_match else None)
        )
        return target_length

    if normalized_family == "python::prefix_characters_constant":
        question_count = _extract_character_prefix_count(normalized_question)
        answer_match = re.search(r"return[a-z_][a-z0-9_]*\[:(-?\d+)\]|return[a-z_][a-z0-9_]*\[0:(-?\d+)\]", compact_answer)
        return (
            str(question_count) if question_count is not None else None
        ) or (answer_match.group(1) if answer_match else None) or (answer_match.group(2) if answer_match else None)

    if normalized_family == "python::list_contains_constant":
        question_value = _extract_list_contains_constant(normalized_question)
        answer_match = re.search(r"return(-?\d+)inlst", compact_answer)
        return (
            str(question_value) if question_value is not None else None
        ) or (answer_match.group(1) if answer_match else None)

    if normalized_family == "python::element_at_index_constant":
        question_position = _extract_element_position(normalized_question)
        answer_match = re.search(r"returnlst\[(-?\d+)\]", compact_answer)
        answer_position = str(int(answer_match.group(1)) + 1) if answer_match else None
        return (str(question_position) if question_position is not None else None) or answer_position

    return None


def _is_profile_reuse_compatible(profile_family, template_family):
    normalized_profile_family = (profile_family or "").strip().lower()
    normalized_template_family = (template_family or "").strip().lower()
    if not normalized_template_family:
        return True
    if not _is_specific_template_family(normalized_template_family):
        return True
    if not normalized_profile_family:
        return False
    if not _is_specific_template_family(normalized_profile_family):
        return False
    return normalized_profile_family == normalized_template_family


def merge_with_existing_profiles(payload, existing_profiles):
    merged = dict(payload or {})
    signature = _normalize_question_signature(merged.get("question"), merged.get("language"))
    model_answer = merged.get("model_answer") or ""
    template_family = merged.get("template_family") or _infer_best_template_family(merged.get("question"), model_answer, merged.get("language"))
    merged["question_signature"] = signature
    merged["template_family"] = template_family

    accepted = []
    incorrect_patterns = []
    test_sets = {"positive": [], "negative": []}
    reused_from_questions = []

    for profile in existing_profiles or []:
        profile_signature = _normalize_question_signature(profile.get("question"), profile.get("language"))
        profile_family = profile.get("template_family") or _infer_best_template_family(profile.get("question"), profile.get("model_answer"), profile.get("language"))
        profile_status = (profile.get("package_status") or "").strip().lower()
        if profile_status not in {"validated", "live"}:
            continue
        if bool(profile.get("review_required", False)):
            continue
        if float(profile.get("package_confidence", 0.0) or 0.0) < 0.9:
            continue
        signature_match = profile_signature == signature
        signature_compatible = _is_profile_reuse_compatible(profile_family, template_family)
        profile_variant = _extract_family_variant(profile_family, profile.get("question"), profile.get("model_answer"))
        target_variant = _extract_family_variant(template_family, merged.get("question"), model_answer)
        family_match = (
            profile_family == template_family
            and _is_specific_template_family(template_family)
            and template_family != "python::model_answer_derived"
            and profile_variant == target_variant
        )
        if not ((signature_match and signature_compatible) or family_match):
            continue
        profile_question = (profile.get("question") or "").strip()
        if (
            profile_question
            and not _is_internal_reuse_question(profile_question)
            and profile_question not in reused_from_questions
        ):
            reused_from_questions.append(profile_question)
        for answer in profile.get("accepted_solutions", []) or profile.get("alternative_answers", []) or []:
            cleaned = answer.strip() if isinstance(answer, str) else ""
            if cleaned and _is_answer_aligned_with_model(cleaned, model_answer) and cleaned not in accepted:
                accepted.append(answer.strip())
        if signature_match:
            for item in (profile.get("incorrect_patterns") or []):
                normalized = _normalize_incorrect_pattern(item)
                if (
                    normalized
                    and _is_pattern_aligned_with_model(normalized.get("pattern"), model_answer)
                    and normalized not in incorrect_patterns
                ):
                    incorrect_patterns.append(normalized)
        profile_test_sets = profile.get("test_sets") or {}
        legacy_hidden = profile.get("hidden_tests") or []
        if signature_match or family_match:
            for item in profile_test_sets.get("positive", []) + legacy_hidden:
                normalized = _normalize_test_case(item)
                if normalized and normalized not in test_sets["positive"]:
                    test_sets["positive"].append(normalized)
            for item in profile_test_sets.get("negative", []):
                normalized = _normalize_test_case(item)
                if normalized and normalized not in test_sets["negative"]:
                    test_sets["negative"].append(normalized)

    merged.setdefault("accepted_solutions", [])
    merged.setdefault("incorrect_patterns", [])
    merged.setdefault("test_sets", {"positive": [], "negative": []})

    for item in merged["accepted_solutions"]:
        cleaned = item.strip() if isinstance(item, str) else ""
        if cleaned and _is_answer_aligned_with_model(cleaned, model_answer) and cleaned not in accepted:
            accepted.append(cleaned)
    for item in merged["incorrect_patterns"]:
        normalized = _normalize_incorrect_pattern(item)
        if normalized and normalized not in incorrect_patterns:
            incorrect_patterns.append(normalized)
    for bucket in ("positive", "negative"):
        for item in merged["test_sets"].get(bucket, []):
            normalized = _normalize_test_case(item)
            if normalized and normalized not in test_sets[bucket]:
                test_sets[bucket].append(normalized)

    merged["accepted_solutions"] = accepted[:AUTO_GENERATE_MAX_ALTERNATIVES]
    if (template_family or "").strip().lower().endswith("::double_number"):
        pruned = []
        for item in incorrect_patterns:
            pattern = (item or {}).get("pattern") or ""
            match_type = ((item or {}).get("match_type") or "").strip().lower()
            normalized = pattern.strip().rstrip(";")

            if match_type in {"contains", "normalized_contains"} and normalized in {
                "return n",
                "return n + n",
                "def double(n): return n + n",
            }:
                continue

            if "return n * 3" in normalized or "return n*3" in normalized:
                item = dict(item)
                item["feedback"] = "This triples the input instead of doubling it."
                item["suggestion"] = "Use n * 2 or n + n to double the value."
                item["score_cap"] = int(item.get("score_cap", 20) or 20)

            pruned.append(item)
        incorrect_patterns = pruned
    merged["incorrect_patterns"] = _sanitize_incorrect_patterns_for_family(
        incorrect_patterns,
        template_family,
        merged.get("question"),
    )
    merged["test_sets"] = _prune_placeholder_tests(
        {
            "positive": _dedupe_tests_by_io(test_sets["positive"])[:AUTO_GENERATE_MAX_HIDDEN_TESTS],
            "negative": _dedupe_tests_by_io(test_sets["negative"])[:AUTO_GENERATE_MAX_HIDDEN_TESTS],
        },
        template_family,
    )
    merged["reused_from_questions"] = reused_from_questions
    return merged


def _promote_learning_patterns(payload):
    promoted = []
    promoted_answers = []
    promoted_tests = {"positive": [], "negative": []}
    signature = _normalize_question_signature(payload.get("question"), payload.get("language"))
    template_family = payload.get("template_family") or _infer_template_family(payload.get("question"), payload.get("language"))
    repeated_bad = {}
    repeated_good = {}
    low_score_hits = 0
    model_answer = payload.get("model_answer") or ""

    for item in list_recent_learning_signals(limit=500):
        if (item.get("language") or "").strip().lower() != (payload.get("language") or "").strip().lower():
            continue
        metadata = item.get("metadata") or {}
        if metadata.get("question_signature") != signature:
            continue
        raw_answer = (item.get("student_answer_text") or "").strip()
        if raw_answer and not _is_answer_aligned_with_model(raw_answer, model_answer):
            continue
        if item.get("status") != "error" and item.get("score", 0) >= 90 and raw_answer:
            entry = repeated_good.setdefault(raw_answer, {"count": 0})
            entry["count"] += 1
            continue
        if item.get("score", 0) > 20 and item.get("status") != "error":
            continue
        answer = (item.get("normalized_student_answer") or "").strip()
        if not answer:
            continue
        low_score_hits += 1
        entry = repeated_bad.setdefault(answer, {"count": 0, "feedback": item.get("feedback", "")})
        entry["count"] += 1

    for answer, data in repeated_good.items():
        if data["count"] < 2:
            continue
        promoted_answers.append(answer)

    for answer, data in repeated_bad.items():
        if data["count"] < 2:
            continue
        promoted.append({
            "pattern": answer,
            "match_type": "normalized_contains",
            "feedback": data["feedback"] or "A repeated incorrect answer pattern was detected from earlier evaluations.",
            "suggestion": "Use the registered hidden tests and accepted solutions to replace this repeated low-scoring pattern.",
            "score_cap": 20,
        })

    if low_score_hits >= 2:
        promoted_test_map = {
            "python::maximum_array": {"positive": [], "negative": [_build_case([[-4, -2, -9]], -2, "learning-added all-negative max trap", kind="trap", weight=1.4, required=True)]},
            "javascript::maximum_array": {"positive": [], "negative": [_build_case([[-4, -2, -9]], -2, "learning-added all-negative max trap", kind="trap", weight=1.4, required=True)]},
            "python::minimum_array": {"positive": [], "negative": [_build_case([[4, 2, 9]], 2, "learning-added positive-only min trap", kind="trap", weight=1.3, required=True)]},
            "javascript::minimum_array": {"positive": [], "negative": [_build_case([[4, 2, 9]], 2, "learning-added positive-only min trap", kind="trap", weight=1.3, required=True)]},
            "python::reverse_string": {"positive": [], "negative": [_build_case([""], "", "learning-added empty-string reverse trap", kind="edge", weight=1.2, required=True)]},
            "javascript::reverse_string": {"positive": [], "negative": [_build_case([""], "", "learning-added empty-string reverse trap", kind="edge", weight=1.2, required=True)]},
            "python::sum_collection": {"positive": [], "negative": [_build_case([[]], 0, "learning-added empty-collection sum trap", kind="edge", weight=1.3, required=True)]},
            "javascript::sum_collection": {"positive": [], "negative": [_build_case([[]], 0, "learning-added empty-collection sum trap", kind="edge", weight=1.3, required=True)]},
            "mysql::sql_join": {"positive": [{"input": "seeded", "expected_output": "joined_rows_required", "description": "learning-added required join case", "kind": "trap", "weight": 1.3, "required": True}], "negative": []},
            "mongodb::aggregation": {"positive": [{"input": "seeded", "expected_output": "aggregation_required", "description": "learning-added required aggregation case", "kind": "trap", "weight": 1.3, "required": True}], "negative": []},
        }
        promoted_tests = promoted_test_map.get(template_family, {"positive": [], "negative": []})

    if promoted or promoted_answers or promoted_tests["positive"] or promoted_tests["negative"]:
        payload = _merge_generated_package(
            payload,
            {
                "accepted_solutions": promoted_answers,
                "test_sets": promoted_tests,
                "incorrect_patterns": promoted,
            },
        )
    return payload


def enrich_question_profile(payload, force_llm=False, repair_context=None):
    enriched = dict(payload or {})
    generation_sources = [
        item for item in (enriched.get("generation_sources") or [])
        if isinstance(item, str) and item.strip()
    ]
    enriched["generation_sources"] = generation_sources
    enriched["llm_assisted"] = bool(enriched.get("llm_assisted", False))
    initial_model_answer = enriched.get("model_answer")
    enriched["question_signature"] = enriched.get("question_signature") or _normalize_question_signature(
        enriched.get("question"),
        enriched.get("language"),
    )
    enriched["template_family"] = enriched.get("template_family") or _infer_best_template_family(
        enriched.get("question"),
        initial_model_answer,
        enriched.get("language"),
    )
    enriched.setdefault("accepted_solutions", [])
    enriched.setdefault("incorrect_patterns", [])
    enriched.setdefault("test_sets", {"positive": [], "negative": []})

    question = (enriched.get("question") or "").strip()
    model_answer = (enriched.get("model_answer") or "").strip()
    language = (enriched.get("language") or "").strip().lower()

    if not question or not model_answer or not language:
        return enriched

    template_family = (enriched.get("template_family") or "").strip().lower()
    if force_llm and (template_family.endswith("::generic") or template_family.endswith("::array_ops") or template_family.endswith("::string_ops")):
        inferred = _infer_template_family_with_llm(question, language)
        if inferred:
            enriched["template_family"] = inferred
            if "llm_template_inference" not in generation_sources:
                generation_sources.append("llm_template_inference")
            enriched["llm_assisted"] = True

    baseline_package = _build_deterministic_baseline_package(question, model_answer, language)
    enriched = _merge_generated_package(enriched, baseline_package)
    if "deterministic_baseline" not in generation_sources:
        generation_sources.append("deterministic_baseline")
    enriched = _promote_learning_patterns(enriched)

    if not AUTO_GENERATE_QUESTION_RULES and not force_llm:
        return enriched

    oracle_package = None
    if language == "python":
        from evaluator.execution.shared import generate_universal_oracle_test_package_for_registration
        oracle_cases = int(ORACLE_TEST_CASES_BASE or 15)
        if force_llm and repair_context:
            oracle_cases = int(ORACLE_TEST_CASES_EXPANDED or oracle_cases)
        oracle_package = generate_universal_oracle_test_package_for_registration(
            question,
            model_answer,
            n_cases=oracle_cases,
        )
        if oracle_package:
            enriched = _merge_generated_package(enriched, oracle_package)

    parsed, llm_source = _call_llm_for_registration_package(
        _build_generation_prompt(question, model_answer, language, repair_context=repair_context)
    )
    if not parsed:
        return enriched
    if llm_source and llm_source not in generation_sources:
        generation_sources.append(llm_source)
    enriched["llm_assisted"] = True

    accepted = []
    for item in parsed.get("accepted_solutions", []):
        if isinstance(item, str):
            cleaned = item.strip()
            if cleaned and cleaned != model_answer and cleaned not in accepted:
                accepted.append(cleaned)

    test_sets = {"positive": [], "negative": []}
    if not oracle_package:
        for bucket in ("positive", "negative"):
            for item in (parsed.get("test_sets") or {}).get(bucket, []):
                normalized = _normalize_test_case(item)
                if normalized:
                    test_sets[bucket].append(normalized)

    incorrect_patterns = []
    for item in parsed.get("incorrect_patterns", []):
        normalized = _normalize_incorrect_pattern(item)
        if normalized:
            incorrect_patterns.append(normalized)

    merged = _merge_generated_package(
        enriched,
        {
            "accepted_solutions": accepted[:AUTO_GENERATE_MAX_ALTERNATIVES],
            "test_sets": {
                "positive": test_sets["positive"][:AUTO_GENERATE_MAX_HIDDEN_TESTS],
                "negative": test_sets["negative"][:AUTO_GENERATE_MAX_HIDDEN_TESTS],
            },
            "incorrect_patterns": incorrect_patterns,
        },
    )
    merged["generation_sources"] = generation_sources
    merged["llm_assisted"] = bool(merged.get("llm_assisted", False) or enriched.get("llm_assisted", False))
    return merged


def _parse_hidden_test_input(raw_value):
    if raw_value is None:
        return tuple()
    if isinstance(raw_value, (list, tuple)):
        return tuple(raw_value)
    if isinstance(raw_value, (int, float, bool)):
        return (raw_value,)
    if not isinstance(raw_value, str):
        return (raw_value,)
    text = raw_value.strip()
    if not text:
        return tuple()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return (text,)
    if isinstance(parsed, list):
        return tuple(parsed)
    return (parsed,)


def _parse_expected_output(raw_value):
    if isinstance(raw_value, (list, dict, int, float, bool)) or raw_value is None:
        return raw_value
    if not isinstance(raw_value, str):
        return raw_value
    text = raw_value.strip()
    if not text:
        return ""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


def _finalize_from_validation_result(finalized, total, passed, summary_prefix):
    if total == 0:
        finalized["package_status"] = "draft"
        finalized["package_summary"] = "No generated tests available for validation."
        finalized["package_confidence"] = 0.2
        finalized["review_required"] = True
        finalized["exam_ready"] = False
        return finalized

    confidence = passed / total
    finalized["package_confidence"] = round(confidence, 3)
    if passed == total:
        finalized["package_status"] = "validated"
        finalized["package_summary"] = f"{summary_prefix} Validated {passed}/{total} generated tests."
        finalized["review_required"] = False
        finalized["exam_ready"] = (
            finalized.get("approval_status") == "approved"
            and confidence >= MIN_PACKAGE_CONFIDENCE_FOR_EXAM
            and not finalized["review_required"]
        )
        if (
            AUTO_ACTIVATE_VALIDATED_QUESTIONS
            and finalized["exam_ready"]
            and (not REQUIRE_FACULTY_APPROVAL_FOR_LIVE or finalized.get("approval_status") == "approved")
        ):
            finalized["package_status"] = "live"
        return finalized

    if passed >= max(1, total - 1):
        finalized["package_status"] = "validated"
        finalized["package_summary"] = f"{summary_prefix} Validated {passed}/{total} generated tests, but review is recommended."
        finalized["review_required"] = True
        finalized["exam_ready"] = False
        return finalized

    finalized["package_status"] = "generated"
    finalized["package_summary"] = f"{summary_prefix} Only {passed}/{total} generated tests validated against the model answer."
    finalized["review_required"] = True
    finalized["exam_ready"] = False
    return finalized


def _finalize_from_syntax_result(finalized, syntax_result, summary_prefix, confidence=0.7):
    if not syntax_result.get("valid"):
        finalized["package_status"] = "draft"
        finalized["package_summary"] = f"{summary_prefix} Syntax validation failed: {syntax_result.get('error', 'unknown error')}."
        finalized["package_confidence"] = 0.15
        finalized["review_required"] = True
        finalized["exam_ready"] = False
        return finalized

    finalized["package_status"] = "validated"
    finalized["package_summary"] = f"{summary_prefix} Static validation passed for the faculty model answer."
    finalized["package_confidence"] = confidence
    finalized["review_required"] = False if confidence >= 0.75 else True
    finalized["exam_ready"] = (
        finalized.get("approval_status") == "approved"
        and confidence >= MIN_PACKAGE_CONFIDENCE_FOR_EXAM
        and not finalized["review_required"]
    )
    if (
        AUTO_ACTIVATE_VALIDATED_QUESTIONS
        and finalized["exam_ready"]
        and (not REQUIRE_FACULTY_APPROVAL_FOR_LIVE or finalized.get("approval_status") == "approved")
    ):
        finalized["package_status"] = "live"
    return finalized


def finalize_question_profile(payload):
    finalized = dict(payload or {})
    finalized["template_family"] = finalized.get("template_family") or _infer_best_template_family(
        finalized.get("question"),
        finalized.get("model_answer"),
        finalized.get("language"),
    )
    finalized["approval_status"] = (finalized.get("approval_status") or "pending").strip().lower()
    finalized["approved_by"] = (finalized.get("approved_by") or "").strip() or None
    finalized["exam_ready"] = False
    accepted = [item for item in finalized.get("accepted_solutions", []) if isinstance(item, str) and item.strip()]
    if finalized.get("model_answer"):
        accepted = [finalized["model_answer"].strip(), *accepted]
    dedup_accepted = []
    for item in accepted:
        cleaned = item.strip()
        if cleaned and cleaned not in dedup_accepted:
            dedup_accepted.append(cleaned)
    template_family = (finalized.get("template_family") or "").strip().lower()
    question_text = (finalized.get("question") or "").strip().lower()
    model_answer = (finalized.get("model_answer") or "").strip()
    language = (finalized.get("language") or "").strip().lower()
    if template_family == "python::string_length" or "length of string" in question_text:
        dedup_accepted = [
            item
            for item in dedup_accepted
            if item == model_answer or "len(str(" not in item.replace(" ", "")
        ]
    if language == "python" and (template_family == "python::minimum_array" or ("minimum" in question_text and "list" in question_text)):
        dedup_accepted = [
            item
            for item in dedup_accepted
            if item == model_answer or "min(arr)" not in item.replace(" ", "")
        ]
    if language == "python" and (template_family == "python::odd_check" or ("odd" in question_text and "number" in question_text)):
        dedup_accepted = [
            item
            for item in dedup_accepted
            if item == model_answer or "%2==1" not in item.replace(" ", "")
        ]
    finalized["accepted_solutions"] = dedup_accepted[: AUTO_GENERATE_MAX_ALTERNATIVES + 1]

    test_sets = finalized.get("test_sets") or {"positive": [], "negative": []}
    raw_positive_tests = [_normalize_test_case(item) for item in test_sets.get("positive", []) if _normalize_test_case(item)]
    raw_negative_tests = [_normalize_test_case(item) for item in test_sets.get("negative", []) if _normalize_test_case(item)]

    rebucketed_positive_tests = []
    rebucketed_negative_tests = list(raw_negative_tests)
    for item in raw_positive_tests:
        try:
            parsed_expected = json.loads(item.get("expected_output") or "")
        except (TypeError, json.JSONDecodeError):
            parsed_expected = None
        if isinstance(parsed_expected, bool) and parsed_expected is False:
            if item not in rebucketed_negative_tests:
                rebucketed_negative_tests.append(item)
            continue
        rebucketed_positive_tests.append(item)

    positive_tests = _trim_oracle_positive_tests(rebucketed_positive_tests)
    negative_tests = rebucketed_negative_tests
    positive_keys = {
        (str(item.get("input")), str(item.get("expected_output"))) for item in positive_tests if item
    }
    required_negative_keys = {
        (str(item.get("input")), str(item.get("expected_output")))
        for item in negative_tests
        if item and item.get("required")
    }
    if required_negative_keys:
        positive_tests = [
            item
            for item in positive_tests
            if (str(item.get("input")), str(item.get("expected_output"))) not in required_negative_keys
        ]
    negative_tests = [
        item
        for item in negative_tests
        if (str(item.get("input")), str(item.get("expected_output"))) not in positive_keys
        or (str(item.get("input")), str(item.get("expected_output"))) in required_negative_keys
    ]
    positive_tests = _dedupe_tests_by_io(positive_tests)
    negative_tests = _dedupe_tests_by_io(negative_tests)
    finalized["test_sets"] = _canonicalize_family_test_descriptions(
        {"positive": positive_tests, "negative": negative_tests},
        template_family,
        finalized.get("question"),
    )
    finalized["positive_test_count"] = len(positive_tests)
    finalized["negative_test_count"] = len(negative_tests)

    if language == "python":
        def _parse_json_value(value):
            if value is None:
                return None
            if isinstance(value, str):
                try:
                    return json.loads(value)
                except Exception:
                    return value
            return value

        def _build_test_cases(test_cases):
            cases = []
            for item in test_cases:
                parsed_input = _parse_json_value(item.get("input"))
                parsed_expected = _parse_json_value(item.get("expected_output"))
                if parsed_expected is None:
                    continue
                if isinstance(parsed_input, list):
                    args = tuple(parsed_input)
                elif parsed_input is None:
                    continue
                else:
                    args = (parsed_input,)
                cases.append((args, parsed_expected))
            return cases

        def _filter_accepted_solutions(candidates, cases):
            if not cases:
                return candidates
            filtered = []
            inputs = [case[0] for case in cases]
            expected = [case[1] for case in cases]
            for item in candidates:
                if not isinstance(item, str) or not item.strip():
                    continue
                code, fn_name = _wrap_python_snippet(item, question_text)
                if not code or not fn_name:
                    continue
                result = _run_code_with_timeout(code, fn_name, inputs)
                if not result or not result.get("ok"):
                    continue
                outputs = result.get("outputs") or []
                if len(outputs) != len(inputs):
                    continue
                ok = True
                for output, exp in zip(outputs, expected):
                    if not output.get("ok"):
                        ok = False
                        break
                    value = output.get("result")
                    if isinstance(exp, bool) and not isinstance(value, bool):
                        ok = False
                        break
                    if not _smart_outputs_equal(exp, value, question_text):
                        ok = False
                        break
                if ok:
                    filtered.append(item)
            return filtered

        execution_cases = _build_test_cases(positive_tests + negative_tests)
        if execution_cases:
            filtered = _filter_accepted_solutions(finalized.get("accepted_solutions", []), execution_cases)
            if not filtered and model_answer:
                filtered = [model_answer]
            finalized["accepted_solutions"] = filtered[: AUTO_GENERATE_MAX_ALTERNATIVES + 1]

    incorrect_patterns = []
    pattern_map = {}
    pattern_order = []
    for item in finalized.get("incorrect_patterns", []) or []:
        normalized = _normalize_incorrect_pattern(item)
        if not normalized:
            continue
        key = (normalized.get("pattern"), normalized.get("match_type"))
        if key not in pattern_map:
            pattern_order.append(key)
        pattern_map[key] = normalized
    for key in pattern_order:
        incorrect_patterns.append(pattern_map[key])

    # Guardrails:
    # 1) Never store a correct/accepted solution as an "incorrect pattern".
    # 2) Never store f-string-related feedback unless the question actually asks for f-strings.
    accepted_compact = set()
    if language == "python":
        for ans in finalized.get("accepted_solutions", []) or []:
            if not isinstance(ans, str) or not ans.strip():
                continue
            try:
                accepted_compact.add(normalize_python_structure(ans).replace(" ", "").replace("\t", "").lower())
            except Exception:
                accepted_compact.add(re.sub(r"\s+", "", ans).lower())
    asks_fstring = bool(re.search(r"(?i)(?<![a-z0-9])f[- ]string(?![a-z0-9])|formatted string literal", question_text))
    filtered_patterns = []
    for item in incorrect_patterns:
        pattern_text = (item.get("pattern") or "").strip()
        compact_pattern = re.sub(r"\s+", "", pattern_text).lower()
        if compact_pattern and compact_pattern in accepted_compact:
            continue
        feedback_text = (item.get("feedback") or "")
        if not asks_fstring and re.search(r"(?i)f-?strings?", feedback_text):
            continue
        filtered_patterns.append(item)
    incorrect_patterns = filtered_patterns
    if template_family == "python::positive_number" or "positive number" in question_text or "is positive" in question_text:
        for item in incorrect_patterns:
            pattern_text = (item.get("pattern") or "")
            if (">= 0" in pattern_text or ">=0" in pattern_text) and "positive" in (item.get("feedback") or ""):
                item["feedback"] = (
                    "Treating zero as positive does not satisfy the strict positive-number requirement, since zero is neither positive nor negative."
                )
    if template_family == "python::double_number" or "double a number" in question_text:
        pruned = []
        for item in incorrect_patterns:
            pattern_text = (item.get("pattern") or "").strip()
            match_type = (item.get("match_type") or "").strip().lower()

            if match_type in {"contains", "normalized_contains"} and (
                "return n + n" in pattern_text
                or "return n+n" in pattern_text
                or "def double(n): return n + n" in pattern_text
                or "def double(n): return n+n" in pattern_text
            ):
                continue

            if match_type == "normalized_contains" and pattern_text.replace(" ", "") in {
                "defdouble(n):returnn",
                "defdouble(n):returnn;",
            }:
                item = dict(item)
                item["match_type"] = "regex"
                item["pattern"] = r"(?m)^\s*def\s+double\s*\([^)]*\)\s*:\s*return\s+n\s*;?\s*$"

            if "return n * 3" in pattern_text or "return n*3" in pattern_text:
                item = dict(item)
                item["feedback"] = "This triples the input instead of doubling it."
                item["suggestion"] = "Use n * 2 or n + n to double the value."
                item["score_cap"] = int(item.get("score_cap", 20) or 20)

            pruned.append(item)
        incorrect_patterns = pruned
    cleaned_patterns = []
    for item in incorrect_patterns:
        feedback = (item.get("feedback") or "").lower()
        if ("safe fallback" in feedback and "primary review" in feedback) or (
            "retry the evaluation" in feedback and "rule-based checks" in feedback
        ):
            continue
        cleaned_patterns.append(item)
    incorrect_patterns = _sanitize_incorrect_patterns_for_family(
        cleaned_patterns,
        template_family,
        finalized.get("question"),
    )
    finalized["incorrect_patterns"] = incorrect_patterns

    all_tests = positive_tests + negative_tests

    finalized["package_status"] = "generated" if all_tests else "draft"
    finalized["package_confidence"] = 0.35 if all_tests else 0.1
    finalized["review_required"] = True
    finalized["package_summary"] = "Generated package content pending validation."

    if language in {"html", "css", "react", "mysql", "mongodb"}:
        if language == "html":
            return _finalize_from_syntax_result(
                finalized,
                check_html_syntax(model_answer),
                "HTML package ready for static review.",
                confidence=0.72,
            )
        if language == "css":
            return _finalize_from_syntax_result(
                finalized,
                check_css_syntax(model_answer),
                "CSS package ready for static review.",
                confidence=0.72,
            )
        if language == "react":
            return _finalize_from_syntax_result(
                finalized,
                check_react_syntax(model_answer),
                "React package ready for static review.",
                confidence=0.7,
            )
        if language == "mysql":
            return _finalize_from_syntax_result(
                finalized,
                check_mysql_syntax(model_answer),
                "MySQL package ready for static review.",
                confidence=0.74,
            )
        if language == "mongodb":
            return _finalize_from_syntax_result(
                finalized,
                check_mongodb_syntax(model_answer),
                "MongoDB package ready for static review.",
                confidence=0.74,
            )

    if not all_tests:
        finalized["package_summary"] = "No generated test sets available yet."
        return finalized

    if language == "python":
        def _parse_json_value(value):
            if value is None:
                return None
            if isinstance(value, str):
                try:
                    return json.loads(value)
                except Exception:
                    return value
            return value

        def _build_test_cases(test_cases):
            cases = []
            for item in test_cases:
                parsed_input = _parse_json_value(item.get("input"))
                parsed_expected = _parse_json_value(item.get("expected_output"))
                if parsed_expected is None:
                    continue
                if isinstance(parsed_input, list):
                    args = tuple(parsed_input)
                elif parsed_input is None:
                    continue
                else:
                    args = (parsed_input,)
                cases.append((args, parsed_expected))
            return cases

        def _filter_accepted_solutions(candidates, cases):
            if not cases:
                return candidates
            filtered = []
            inputs = [case[0] for case in cases]
            expected = [case[1] for case in cases]
            for item in candidates:
                if not isinstance(item, str) or not item.strip():
                    continue
                code, fn_name = _wrap_python_snippet(item, question_text)
                if not code or not fn_name:
                    continue
                result = _run_code_with_timeout(code, fn_name, inputs)
                if not result or not result.get("ok"):
                    continue
                outputs = result.get("outputs") or []
                if len(outputs) != len(inputs):
                    continue
                ok = True
                for output, exp in zip(outputs, expected):
                    if not output.get("ok"):
                        ok = False
                        break
                    value = output.get("result")
                    if isinstance(exp, bool) and not isinstance(value, bool):
                        ok = False
                        break
                    if not _smart_outputs_equal(exp, value, question_text):
                        ok = False
                        break
                if ok:
                    filtered.append(item)
            return filtered

        execution_cases = _build_test_cases(positive_tests + negative_tests)
        if execution_cases:
            filtered = _filter_accepted_solutions(finalized.get("accepted_solutions", []), execution_cases)
            if not filtered and model_answer:
                filtered = [model_answer]
            finalized["accepted_solutions"] = filtered[: AUTO_GENERATE_MAX_ALTERNATIVES + 1]

    incorrect_patterns = []
    pattern_map = {}
    pattern_order = []
    for item in finalized.get("incorrect_patterns", []) or []:
        normalized = _normalize_incorrect_pattern(item)
        if not normalized:
            continue
        key = (normalized.get("pattern"), normalized.get("match_type"))
        if key not in pattern_map:
            pattern_order.append(key)
        pattern_map[key] = normalized
    for key in pattern_order:
        incorrect_patterns.append(pattern_map[key])
    if template_family == "python::positive_number" or "positive number" in question_text or "is positive" in question_text:
        for item in incorrect_patterns:
            pattern_text = (item.get("pattern") or "")
            if (">= 0" in pattern_text or ">=0" in pattern_text) and "positive" in (item.get("feedback") or ""):
                item["feedback"] = (
                    "Treating zero as positive does not satisfy the strict positive-number requirement, since zero is neither positive nor negative."
                )
    if template_family == "python::double_number" or "double a number" in question_text:
        pruned = []
        for item in incorrect_patterns:
            pattern_text = (item.get("pattern") or "").strip()
            match_type = (item.get("match_type") or "").strip().lower()

            if match_type in {"contains", "normalized_contains"} and (
                "return n + n" in pattern_text
                or "return n+n" in pattern_text
                or "def double(n): return n + n" in pattern_text
                or "def double(n): return n+n" in pattern_text
            ):
                continue

            if match_type == "normalized_contains" and pattern_text.replace(" ", "") in {
                "defdouble(n):returnn",
                "defdouble(n):returnn;",
            }:
                item = dict(item)
                item["match_type"] = "regex"
                item["pattern"] = r"(?m)^\s*def\s+double\s*\([^)]*\)\s*:\s*return\s+n\s*;?\s*$"

            if "return n * 3" in pattern_text or "return n*3" in pattern_text:
                item = dict(item)
                item["feedback"] = "This triples the input instead of doubling it."
                item["suggestion"] = "Use n * 2 or n + n to double the value."
                item["score_cap"] = int(item.get("score_cap", 20) or 20)

            pruned.append(item)
        incorrect_patterns = pruned
    cleaned_patterns = []
    for item in incorrect_patterns:
        feedback = (item.get("feedback") or "").lower()
        if ("safe fallback" in feedback and "primary review" in feedback) or (
            "retry the evaluation" in feedback and "rule-based checks" in feedback
        ):
            continue
        cleaned_patterns.append(item)
    incorrect_patterns = _sanitize_incorrect_patterns_for_family(
        cleaned_patterns,
        template_family,
        finalized.get("question"),
    )
    finalized["incorrect_patterns"] = incorrect_patterns

    all_tests = positive_tests + negative_tests

    finalized["package_status"] = "generated" if all_tests else "draft"
    finalized["package_confidence"] = 0.35 if all_tests else 0.1
    finalized["review_required"] = True
    finalized["package_summary"] = "Generated package content pending validation."

    if language in {"html", "css", "react", "mysql", "mongodb"}:
        if language == "html":
            return _finalize_from_syntax_result(
                finalized,
                check_html_syntax(model_answer),
                "HTML package ready for static review.",
                confidence=0.72,
            )
        if language == "css":
            return _finalize_from_syntax_result(
                finalized,
                check_css_syntax(model_answer),
                "CSS package ready for static review.",
                confidence=0.72,
            )
        if language == "react":
            return _finalize_from_syntax_result(
                finalized,
                check_react_syntax(model_answer),
                "React package ready for static review.",
                confidence=0.7,
            )
        if language == "mysql":
            return _finalize_from_syntax_result(
                finalized,
                check_mysql_syntax(model_answer),
                "MySQL package ready for static review.",
                confidence=0.74,
            )
        if language == "mongodb":
            return _finalize_from_syntax_result(
                finalized,
                check_mongodb_syntax(model_answer),
                "MongoDB package ready for static review.",
                confidence=0.74,
            )

    if not all_tests:
        finalized["package_summary"] = "No generated test sets available yet."
        return finalized

    if language == "python":
        repaired_answer = normalize_python_structure(model_answer)

        actual_code, function_name = _wrap_python_snippet(repaired_answer, finalized.get("question", ""))
        if not function_name:
            finalized["package_status"] = "draft"
            finalized["package_summary"] = "Could not validate the registered model answer because no Python function or valid snippet was found."
            finalized["package_confidence"] = 0.15
            finalized["exam_ready"] = False
            return finalized

        cases = [_parse_hidden_test_input(item.get("input")) for item in all_tests]
        expected_outputs = [_parse_expected_output(item.get("expected_output")) for item in all_tests]

        run_result = _run_code_with_timeout(actual_code, function_name, cases)

        if not run_result.get("ok") and repaired_answer != model_answer:
            raw_code, raw_fn = _wrap_python_snippet(model_answer, finalized.get("question", ""))
            if raw_fn:
                run_result = _run_code_with_timeout(raw_code, raw_fn, cases)
                if run_result.get("ok"):
                    actual_code = raw_code
                    function_name = raw_fn

        if not run_result.get("ok"):
            finalized["package_status"] = "draft"
            error_msg = run_result.get('error', 'execution error')
            finalized["package_summary"] = f"Model answer validation failed: {error_msg}. Check for unhashable types or syntax errors."
            finalized["package_confidence"] = 0.15
            finalized["exam_ready"] = False
            return finalized

        if run_result.get("ok") and actual_code.startswith("def ") and "model_answer" in finalized:
            finalized["model_answer"] = actual_code
            if "accepted_solutions" in finalized:
                if actual_code not in finalized["accepted_solutions"]:
                    finalized["accepted_solutions"].insert(0, actual_code)

        outputs = run_result.get("outputs", [])
        passed = 0
        for expected, actual in zip(expected_outputs, outputs):
            if actual.get("ok") and _smart_outputs_equal(actual.get("result"), expected):
                passed += 1
        return _finalize_from_validation_result(finalized, len(all_tests), passed, "Python package ready.")

    if language == "java":
        result = evaluate_java_hidden_tests(model_answer, all_tests)
        if result is None:
            finalized["package_summary"] = "Generated Java package content. Validation will activate automatically on systems with a JDK."
            finalized["package_confidence"] = 0.4
            finalized["review_required"] = True
            finalized["exam_ready"] = False
            return finalized
        passed = len(all_tests) if result.get("result_type") == "full_pass" else int(result.get("passed_cases", 0) or 0)
        return _finalize_from_validation_result(finalized, len(all_tests), passed, "Java package ready.")

    if language == "javascript":
        result = evaluate_javascript_hidden_tests(model_answer, all_tests)
        if result is None:
            syntax_result = check_javascript_syntax(model_answer)
            return _finalize_from_syntax_result(
                finalized,
                syntax_result,
                "JavaScript package ready for static review.",
                confidence=0.68,
            )
        passed = len(all_tests) if result.get("result_type") == "full_pass" else int(result.get("passed_cases", 0) or 0)
        return _finalize_from_validation_result(finalized, len(all_tests), passed, "JavaScript package ready.")

    finalized["package_summary"] = "Generated package content. Automated validation is currently strongest for Python and Java."
    finalized["package_confidence"] = 0.45 if accepted else 0.3
    finalized["review_required"] = True
    finalized["exam_ready"] = False
    return finalized
