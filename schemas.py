from pydantic import BaseModel, Field
from typing import List, Optional


class HiddenTestCase(BaseModel):
    input: Optional[str] = Field(None, example="[1,2,3]")
    expected_output: Optional[str] = Field(None, example="6")
    description: Optional[str] = Field(None, example="basic positive case")


class QuestionSubmission(BaseModel):
    question_id: Optional[str] = Field(None, example="q1")
    question: Optional[str] = Field(None, example="Write a function to calculate factorial")
    model_answer: Optional[str] = Field(None, example="def f(n): return 1 if n==0 else n*f(n-1)")
    alternative_answers: Optional[List[str]] = Field(
        default=None,
        example=["def fact(n): return 1 if n == 0 else n * fact(n - 1)"],
    )
    hidden_tests: Optional[List[HiddenTestCase]] = None
    student_answer: str = Field(..., example="def fact(n): return 1 if n==0 else n*fact(n-1)")
    language: Optional[str] = Field(None, example="python")


class StudentEvaluationRequest(BaseModel):
    student_id: str = Field(..., example="123")
    llm_review: Optional[bool] = Field(
        default=None,
        example=True,
        description="Force LLM review of score/feedback for this student.",
    )
    llm_review_max_attempts: Optional[int] = Field(
        default=None,
        example=3,
        description="Max LLM review attempts per question for this student.",
    )
    submissions: List[QuestionSubmission] = Field(
        ...,
        example=[
            {
                "question": "Write a function to add two numbers",
                "model_answer": "def add(a,b): return a+b",
                "student_answer": "def add(a,b): return a+b",
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
                        "question": "Write a function to add two numbers",
                        "model_answer": "def add(a,b): return a+b",
                        "student_answer": "def add(a,b): return a+b",
                        "language": "python"
                    },
                    {
                        "question": "Reverse a string",
                        "model_answer": "def reverse(s): return s[::-1]",
                        "student_answer": "def reverse(s): return ''.join(reversed(s))",
                        "language": "python"
                    }
                ]
            }
        ]
    )
    llm_review: Optional[bool] = Field(
        default=None,
        example=True,
        description="Force LLM review of score/feedback for all students.",
    )
    llm_review_max_attempts: Optional[int] = Field(
        default=None,
        example=3,
        description="Max LLM review attempts per question for all students.",
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


class QuestionPackageRequest(BaseModel):
    question_id: Optional[str] = Field(None, example="q-demo")
    question: str = Field(..., example="Write a function to add two numbers")
    model_answer: str = Field(..., example="def add(a,b): return a+b")
    language: str = Field(..., example="python")


class MultiQuestionPackageRequest(BaseModel):
    questions: List[QuestionPackageRequest] = Field(
        ...,
        example=[
            {
                "question": "Write a function to add two numbers",
                "model_answer": "def add(a,b): return a+b",
                "language": "python"
            }
        ],
    )


class QuestionPackageResponse(BaseModel):
    question_id: Optional[str] = None
    question: str
    model_answer: str
    language: str
    profile: dict
    question_signature: str
    template_family: Optional[str] = None
    accepted_solutions: Optional[List[str]] = None
    test_sets: Optional[dict] = None
    incorrect_patterns: Optional[List[dict]] = None
    package_status: Optional[str] = None
    package_summary: Optional[str] = None
    package_confidence: Optional[float] = None
    review_required: Optional[bool] = None
    approval_status: Optional[str] = None
    approved_by: Optional[str] = None
    approved_at: Optional[str] = None
    approval_checklist: Optional[List[dict]] = None
    approval_notes: Optional[str] = None
    positive_test_count: Optional[int] = None
    negative_test_count: Optional[int] = None
    reused_from_questions: Optional[List[str]] = None
    validation_options: Optional[dict] = None


class ApprovalChecklistItem(BaseModel):
    key: str = Field(..., example="question_intent_clear")
    label: str = Field(..., example="Question intent is clear and unambiguous")
    status: bool = Field(..., example=True)
    notes: Optional[str] = Field(None, example="Clarified wording with faculty")


class ApprovalRequest(BaseModel):
    approved_by: Optional[str] = Field("faculty", example="faculty")
    checklist: Optional[List[ApprovalChecklistItem]] = None
    approval_notes: Optional[str] = Field(None, example="Mentor confirmed edge cases")
    question: Optional[str] = None
    model_answer: Optional[str] = None
    language: Optional[str] = None
    accepted_solutions: Optional[List[str]] = None
    test_sets: Optional[dict] = None
    incorrect_patterns: Optional[List[dict]] = None
    package_summary: Optional[str] = None
    package_confidence: Optional[float] = None


class QuestionPackageEditRequest(BaseModel):
    question: Optional[str] = None
    model_answer: Optional[str] = None
    language: Optional[str] = None
    accepted_solutions: Optional[List[str]] = None
    test_sets: Optional[dict] = None
    incorrect_patterns: Optional[List[dict]] = None
    package_status: Optional[str] = None
    package_summary: Optional[str] = None
    package_confidence: Optional[float] = None
    review_required: Optional[bool] = None
    approval_status: Optional[str] = None
    approved_by: Optional[str] = None


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


# Backward-compatible aliases for older imports.
QuestionProfileRequest = QuestionPackageRequest
MultiQuestionProfileRequest = MultiQuestionPackageRequest
QuestionProfileResponse = QuestionPackageResponse
