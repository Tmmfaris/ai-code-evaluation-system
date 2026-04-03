from pydantic import BaseModel, Field
from typing import List, Optional


class QuestionSubmission(BaseModel):
    question_id: Optional[str] = Field(None, example="q1")
    question: Optional[str] = Field(None, example="Write a function to calculate factorial")
    model_answer: Optional[str] = Field(None, example="def f(n): return 1 if n==0 else n*f(n-1)")
    student_answer: str = Field(..., example="def fact(n): return 1 if n==0 else n*fact(n-1)")
    language: Optional[str] = Field(None, example="python")


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


class ConceptEvaluation(BaseModel):
    logic: str = Field(..., example="Strong")
    edge_cases: str = Field(..., example="Good")
    completeness: str = Field(..., example="High")
    efficiency: str = Field(..., example="Good")
    readability: str = Field(..., example="Good")


class EvaluationResponse(BaseModel):
    score: int = Field(..., example=85)
    concepts: ConceptEvaluation
    logic_evaluation: Optional[str] = Field(
        None,
        example="The student used a different approach, but the logic is correct.",
    )
    feedback: str = Field(
        ...,
        example="Correct solution. The implementation matches the expected behavior and uses a clear structure.",
    )


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


class QuestionProfileRequest(BaseModel):
    question_id: str = Field(..., example="q1")
    question: str = Field(..., example="Write a function to calculate factorial")
    model_answer: str = Field(..., example="def fact(n): return 1 if n == 0 else n * fact(n-1)")
    language: str = Field(..., example="python")
    course_id: Optional[str] = Field(None, example="course-101")
    faculty_id: Optional[str] = Field(None, example="faculty-200")
    topic: Optional[str] = Field(None, example="recursion")


class QuestionProfileResponse(BaseModel):
    question_id: str
    question: str
    model_answer: str
    language: str
    course_id: Optional[str] = None
    faculty_id: Optional[str] = None
    topic: Optional[str] = None
    profile: dict


class EvaluationHistoryItem(BaseModel):
    id: int
    student_id: str
    question_id: Optional[str] = None
    question: str
    model_answer: str
    student_answer: str
    language: str
    score: int
    concepts: dict
    feedback: str
    status: str
    error: Optional[str] = None
    created_at: str
