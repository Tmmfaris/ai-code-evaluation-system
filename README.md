# AI Intelligent Evaluation Model

FastAPI service for evaluating student coding answers for academy and LMS workflows.

## What It Does

- evaluates one or many students in one request
- supports multiple questions per student
- combines exact match, rules, execution checks, syntax checks, and local LLM fallback
- stores question profiles and evaluation history in SQLite

## Main Endpoint

- `POST /evaluate/students`

Useful routes:

- `GET /`
- `GET /health`
- `POST /questions/register`
- `GET /questions`
- `GET /questions/{question_id}`
- `GET /evaluations`
- `GET /evaluations/students/{student_id}`

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

## Request Shape

```json
{
  "students": [
    {
      "student_id": "101",
      "submissions": [
        {
          "question_id": "q1",
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

## Response Shape

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
2. use exact-match shortcut when possible
3. run syntax, structure, rules, and execution checks
4. use local GGUF LLM only when needed
5. apply score calibration and confidence bounds
6. return structured score, concepts, and feedback

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

SQLite is used by default for:

- question profiles: `data/question_profiles.db`
- evaluation history: `data/evaluation_history.db`

Legacy JSON profile seed:

- `data/question_profiles.json`

## Project Structure

```text
app.py
config.py
analysis/
evaluator/
llm/
data/
tests/
utils/
```

## Notes

- best accuracy is on controlled academy-style questions
- expanding deterministic coverage improves both speed and consistency
- benchmark guards live in `tests/test_benchmark.py`
