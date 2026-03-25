from pydantic import BaseModel, Field
from typing import Optional, Dict


# 🔹 Input Schema (Request from LMS / API)
class CodeRequest(BaseModel):
    student_id: str = Field(..., example="123")
    question: str = Field(..., example="Write a function to calculate factorial")
    model_answer: str = Field(..., example="def f(n): return 1 if n==0 else n*f(n-1)")
    student_answer: str = Field(..., example="def fact(n): return 1 if n==0 else n*fact(n-1)")
    language: str = Field(..., example="python")


# 🔹 Rubric Breakdown Schema
class RubricScore(BaseModel):
    correctness: int = Field(..., example=40)
    efficiency: int = Field(..., example=20)
    readability: int = Field(..., example=15)
    structure: int = Field(..., example=15)


# 🔹 Concept Evaluation Schema
class ConceptEvaluation(BaseModel):
    logic: str = Field(..., example="Strong")
    edge_cases: str = Field(..., example="Good")
    completeness: str = Field(..., example="High")
    efficiency: str = Field(..., example="Good")
    readability: str = Field(..., example="Good")


# 🔹 Final Response Schema
class EvaluationResponse(BaseModel):
    score: int = Field(..., example=85)
    rubric: RubricScore
    concepts: ConceptEvaluation
    feedback: str = Field(..., example="Correct solution but missing edge cases")
    suggestions: Optional[str] = Field(None, example="Handle boundary conditions like n=0")


# 🔹 API Wrapper Response (Optional but Professional)
class APIResponse(BaseModel):
    status: str = Field(..., example="success")
    execution_time: float = Field(..., example=0.45)
    data: EvaluationResponse