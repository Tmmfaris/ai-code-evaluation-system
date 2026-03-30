from pydantic import BaseModel, Field
from typing import Optional, List


# ==============================
# 🔹 INPUT SCHEMAS
# ==============================

class CodeRequest(BaseModel):
    student_id: str = Field(..., example="123")
    question: str = Field(..., example="Write a function to calculate factorial")
    model_answer: str = Field(..., example="def f(n): return 1 if n==0 else n*f(n-1)")
    student_answer: str = Field(..., example="def fact(n): return 1 if n==0 else n*fact(n-1)")
    language: str = Field(..., example="python")


class QuestionSubmission(BaseModel):
    question_id: Optional[str] = Field(None, example="q1")
    question: str = Field(..., example="Write a function to calculate factorial")
    model_answer: str = Field(..., example="def f(n): return 1 if n==0 else n*f(n-1)")
    student_answer: str = Field(..., example="def fact(n): return 1 if n==0 else n*fact(n-1)")
    language: str = Field(..., example="python")


class BatchRequest(BaseModel):
    submissions: List[CodeRequest] = Field(
        ...,
        example=[
            {
                "student_id": "101",
                "question": "Write a function to add two numbers",
                "model_answer": "def add(a,b): return a+b",
                "student_answer": "def add(a,b): return a+b",
                "language": "python"
            },
            {
                "student_id": "102",
                "question": "Write a function to add two numbers",
                "model_answer": "def add(a,b): return a+b",
                "student_answer": "def add(a,b): return a-b",
                "language": "python"
            }
        ]
    )


class StudentEvaluationRequest(BaseModel):
    student_id: str = Field(..., example="123")
    submissions: List[QuestionSubmission] = Field(
        ...,
        example=[
            {
                "question_id": "q1",
                "question": "Write a function to add two numbers",
                "model_answer": "def add(a,b): return a+b",
                "student_answer": "def add(a,b): return a+b",
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
    )


class MultiStudentEvaluationRequest(BaseModel):
    students: List[StudentEvaluationRequest] = Field(
        ...,
        example=[
            {
                "student_id": "123",
                "submissions": [
                    {
                        "question_id": "q1",
                        "question": "Write a function to add two numbers",
                        "model_answer": "def add(a,b): return a+b",
                        "student_answer": "def add(a,b): return a+b",
                        "language": "python"
                    }
                ]
            },
            {
                "student_id": "124",
                "submissions": [
                    {
                        "question_id": "q1",
                        "question": "Write a function to reverse a string",
                        "model_answer": "def reverse(s): return s[::-1]",
                        "student_answer": "def reverse(s): return ''.join(reversed(s))",
                        "language": "python"
                    }
                ]
            }
        ]
    )


# ==============================
# 🔹 EVALUATION SCHEMAS
# ==============================

class RubricScore(BaseModel):
    correctness: int = Field(..., example=40)
    efficiency: int = Field(..., example=20)
    readability: int = Field(..., example=15)
    structure: int = Field(..., example=15)


class ConceptEvaluation(BaseModel):
    logic: str = Field(..., example="Strong")
    edge_cases: str = Field(..., example="Good")
    completeness: str = Field(..., example="High")
    efficiency: str = Field(..., example="Good")
    readability: str = Field(..., example="Good")


class EvaluationResponse(BaseModel):
    score: int = Field(..., example=85)
    concepts: ConceptEvaluation
    feedback: str = Field(..., example="Correct solution. The implementation matches the expected behavior and uses a clear structure.")


# ==============================
# 🔹 SINGLE API RESPONSE
# ==============================

class APIResponse(BaseModel):
    status: str = Field(..., example="success")
    execution_time: float = Field(..., example=1.25)
    data: EvaluationResponse


# ==============================
# 🔹 BATCH RESPONSE SCHEMAS
# ==============================

class BatchResultItem(BaseModel):
    student_id: str = Field(..., example="101")
    status: str = Field(..., example="success")
    data: Optional[EvaluationResponse] = None
    error: Optional[str] = None


class BatchResponse(BaseModel):
    status: str = Field(..., example="success")
    total_students: int = Field(..., example=2)
    execution_time: float = Field(..., example=12.5)
    results: List[BatchResultItem]


class StudentQuestionResultItem(BaseModel):
    question_id: Optional[str] = Field(None, example="q1")
    data: Optional[EvaluationResponse] = None
    error: Optional[str] = None


class StudentEvaluationResponse(BaseModel):
    student_id: str = Field(..., example="123")
    question_count: int = Field(..., example=2)
    total_score: int = Field(..., example=177)
    questions: List[StudentQuestionResultItem]


class MultiStudentEvaluationResponse(BaseModel):
    execution_time: float = Field(..., example=20.5)
    students: List[StudentEvaluationResponse]
