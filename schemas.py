from pydantic import BaseModel, Field
from typing import List, Optional


def _example(value):
    return {"example": value}


class HiddenTestCase(BaseModel):
    input: Optional[str] = Field(None, json_schema_extra=_example("[1,2,3]"))
    expected_output: Optional[str] = Field(None, json_schema_extra=_example("6"))
    description: Optional[str] = Field(None, json_schema_extra=_example("basic positive case"))


class QuestionSubmission(BaseModel):
    question_id: Optional[str] = Field(None, json_schema_extra=_example("q1"))
    question: Optional[str] = Field(None, json_schema_extra=_example("Write a function to calculate factorial"))
    model_answer: Optional[str] = Field(None, json_schema_extra=_example("def f(n): return 1 if n==0 else n*f(n-1)"))
    alternative_answers: Optional[List[str]] = Field(
        default=None,
        json_schema_extra=_example(["def fact(n): return 1 if n == 0 else n * fact(n - 1)"]),
    )
    hidden_tests: Optional[List[HiddenTestCase]] = None
    student_answer: str = Field(..., json_schema_extra=_example("def fact(n): return 1 if n==0 else n*fact(n-1)"))
    language: Optional[str] = Field(None, json_schema_extra=_example("python"))


class StudentEvaluationRequest(BaseModel):
    student_id: str = Field(..., json_schema_extra=_example("123"))
    llm_review: Optional[bool] = Field(
        default=None,
        json_schema_extra=_example(True),
        description="Force LLM review of score/feedback for this student.",
    )
    llm_review_max_attempts: Optional[int] = Field(
        default=None,
        json_schema_extra=_example(3),
        description="Max LLM review attempts per question for this student.",
    )
    submissions: List[QuestionSubmission] = Field(
        ...,
        json_schema_extra=_example([
            {
                "question": "Write a function to add two numbers",
                "model_answer": "def add(a,b): return a+b",
                "student_answer": "def add(a,b): return a+b",
                "language": "python"
            }
        ]),
    )


class MultiStudentEvaluationRequest(BaseModel):
    students: List[StudentEvaluationRequest] = Field(
        ...,
        json_schema_extra=_example([
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
        ]),
    )
    llm_review: Optional[bool] = Field(
        default=None,
        json_schema_extra=_example(True),
        description="Force LLM review of score/feedback for all students.",
    )
    llm_review_max_attempts: Optional[int] = Field(
        default=None,
        json_schema_extra=_example(3),
        description="Max LLM review attempts per question for all students.",
    )


class ConceptEvaluation(BaseModel):
    logic: str = Field(..., json_schema_extra=_example("Strong"))
    edge_cases: str = Field(..., json_schema_extra=_example("Good"))
    completeness: str = Field(..., json_schema_extra=_example("High"))
    efficiency: str = Field(..., json_schema_extra=_example("Good"))
    readability: str = Field(..., json_schema_extra=_example("Good"))


class EvaluationResponse(BaseModel):
    score: int = Field(..., json_schema_extra=_example(85))
    concepts: ConceptEvaluation
    logic_evaluation: Optional[str] = Field(
        None,
        json_schema_extra=_example("The student used a different approach, but the logic is correct."),
    )
    feedback: str = Field(
        ...,
        json_schema_extra=_example("Correct solution. The implementation matches the expected behavior and uses a clear structure."),
    )


class StudentQuestionResultItem(BaseModel):
    question_id: Optional[str] = Field(None, json_schema_extra=_example("q1"))
    data: Optional[EvaluationResponse] = None
    error: Optional[str] = None


class StudentEvaluationResponse(BaseModel):
    student_id: str = Field(..., json_schema_extra=_example("123"))
    question_count: int = Field(..., json_schema_extra=_example(2))
    total_score: int = Field(..., json_schema_extra=_example(177))
    questions: List[StudentQuestionResultItem]


class MultiStudentEvaluationResponse(BaseModel):
    execution_time: float = Field(..., json_schema_extra=_example(20.5))
    students: List[StudentEvaluationResponse]


class QuestionPackageRequest(BaseModel):
    question_id: Optional[str] = Field(None, json_schema_extra=_example("q-demo"))
    question: str = Field(..., json_schema_extra=_example("Write a function to add two numbers"))
    model_answer: str = Field(..., json_schema_extra=_example("def add(a,b): return a+b"))
    language: str = Field(..., json_schema_extra=_example("python"))


class MultiQuestionPackageRequest(BaseModel):
    questions: List[QuestionPackageRequest] = Field(
        ...,
        json_schema_extra=_example([
            {
                "question": "Write a function to add two numbers",
                "model_answer": "def add(a,b): return a+b",
                "language": "python"
            }
        ]),
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
    hidden_tests: Optional[List[dict]] = None
    test_sets: Optional[dict] = None
    incorrect_patterns: Optional[List[dict]] = None
    package_status: Optional[str] = None
    package_summary: Optional[str] = None
    package_confidence: Optional[float] = None
    review_required: Optional[bool] = None
    exam_ready: Optional[bool] = None
    approval_status: Optional[str] = None
    approved_by: Optional[str] = None
    approved_at: Optional[str] = None
    approval_checklist: Optional[List[dict]] = None
    approval_notes: Optional[str] = None
    positive_test_count: Optional[int] = None
    negative_test_count: Optional[int] = None
    reused_from_questions: Optional[List[str]] = None
    llm_assisted: Optional[bool] = None
    generation_sources: Optional[List[str]] = None
    validation_options: Optional[dict] = None


class ApprovalChecklistItem(BaseModel):
    key: str = Field(..., json_schema_extra=_example("question_intent_clear"))
    label: str = Field(..., json_schema_extra=_example("Question intent is clear and unambiguous"))
    status: bool = Field(..., json_schema_extra=_example(True))
    notes: Optional[str] = Field(None, json_schema_extra=_example("Clarified wording with faculty"))


class ApprovalRequest(BaseModel):
    approved_by: Optional[str] = Field("faculty", json_schema_extra=_example("faculty"))
    checklist: Optional[List[ApprovalChecklistItem]] = None
    approval_notes: Optional[str] = Field(None, json_schema_extra=_example("Mentor confirmed edge cases"))
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
