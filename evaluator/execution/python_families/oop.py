# evaluator/execution/python_families/oop.py
"""
Deterministic evaluation rules for Object-Oriented Programming questions.
Covers: class definition, __init__, inheritance, super(), properties,
        static/class methods, abstract classes, magic methods, dataclasses.
"""
import ast
import re


def _has_class_def(student_answer):
    try:
        tree = ast.parse(student_answer or "")
        return any(isinstance(n, ast.ClassDef) for n in ast.walk(tree))
    except Exception:
        return False


def _has_init(student_answer):
    c = (student_answer or "").replace(" ", "")
    return "def__init__" in c


def _has_super_call(student_answer):
    return "super()" in (student_answer or "") or "super().__init__" in (student_answer or "")


def _has_inheritance(student_answer):
    try:
        tree = ast.parse(student_answer or "")
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.bases:
                return True
        return False
    except Exception:
        return re.search(r"class\s+\w+\s*\(", student_answer or "") is not None


def _has_property_decorator(student_answer):
    return "@property" in (student_answer or "")


def _has_abstract_method(student_answer):
    code = student_answer or ""
    return "@abstractmethod" in code or "ABC" in code


def _has_dunder(student_answer, method):
    """Check if a dunder method is defined."""
    return f"def {method}" in (student_answer or "")


def _has_static_method(student_answer):
    return "@staticmethod" in (student_answer or "")


def _has_class_method(student_answer):
    return "@classmethod" in (student_answer or "")


def _has_dataclass(student_answer):
    return "@dataclass" in (student_answer or "")


def evaluate_oop_family(question, question_text, families, normalized_student, student_answer):
    """Evaluate OOP-related Python questions."""
    q = question_text

    # ── Class Definition ────────────────────────────────────────────────────
    if "class" in q or "oop" in q or "object-oriented" in q or "object oriented" in q:
        if not _has_class_def(student_answer):
            # Check if question explicitly requires a class
            if any(kw in q for kw in ("define a class", "create a class", "write a class",
                                       "class with", "class that", "implement a class")):
                return {
                    "result_type": "zero_pass",
                    "correctness_max": 5,
                    "efficiency_max": 5,
                    "feedback": "The answer does not define a class even though the question requires one.",
                    "suggestion": "Use the `class` keyword to define the required class.",
                }

    # ── __init__ / Constructor ───────────────────────────────────────────────
    if any(kw in q for kw in ("constructor", "__init__", "initialize", "initialise")):
        if _has_class_def(student_answer):
            if not _has_init(student_answer):
                return {
                    "result_type": "zero_pass",
                    "correctness_max": 8,
                    "efficiency_max": 8,
                    "feedback": "The class is missing the required `__init__` constructor method.",
                    "suggestion": "Define `def __init__(self, ...)` inside the class to initialize attributes.",
                }
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": "The class correctly defines an `__init__` constructor to initialize instance attributes.",
            }

    # ── Inheritance ─────────────────────────────────────────────────────────
    if any(kw in q for kw in ("inherit", "subclass", "parent class", "child class", "base class", "derived class")):
        if _has_class_def(student_answer):
            if not _has_inheritance(student_answer):
                return {
                    "result_type": "zero_pass",
                    "correctness_max": 8,
                    "efficiency_max": 8,
                    "feedback": "The class does not inherit from the required parent class.",
                    "suggestion": "Pass the parent class name inside the parentheses of the class definition: `class Child(Parent):`.",
                }
            if "super" in q and not _has_super_call(student_answer):
                return {
                    "result_type": "mostly_correct",
                    "correctness_max": 28,
                    "feedback": "The class inherits correctly, but it does not call `super().__init__()` to initialize the parent.",
                    "suggestion": "Call `super().__init__(...)` inside the child's `__init__` to properly initialize the parent.",
                }
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": "The class correctly inherits from the parent and initializes properly.",
            }

    # ── @property ────────────────────────────────────────────────────────────
    if "property" in q or "@property" in q or "getter" in q or "setter" in q:
        if _has_class_def(student_answer):
            if not _has_property_decorator(student_answer):
                return {
                    "result_type": "zero_pass",
                    "correctness_max": 8,
                    "efficiency_max": 8,
                    "feedback": "The class does not use the `@property` decorator even though the question requires a property.",
                    "suggestion": "Decorate the getter method with `@property` and the setter with `@<name>.setter`.",
                }
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": "The class correctly implements a property using the `@property` decorator.",
            }

    # ── @staticmethod ────────────────────────────────────────────────────────
    if "static method" in q or "staticmethod" in q:
        if _has_class_def(student_answer):
            if not _has_static_method(student_answer):
                return {
                    "result_type": "zero_pass",
                    "correctness_max": 8,
                    "efficiency_max": 8,
                    "feedback": "The class does not define a static method even though the question requires one.",
                    "suggestion": "Decorate the method with `@staticmethod` and remove `self` from its parameters.",
                }
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": "The class correctly defines a static method using `@staticmethod`.",
            }

    # ── @classmethod ─────────────────────────────────────────────────────────
    if "class method" in q or "classmethod" in q:
        if _has_class_def(student_answer):
            if not _has_class_method(student_answer):
                return {
                    "result_type": "zero_pass",
                    "correctness_max": 8,
                    "efficiency_max": 8,
                    "feedback": "The class does not define a class method even though the question requires one.",
                    "suggestion": "Decorate the method with `@classmethod` and use `cls` as the first parameter.",
                }
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": "The class correctly defines a class method using `@classmethod`.",
            }

    # ── Abstract Class ───────────────────────────────────────────────────────
    if "abstract" in q or "abc" in q:
        if _has_class_def(student_answer):
            if not _has_abstract_method(student_answer):
                return {
                    "result_type": "zero_pass",
                    "correctness_max": 8,
                    "efficiency_max": 8,
                    "feedback": "The class does not use `@abstractmethod` even though the question requires an abstract class.",
                    "suggestion": "Import `ABC` and `abstractmethod` from `abc`, inherit from `ABC`, and decorate abstract methods.",
                }
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": "The abstract class correctly defines the required abstract method(s).",
            }

    # ── Magic Methods ────────────────────────────────────────────────────────
    if "__str__" in q or "string representation" in q or "__repr__" in q:
        if _has_class_def(student_answer):
            if not _has_dunder(student_answer, "__str__") and not _has_dunder(student_answer, "__repr__"):
                return {
                    "result_type": "zero_pass",
                    "correctness_max": 8,
                    "feedback": "The class does not define `__str__` or `__repr__` for string representation.",
                    "suggestion": "Define `def __str__(self): return ...` inside the class.",
                }
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": "The class correctly defines a string representation method.",
            }

    if "__len__" in q or "length of" in q and "class" in q:
        if _has_class_def(student_answer) and _has_dunder(student_answer, "__len__"):
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": "The class correctly implements `__len__` to support `len()` calls.",
            }

    if "__eq__" in q or "equality" in q and "class" in q:
        if _has_class_def(student_answer):
            if _has_dunder(student_answer, "__eq__"):
                return {
                    "result_type": "full_pass",
                    "correctness_min": 36,
                    "feedback": "The class correctly implements `__eq__` for equality comparison.",
                }

    if "__add__" in q or "operator overload" in q or "overload" in q and "+" in q:
        if _has_class_def(student_answer):
            if _has_dunder(student_answer, "__add__"):
                return {
                    "result_type": "full_pass",
                    "correctness_min": 36,
                    "feedback": "The class correctly overloads the `+` operator using `__add__`.",
                }
            return {
                "result_type": "zero_pass",
                "correctness_max": 8,
                "feedback": "The class does not implement `__add__` for operator overloading.",
                "suggestion": "Define `def __add__(self, other): return ...` inside the class.",
            }

    # ── Dataclass ────────────────────────────────────────────────────────────
    if "dataclass" in q:
        if not _has_dataclass(student_answer):
            return {
                "result_type": "zero_pass",
                "correctness_max": 8,
                "feedback": "The answer does not use the `@dataclass` decorator.",
                "suggestion": "Import `dataclass` from `dataclasses` and decorate the class with `@dataclass`.",
            }
        return {
            "result_type": "full_pass",
            "correctness_min": 36,
            "feedback": "The dataclass is correctly defined with the required fields.",
        }

    return None
