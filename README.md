# AI Intelligent Evaluation Model

FastAPI service for evaluating student coding answers with deterministic rules, execution checks, question packages, and LLM fallback.

## What It Does

- evaluates one or many students in one request
- supports multiple questions per student
- supports direct evaluation with `question + model_answer + language`
- supports reusable registered question packages
- combines exact match, rules, execution checks, syntax checks, and local LLM fallback
- stores package/history/learning data in SQLite

## Main Endpoint

- `POST /evaluate/students`

Main routes:

- `GET /`
- `GET /health`
- `POST /evaluate/students`
- `POST /questions/register`

## Supported Languages

- `python`
- `java`
- `javascript`
- `html`
- `css`
- `react`
- `mongodb`
- `mysql`

Current strongest deterministic coverage:

- `python`
- `java`
- `javascript` for common academy-style patterns

## Evaluation Request

```json
{
  "students": [
    {
      "student_id": "101",
      "submissions": [
        {
          "question": "Write a function to add two numbers",
          "model_answer": "def add(a, b): return a + b",
          "student_answer": "def add(a, b): return a + b",
          "language": "python"
        }
      ]
    }
  ]
}
```

Limits:

- max `20` students per request
- max `20` submissions per student

## Evaluation Response

```json
{
  "execution_time": 1.24,
  "students": [
    {
      "student_id": "101",
      "question_count": 1,
      "total_score": 100,
      "questions": [
        {
          "question_id": "q1",
          "data": {
            "score": 100,
            "concepts": {
              "logic": "Strong",
              "edge_cases": "Good",
              "completeness": "High",
              "efficiency": "Good",
              "readability": "Good"
            },
            "feedback": "The student answer exactly matches the expected function."
          }
        }
      ]
    }
  ]
}
```

## Scoring

Each question is scored out of `100`.

- rubric: `90`
- concepts: `10`

Rubric split:

- correctness: `40`
- efficiency: `20`
- readability: `15`
- structure: `15`

## Evaluation Flow

1. validate and normalize input
2. load direct question context or registered package data
3. use exact-match shortcut when possible
4. run syntax, structure, deterministic rules, and execution checks
5. use question-package accepted solutions, hidden tests, and incorrect patterns
6. use local GGUF LLM only when needed
7. apply score calibration and confidence bounds
8. return structured score, concepts, and feedback

## Evaluation Modes

- direct mode
  - send `question + model_answer + student_answer + language`
  - useful when you want immediate evaluation without registering a package first
- package mode
  - register questions first with `POST /questions/register`
  - later evaluate using the same question content or a registered package context
  - useful for reuse, stronger hidden tests, and more stable scoring

## Evaluation Layers

- exact match
  - fastest path when the student answer matches the expected answer or an accepted equivalent
- deterministic rules
  - catches common known patterns quickly and consistently
- execution and hidden tests
  - strongest for runnable languages when the question package contains hidden tests
- package support data
  - uses stored `accepted_solutions`, `test_sets`, and `incorrect_patterns`
- LLM fallback
  - used only when the earlier layers are not enough

## Evaluation Output

Each evaluated question returns:

- `score`
- `concepts`
- `logic_evaluation`
- `feedback`

Each student result returns:

- `student_id`
- `question_count`
- `total_score`
- per-question results

## Question Packages

- evaluation can run directly with `question + model_answer + language`
- faculty can register bulk question packages with `POST /questions/register`
- registration builds reusable package data:
  - `accepted_solutions`
  - `test_sets`
  - `incorrect_patterns`
  - `template_family`
  - `package_status`
  - `package_confidence`
  - `approval_status`
  - `exam_ready`
- `question_id` is optional at registration time
- stored packages use question content/signature for reuse, not `question_id`
- `question_id` is only an evaluation-time label/reference when you choose to send it
- reuse is based on question content, normalized question signature, language, and template family

### Package Registration Example

```json
{
  "questions": [
    {
      "question": "Write a function to add two numbers",
      "model_answer": "def add(a,b): return a+b",
      "language": "python"
    },
    {
      "question": "Reverse a string",
      "model_answer": "def reverse(s): return s[::-1]",
      "language": "python"
    }
  ]
}
```

## Setup

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install fastapi uvicorn pydantic requests llama-cpp-python
python -m uvicorn app:app --reload
```

Swagger:

- `http://127.0.0.1:8000/docs`

Model file expected at:

- `models/Phi-3-mini-4k-instruct-q4.gguf`

## Storage

Global deterministic rules stay in code:

- `evaluator/rules/`
- `evaluator/execution/shared.py`
- `evaluator/question_rule_generator.py`

Dynamic package and history data stay in SQLite:

- question packages: `data/question_profiles.db`
- evaluation history: `data/evaluation_history.db`
- learning signals: `data/question_learning.db`

Legacy JSON profile seed:

- `data/question_profiles.json`

## Project Structure

```text
ai-intelligent-evaluation-model/
|-- app.py
|-- config.py
|-- schemas.py
|-- README.md
|
|-- analysis/
|   |-- line_analyzer.py
|   |-- structure_analyzer.py
|   `-- syntax_checker/
|       |-- __init__.py
|       |-- python_checker.py
|       |-- java_checker.py
|       |-- javascript_checker.py
|       |-- html_checker.py
|       |-- css_checker.py
|       |-- react_checker.py
|       |-- mysql_checker.py
|       `-- mongodb_checker.py
|
|-- evaluator/
|   |-- concept_evaluator.py
|   |-- evaluation_history_repository.py
|   |-- evaluation_history_store.py
|   |-- execution_engine.py
|   |-- main_evaluator.py
|   |-- question_classifier.py
|   |-- question_learning_repository.py
|   |-- question_learning_store.py
|   |-- question_profile_repository.py
|   |-- question_profile_store.py
|   |-- question_rule_generator.py
|   |-- comparison/
|   |   |-- answer_comparator.py
|   |   |-- feedback_generator.py
|   |   |-- llm_comparator.py
|   |   |-- logic_checker.py
|   |   |-- logic_summary.py
|   |   `-- score_calibrator.py
|   |-- execution/
|   |   |-- __init__.py
|   |   |-- shared.py
|   |   `-- python_families/
|   |       |-- __init__.py
|   |       |-- strings.py
|   |       |-- lists.py
|   |       `-- numbers.py
|   |-- orchestration/
|   |   |-- __init__.py
|   |   |-- confidence.py
|   |   `-- pipeline.py
|   |-- question_package/
|   |   |-- __init__.py
|   |   |-- approvals.py
|   |   |-- generator.py
|   |   |-- learning.py
|   |   |-- reuser.py
|   |   |-- validator.py
|   |   `-- workflow.py
|   |-- rubric_engine.py
|   |-- rule_engine.py
|   |-- scoring_engine.py
|   `-- rules/
|       |-- __init__.py
|       |-- shared.py
|       |-- javascript_rules.py
|       |-- javascript_families/
|       |   |-- __init__.py
|       |   |-- strings.py
|       |   |-- lists.py
|       |   `-- numbers.py
|       `-- python_families/
|           |-- __init__.py
|           |-- strings.py
|           |-- lists.py
|           `-- numbers.py
|
|-- llm/
|   |-- llm_engine.py
|   |-- prompt_builder.py
|   `-- response_parser.py
|
|-- data/
|   |-- question_profiles.json
|   |-- question_profiles.db
|   |-- evaluation_history.db
|   `-- question_learning.db
|
|-- tests/
|   |-- benchmark_cases.json
|   |-- benchmark_thresholds.json
|   |-- test_benchmark.py
|   |-- test_evaluator.py
|   `-- test_language_support.py
|
`-- utils/
    |-- formatter.py
    |-- helpers.py
    `-- logger.py
```

## Notes

- best accuracy is on controlled academy-style questions
- expanding deterministic coverage improves both speed and consistency
- package workflow is: `generated -> validated -> live`
- post-exam learning can promote repeated strong answers and repeated mistakes into future package improvements
- hidden review routes exist internally for package approval and inspection
- benchmark guards live in `tests/test_benchmark.py`
