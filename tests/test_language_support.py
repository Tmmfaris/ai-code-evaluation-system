import os
import sys


sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from analysis.syntax_checker import check_syntax
from evaluator.question_classifier import classify_question


def test_css_support():
    result = check_syntax("h1 { color: red; }", "css")
    assert result["valid"] is True


def test_react_support():
    code = "export default function App(){ return (<div>Hello</div>); }"
    result = check_syntax(code, "react")
    assert result["valid"] is True


def test_mysql_support():
    result = check_syntax("SELECT * FROM students;", "mysql")
    assert result["valid"] is True


def test_mongodb_support():
    result = check_syntax("db.students.find({ active: true })", "mongodb")
    assert result["valid"] is True


def test_question_classifier_for_react():
    profile = classify_question("Build a React component to render a student card", "react")
    assert profile["category"] == "frontend_component"
    assert profile["risk"] == "high"
