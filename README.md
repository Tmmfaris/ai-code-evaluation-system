# AI Intelligent Evaluation Model

This project is a FastAPI service for evaluating student coding answers for academy and LMS workflows. It uses a hybrid scoring pipeline so the final result does not depend only on the LLM.

## Overview

The service accepts one unified request shape through `POST /evaluate/students`. That single endpoint supports:

1. one student, one question
2. one student, multiple questions
3. multiple students, one question each
4. multiple students, multiple questions each

The evaluator combines:

- deterministic exact-match shortcuts
- rule-based analysis
- execution-based checks for many Python and Java academy-style questions
- syntax and structure checks
- GGUF-based local LLM fallback for cases not covered by the deterministic path

## API

Main evaluation endpoint:

`POST /evaluate/students`

Local URL:

`http://127.0.0.1:8000/evaluate/students`

Supporting routes:

- `GET /`
- `GET /health`

## Request Format

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

Request fields:

- `student_id`: unique student identifier
- `submissions`: list of question attempts for that student
- `question_id`: optional question identifier
- `question`: original question text
- `model_answer`: expected answer or sample answer
- `student_answer`: submitted student answer
- `language`: language of the answer, such as `python`, `java`, `html`, or `json`

Validation limits:

- maximum `20` students per request
- maximum `20` questions per student

## Response Format

```json
{
  "execution_time": 8.214,
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
            "feedback": "The student answer exactly matches the expected function for adding two numbers."
          }
        }
      ]
    }
  ]
}
```

Response fields:

- `execution_time`: total API processing time in seconds
- `question_count`: number of evaluated questions for the student
- `total_score`: sum of that student's question scores
- `score`: score for one question, out of `100`
- `concepts`: qualitative evaluation summary
- `feedback`: detailed textual feedback

If a question cannot be evaluated normally, the question item may contain an `error` field instead of `data`. Empty student answers are currently handled as structured zero-score results with `feedback: "No answer provided."`

## Scoring

Each question is scored out of `100`.

Rubric component:

- `correctness`: `40`
- `efficiency`: `20`
- `readability`: `15`
- `structure`: `15`

Rubric subtotal: `90`

Concept component:

- `logic`: `4`
- `edge_cases`: `2`
- `completeness`: `2`
- `efficiency`: `1`
- `readability`: `1`

Concept subtotal: `10`

Final score:

`rubric (90) + concepts (10) = 100`

## Evaluation Flow

For each submission, the evaluator uses the following strategy:

1. validate the request fields
2. detect empty answers and return a zero-score result when needed
3. normalize code for exact-match comparison
4. use the exact-match fast path when student and model answers are the same
5. run syntax and structure analysis
6. try deterministic execution and rule-based evaluation
7. fall back to the local GGUF LLM only when no deterministic path applies
8. normalize and format the final score, concepts, and feedback

This hybrid flow makes the system much more stable than pure LLM scoring.

## Supported Languages

Configured language support includes:

- `python`
- `java`
- `html`
- `json`

Current behavior by language:

- `python`: strongest deterministic coverage, including many common academy-style algorithm questions
- `java`: deterministic coverage for many common method-based academy questions
- `html` and `json`: still supported, with syntax/structure checks and LLM-assisted evaluation

## Accuracy Notes

The system is designed for high consistency on controlled academy-style questions, especially where expected behavior is clear.

Strongest areas:

- exact-match answers
- clearly correct vs clearly wrong solutions
- common Python algorithm questions
- common Java method questions
- alternative correct solutions that still produce correct behavior

Important limitation:

- 100% accuracy is not realistic for unrestricted open-ended code evaluation

If you need the highest possible accuracy for one academy, the best path is to expand deterministic execution coverage for that exact syllabus.

## Performance Notes

Current optimizations include:

- thread-based parallel processing for multiple students
- exact-match fast path
- deterministic scoring before LLM fallback
- reduced token usage for LLM fallback

Current thread configuration:

- student-level parallelism uses `ThreadPoolExecutor(max_workers=6)`

Performance still depends on:

- number of students
- number of questions
- how many submissions fall back to the GGUF model
- local machine resources

## Setup

### 1. Create and activate a virtual environment

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

### 2. Install dependencies

At minimum, install the packages used by the API and local model runtime.

```powershell
pip install fastapi uvicorn pydantic requests llama-cpp-python
```

### 3. Add the GGUF model

Place the model file here:

`models/Phi-3-mini-4k-instruct-q4.gguf`

The model path and LLM settings are configured in `config.py`.

### 4. Run the API

```powershell
python -m uvicorn app:app --reload
```

### 5. Open Swagger

`http://127.0.0.1:8000/docs`

## App and LMS Integration

Recommended integration flow:

1. frontend sends evaluation data to your app backend
2. app backend calls `POST /evaluate/students`
3. this API returns structured evaluation results
4. app backend stores the results or forwards them to the frontend

Using the backend as the caller is better than calling this API directly from the frontend.

## Example Use Cases

This one endpoint supports all common academy request shapes.

One student, one question:

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

One student, multiple questions:

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
        },
        {
          "question_id": "q2",
          "question": "Write a function to reverse a string",
          "model_answer": "def reverse(s): return s[::-1]",
          "student_answer": "def reverse(s): return ''.join(reversed(s))",
          "language": "python"
        }
      ]
    }
  ]
}
```

Multiple students, one question each:

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
    },
    {
      "student_id": "102",
      "submissions": [
        {
          "question_id": "q1",
          "question": "Write a function to check if a number is even",
          "model_answer": "def is_even(n): return n % 2 == 0",
          "student_answer": "def is_even(n): return n % 2",
          "language": "python"
        }
      ]
    }
  ]
}
```

Multiple students, multiple questions:

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
        },
        {
          "question_id": "q2",
          "question": "Write a function to reverse a string",
          "model_answer": "def reverse(s): return s[::-1]",
          "student_answer": "def reverse(s): return ''.join(reversed(s))",
          "language": "python"
        }
      ]
    },
    {
      "student_id": "102",
      "submissions": [
        {
          "question_id": "q1",
          "question": "Write a function to find factorial using recursion",
          "model_answer": "def fact(n): return 1 if n == 0 else n * fact(n - 1)",
          "student_answer": "def fact(n): return n * n",
          "language": "python"
        },
        {
          "question_id": "q2",
          "question": "Write a function to remove spaces from a string",
          "model_answer": "def remove_spaces(s): return s.replace(' ', '')",
          "student_answer": "def remove_spaces(s): return ''.join(s.split())",
          "language": "python"
        }
      ]
    }
  ]
}
```

## Project Structure

```text
ai-intelligent-evaluation-model/
|-- app.py
|-- config.py
|-- schemas.py
|-- analysis/
|   |-- line_analyzer.py
|   |-- structure_analyzer.py
|   `-- syntax_checker/
|-- evaluator/
|   |-- concept_evaluator.py
|   |-- execution_engine.py
|   |-- main_evaluator.py
|   |-- rubric_engine.py
|   |-- rule_engine.py
|   `-- scoring_engine.py
|-- llm/
|   |-- llm_engine.py
|   |-- prompt_builder.py
|   `-- response_parser.py
|-- models/
|   `-- Phi-3-mini-4k-instruct-q4.gguf
|-- tests/
|-- utils/
`-- logs/
```

## Recommended Next Improvements

- add persistent evaluation storage
- add async job processing for large academy batches
- add exam metadata such as `exam_id`, `course_id`, `subject`, and `max_marks`
- expand deterministic coverage for more syllabus-specific questions
- add faculty review and manual override workflow

## License

Use the license policy defined for your organization or project.
