# AI Intelligent Evaluation Model

A FastAPI-based code evaluation service for academy and LMS use cases. It evaluates student code answers using a hybrid pipeline that combines:

- GGUF-based local LLM evaluation
- rule-based validation
- execution-based checks for common Python questions
- rubric and concept scoring

The API is designed so an external app or LMS can send one student or many students, with one question or many questions, through a single endpoint.

## Features

- Single unified evaluation API: `POST /evaluate/students`
- Supports:
  - one student, one question
  - one student, multiple questions
  - multiple students, one question each
  - multiple students, multiple questions each
- Local GGUF inference using `llama-cpp-python`
- Controlled parallel evaluation for multiple students
- Rule-based corrections for common code-evaluation mistakes
- Execution-based validation for common Python question patterns
- App-friendly response format with:
  - per-student summary
  - per-question score
  - concepts
  - detailed feedback

## Tech Stack

- Python
- FastAPI
- Uvicorn
- `llama-cpp-python`
- Local GGUF model

## Current API

The main evaluation API is:

`POST /evaluate/students`

If running locally, use:

`http://127.0.0.1:8000/evaluate/students`

Supporting routes:

- `GET /`
- `GET /health`

## Supported Input Cases

The same endpoint supports all of these:

1. One student, one question
2. One student, multiple questions
3. Multiple students, one question each
4. Multiple students, multiple questions each

This is possible because the request shape is:

- `students`: a list of students
- `submissions`: a list of question submissions per student

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

### Request Fields

- `student_id`: unique student identifier
- `submissions`: list of question attempts for that student
- `question_id`: optional question identifier
- `question`: original question text
- `model_answer`: expected/sample answer
- `student_answer`: student submission
- `language`: programming language, for example `python`

## Response Format

```json
{
  "execution_time": 10.526,
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
            "feedback": "Code is correct and follows good structure and readability practices."
          }
        }
      ]
    }
  ]
}
```

### Response Notes

- `execution_time`: total API processing time
- `question_count`: number of questions evaluated for the student
- `total_score`: sum of that student’s question scores
- `score`: score for a single question
- `concepts`: qualitative evaluation summary
- `feedback`: detailed feedback for the student answer

If a question fails validation or evaluation, an `error` field may appear for that question item.

## Example Payloads

### 1. One Student, One Question

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

### 2. One Student, Multiple Questions

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

### 3. Multiple Students, One Question Each

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

### 4. Multiple Students, Multiple Questions

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

## Scoring System

The final score is out of `100`.

### Rubric Weights

- `correctness`: 40
- `efficiency`: 20
- `readability`: 15
- `structure`: 15

Rubric subtotal: `90`

### Concept Weights

- `logic`: 4
- `edge_cases`: 2
- `completeness`: 2
- `efficiency`: 1
- `readability`: 1

Concept subtotal: `10`

### Final Score

`rubric total (90) + concept total (10) = 100`

## Evaluation Pipeline

For each question submission, the service performs:

1. Input cleaning and validation
2. Syntax checking
3. Line analysis
4. Structure analysis
5. Prompt generation
6. Local GGUF LLM evaluation
7. LLM response parsing
8. Rubric score calculation
9. Rule-based correction
10. Execution-based validation for common Python question types
11. Concept evaluation
12. Final score combination and normalization
13. Response formatting

## Accuracy Approach

This project does not rely only on the LLM for scoring.

It uses a hybrid evaluation method:

- LLM for initial reasoning and feedback
- rule-based checks for known patterns
- execution-based checks for common Python questions
- score normalization to reduce unstable LLM scoring

This improves consistency significantly over pure LLM scoring.

## Performance Notes

- The API uses controlled concurrency for multiple students.
- Current student-level processing is parallelized with a thread pool.
- GGUF inference itself is guarded by locks to keep the shared local model stable.
- Large requests can still take time, especially with many students and many questions.

Current validation limits:

- maximum `20` students per request
- maximum `20` questions per student

## Setup

### 1. Create and activate a virtual environment

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

### 2. Install dependencies

Install the project dependencies you use in your environment. At minimum, this project needs FastAPI, Uvicorn, Requests, Pydantic, and `llama-cpp-python`.

Example:

```powershell
pip install fastapi uvicorn requests pydantic llama-cpp-python
```

### 3. Add the GGUF model

Place the model file at:

`models/Phi-3-mini-4k-instruct-q4.gguf`

This path is configured in [config.py](/c:/DSA%20ICT/Internship/ai-intelligent-evaluation-model/config.py).

### 4. Run the server

```powershell
python -m uvicorn app:app --reload
```

### 5. Open Swagger docs

`http://127.0.0.1:8000/docs`

## App Integration Recommendation

For app or LMS integration, the recommended flow is:

1. Frontend sends evaluation data to the app backend
2. App backend calls `POST /evaluate/students`
3. This service returns evaluation results
4. App backend stores or forwards the results to the frontend

This is better than calling the model API directly from the frontend.

## Project Structure

```text
ai-intelligent-evaluation-model/
├── app.py
├── config.py
├── schemas.py
├── analysis/
│   ├── line_analyzer.py
│   ├── structure_analyzer.py
│   └── syntax_checker/
├── evaluator/
│   ├── concept_evaluator.py
│   ├── execution_engine.py
│   ├── main_evaluator.py
│   ├── rubric_engine.py
│   ├── rule_engine.py
│   └── scoring_engine.py
├── llm/
│   ├── llm_engine.py
│   ├── prompt_builder.py
│   └── response_parser.py
├── models/
│   └── Phi-3-mini-4k-instruct-q4.gguf
├── services/
├── tests/
├── utils/
└── logs/
```

## Limitations

- 100% accuracy is not realistic for unrestricted open-ended code evaluation.
- Accuracy is strongest for academy-style questions with clear expected behavior.
- Performance depends on local machine resources and GGUF model speed.
- Very large batches may need chunking or background job processing in a production LMS.

## Recommended Next Improvements

- add persistent database storage for evaluation history
- add async job processing for large academy batches
- add `exam_id`, `course_id`, `subject`, and `max_marks`
- expand execution-based test coverage for your academy syllabus
- add faculty override and re-evaluation workflow

## License

Use the license policy defined for your organization or project.
