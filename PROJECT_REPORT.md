<<<COVER>>>
PROJECT REPORT
AI Intelligent Evaluation Model

Submitted By
Student Name: ____________________
Register Number: ____________________
Course / Department: ____________________

Submitted To
Guide / Faculty Name: ____________________
Institution Name: ____________________

Academic Year: 2025-2026
Date: ____________________
<<<END_COVER>>>

<<<PAGE_BREAK>>>

# PROJECT REPORT

## AI Intelligent Evaluation Model

## Abstract

The AI Intelligent Evaluation Model is a package-backed academic evaluation system built to assess student answers with stronger consistency, better reuse, and more reliable feedback than a traditional prompt-only AI grader. The project was developed to solve major problems found in automatic academic assessment, such as inconsistent scoring, weak handling of edge cases, poor support for new question types, and contradictory score-feedback combinations. To solve these issues, the system was redesigned around reusable question packages that store accepted solutions, hidden tests, incorrect-pattern rules, and package metadata for future evaluations. The project uses deterministic-first scoring, package validation, persistent storage, suspicious-output monitoring, and regression-based protection to improve reliability. A major part of the project involved identifying repeated failures in registration and evaluation, analyzing their causes, and converting those lessons into stronger package generation logic, feedback guardrails, and automated tests. The final system provides a strong foundation for academy-level deployment, especially for repeated coding-question evaluation where correctness, fairness, and traceable logic are critical.

<<<PAGE_BREAK>>>

## Acknowledgement

This project report has been prepared as part of the development and documentation of the AI Intelligent Evaluation Model. The work reflects continuous improvement through implementation, testing, debugging, and refinement of the evaluation pipeline. The project also benefited from repeated observation of real failure cases, structured repository documentation, and regression-based engineering practices that helped transform early issues into reusable solutions.

<<<PAGE_BREAK>>>

## Table of Contents

1. Introduction
2. Background and Need for the Project
3. Problem Statement
4. Objectives
5. Scope of the Project
6. Overview of the Model
7. Working Principle of the System
8. Technology Stack
9. System Architecture
10. Main Stored Package Fields
11. Methodology Followed
12. Problems Faced During the Project
13. How the Problems Were Identified
14. Solutions Implemented to Overcome the Problems
15. Measures Taken to Improve Accuracy
16. System Requirements
17. Sample Workflow and API Usage
18. Results and Achievements
19. Key Files and Their Role
20. Testing and Validation Strategy
21. Current Strengths of the Model
22. Current Limitations
23. Future Enhancements
24. Conclusion
25. References
26. Appendix A: Sample API Outputs
27. Appendix B: Actual Test Results and Benchmark Snapshot
28. Appendix C: Swagger Screenshot Placement Notes

<<<PAGE_BREAK>>>

## 1. Introduction

The AI Intelligent Evaluation Model is a FastAPI-based academic evaluation system designed to assess student answers for coding questions and selected web or static question types. The primary purpose of the project is to build a reliable, reusable, and explainable automated evaluation engine that can be used inside an educational application.

In many academic platforms, the same types of questions are asked repeatedly across students, assignments, labs, and assessments. In such environments, evaluation should not depend only on free-form AI judgment, because that can lead to inconsistent scoring, unstable feedback, and loss of trust. This project was therefore built around a different idea: instead of evaluating each answer from scratch, the system should first understand the question, store reusable evaluation rules for that question, and then use those stored rules whenever students submit answers later.

This project has gradually evolved from a more LLM-dependent evaluator into a deterministic-first, package-backed evaluation system. It now emphasizes structured question packages, hidden tests, accepted solutions, incorrect-pattern matching, guarded feedback generation, and regression-protected behavior.

## 2. Background and Need for the Project

Automatic evaluation is a difficult problem in education. A basic evaluator may compare the student answer with a sample answer or ask an AI model to judge correctness. However, this approach usually creates practical issues such as:

- inconsistent scores for similar answers
- vague or misleading feedback
- inability to handle edge cases
- poor support for new question types
- weak reusability across repeated questions

For an academy-level app, these weaknesses are serious. Students expect fairness, faculty expect accuracy, and the institution expects the system to scale over time. A one-time answer comparison system is not enough. What is needed is a reusable evaluation model that can preserve question-specific logic and apply it consistently in future evaluations.

That is the problem this project tries to solve.

## 3. Problem Statement

The project addresses the following core problem:

How can an academic platform evaluate student coding answers automatically with high accuracy, consistent scoring, reusable logic, and reliable feedback, even when new questions or new question types are introduced?

The project specifically aims to solve these difficulties:

- heavy dependence on unstable LLM-based evaluation
- weak question registration for unseen questions
- reuse of incorrect stored rules
- feedback that does not match the score
- poor handling of hidden tests and edge cases
- repeated failures when new topics appear

## 4. Objectives

The main objectives of the project are:

1. To build a reusable automated evaluation system for student answers.
2. To reduce dependence on free-form LLM score invention.
3. To register each question as a structured evaluation package.
4. To store evaluation rules persistently for future reuse.
5. To evaluate student answers using deterministic evidence wherever possible.
6. To improve feedback quality and remove contradictions.
7. To support new question registration with stronger automatic package generation.
8. To make the system suitable for academy deployment inside an educational app.
9. To protect the system using regression and benchmark tests.

## 5. Scope of the Project

The project includes the following functional scope:

- question registration through API
- creation of reusable question packages
- package storage in a persistent question profile store
- student evaluation through API
- deterministic scoring for supported languages
- hidden-test execution for runnable languages
- package editing, review, and approval workflows
- suspicious evaluation monitoring
- regression and benchmark testing

The current strongest area of the system is structured coding-question evaluation, especially for Python beginner and intermediate question families.

## 6. Overview of the Model

The core design of the model is based on the concept of a reusable question package.

Instead of asking the system to judge a student answer from scratch every time, the model first creates a package for each question. That package stores the reusable scoring rulebook for that question.

The package may contain:

- accepted correct solutions
- hidden tests
- grouped positive and negative test sets
- incorrect-pattern rules
- template family information
- confidence and approval metadata
- question-specific evaluation logic

Once this package is stored, later student answers can be evaluated against it in a consistent and repeatable manner.

This architecture makes the project more suitable for academic use because the question is understood once and then reused many times.

## 7. Working Principle of the System

The working flow of the project is:

1. A faculty or admin submits a question through `POST /questions/register`.
2. The system analyzes the question text and model answer.
3. It identifies a deterministic family or derives one from the model answer.
4. It generates accepted solutions, hidden tests, test sets, and incorrect patterns.
5. It validates the generated package using the faculty model answer.
6. It stores the package in the question profile store.
7. A student answer is later submitted through `POST /evaluate/students`.
8. The evaluator fetches the stored package.
9. The answer is scored using deterministic evidence such as hidden tests and pattern rules.
10. The final score and feedback are repaired if contradictions exist before returning the API response.

This means the evaluator is not only checking answers. It is also maintaining reusable knowledge about each question.

## 8. Technology Stack

The project uses the following technologies:

- Python
- FastAPI
- SQLite-backed storage
- Pytest
- local LLM integration through `llama_cpp`
- structured schema validation
- deterministic code execution modules

Important project files include:

- [app.py](</c:/DSA ICT/Internship/ai-intelligent-evaluation-model/app.py>)
- [config.py](</c:/DSA ICT/Internship/ai-intelligent-evaluation-model/config.py>)
- [schemas.py](</c:/DSA ICT/Internship/ai-intelligent-evaluation-model/schemas.py>)
- [README.md](</c:/DSA ICT/Internship/ai-intelligent-evaluation-model/README.md>)

## 9. System Architecture

The project can be viewed as several coordinated layers.

### 9.1 API Layer

This layer handles incoming requests for question registration, question retrieval, approval, and student evaluation.

Main endpoint handling is in:

- [app.py](</c:/DSA ICT/Internship/ai-intelligent-evaluation-model/app.py>)

### 9.2 Question Package Generation Layer

This layer is responsible for generating question packages. It decides the template family and creates:

- accepted solutions
- hidden tests
- test sets
- incorrect patterns
- package confidence
- package readiness state

Important files:

- [evaluator/question_rule_generator.py](</c:/DSA ICT/Internship/ai-intelligent-evaluation-model/evaluator/question_rule_generator.py>)
- [evaluator/question_package/workflow.py](</c:/DSA ICT/Internship/ai-intelligent-evaluation-model/evaluator/question_package/workflow.py>)
- [evaluator/question_package/generator.py](</c:/DSA ICT/Internship/ai-intelligent-evaluation-model/evaluator/question_package/generator.py>)
- [evaluator/question_package/validator.py](</c:/DSA ICT/Internship/ai-intelligent-evaluation-model/evaluator/question_package/validator.py>)

### 9.3 Question Profile Storage Layer

This is the persistent memory of the system. It stores reusable evaluation rulebooks for questions.

Important files:

- [evaluator/question_profile_repository.py](</c:/DSA ICT/Internship/ai-intelligent-evaluation-model/evaluator/question_profile_repository.py>)
- [evaluator/question_profile_store.py](</c:/DSA ICT/Internship/ai-intelligent-evaluation-model/evaluator/question_profile_store.py>)

### 9.4 Evaluation Orchestration Layer

This layer applies deterministic scoring using package-backed evidence such as hidden tests, accepted solutions, and incorrect-pattern matches.

Important files:

- [evaluator/main_evaluator.py](</c:/DSA ICT/Internship/ai-intelligent-evaluation-model/evaluator/main_evaluator.py>)
- [evaluator/orchestration/pipeline.py](</c:/DSA ICT/Internship/ai-intelligent-evaluation-model/evaluator/orchestration/pipeline.py>)

### 9.5 Execution Layer

This layer executes hidden tests and family-specific logic for supported languages.

Important files:

- [evaluator/execution/shared.py](</c:/DSA ICT/Internship/ai-intelligent-evaluation-model/evaluator/execution/shared.py>)
- [evaluator/execution/python_families/numbers.py](</c:/DSA ICT/Internship/ai-intelligent-evaluation-model/evaluator/execution/python_families/numbers.py>)
- [evaluator/execution/python_families/strings.py](</c:/DSA ICT/Internship/ai-intelligent-evaluation-model/evaluator/execution/python_families/strings.py>)
- [evaluator/execution/python_families/lists.py](</c:/DSA ICT/Internship/ai-intelligent-evaluation-model/evaluator/execution/python_families/lists.py>)

<<<PAGE_BREAK>>>

## 10. Main Stored Package Fields

One of the most important achievements of the project is the creation of a reusable question profile store. The following package fields are central to the evaluator:

- `accepted_solutions`
- `hidden_tests`
- `test_sets`
- `incorrect_patterns`
- `template_family`
- `package_status`
- `package_confidence`
- `approval_status`
- `review_required`
- question-specific evaluation rules

These fields are stored so they can be reused later during evaluation. Because of this, the system behaves more like a structured academic engine than a simple prompt-driven evaluator.

## 11. Methodology Followed

The development of the project followed an iterative engineering methodology:

1. Build an evaluation feature.
2. Run it on realistic questions and student-style submissions.
3. Observe where it fails.
4. Diagnose whether the failure comes from:
   question registration,
   package generation,
   hidden tests,
   scoring logic,
   feedback logic, or
   package reuse.
5. Fix the root cause in code or in the package logic.
6. Add automated tests so the same issue does not reappear.

This method helped the project improve steadily. Most major improvements came from solving real observed failures, not only from theoretical planning.

## 12. Problems Faced During the Project

This section explains the real difficulties faced during development.

### 12.1 Overreliance on LLM-Based Grading

In the earlier stages, the evaluator relied too much on free-form LLM comparison. This caused multiple issues:

- different scores for similar answers
- weak or generic feedback
- invented or unsupported reasoning
- mismatch between score and explanation

This was a serious problem because academic systems require repeatability.

### 12.2 Weak Registration Packages

Many registration attempts produced packages that were incomplete or too weak. Common issues included:

- generic template families
- low confidence scores
- very few hidden tests
- poor incorrect-pattern coverage
- missing required edge cases

This often caused `POST /questions/register` failures such as `422 Unprocessable Entity`.

### 12.3 Register-Evaluate Drift

The same question could be normalized differently during registration and evaluation. As a result:

- correct stored packages were not always found
- evaluation sometimes missed reusable package logic
- registration and evaluation behaved differently for the same question

### 12.4 Reuse of the Wrong Stored Package

Sometimes a previously stored package was reused because the wording looked similar, even though the logic was different.

Examples:

- `multiple of 3` versus `multiple of 6`
- `greater than 10` versus `greater than 5`
- `second element` versus `third element`
- `first two characters` versus `first three characters`

This was a major risk because it could lead to incorrect student scoring.

### 12.5 Correct Score but Incorrect Feedback

One of the most serious issues was that the score could be correct while the feedback was wrong. For example:

- full marks with corrective feedback
- zero score with positive feedback
- vague feedback despite exact hidden-test evidence
- generic feedback despite a known wrong pattern being matched

This reduced trust in the system.

### 12.6 Overbroad Incorrect-Pattern Rules

Some incorrect-pattern rules were too broad. Patterns like `return s` or `return len(lst)` could match many forms of code, including ones that were not actually the same mistake.

This caused:

- unfair penalties
- poor-quality explanations
- incorrect pattern-based scoring

### 12.7 New Question and New Topic Instability

When new topics or new question forms appeared, package generation could fail or become too generic. This directly affected the requirement that the model should continue working when new questions are added.

### 12.8 Weak Hidden-Test Quality

Generated hidden tests sometimes had issues such as:

- duplicate entries
- poor edge-case coverage
- weak positive and negative balancing
- incorrect grouping for boolean outputs

Weak tests directly reduce evaluation reliability.

### 12.9 Test Contamination from Local Data

Because the project stores packages and evaluation history persistently, existing local stored data sometimes affected automated tests. This made the test suite less deterministic until isolation measures were introduced.

## 13. How the Problems Were Identified

The project team identified problems through:

- local API testing
- Swagger requests
- examination of registration output
- repeated evaluation trials
- regression failures
- benchmark failures
- suspicious output monitoring
- direct inspection of stored packages

The automated tests were especially important for identifying and reproducing problems. The most useful test files included:

- [tests/test_monitoring_and_registration.py](</c:/DSA ICT/Internship/ai-intelligent-evaluation-model/tests/test_monitoring_and_registration.py>)
- [tests/test_deterministic_guardrails.py](</c:/DSA ICT/Internship/ai-intelligent-evaluation-model/tests/test_deterministic_guardrails.py>)
- [tests/test_regressions.py](</c:/DSA ICT/Internship/ai-intelligent-evaluation-model/tests/test_regressions.py>)
- [tests/test_benchmark.py](</c:/DSA ICT/Internship/ai-intelligent-evaluation-model/tests/test_benchmark.py>)
- [tests/test_evaluator.py](</c:/DSA ICT/Internship/ai-intelligent-evaluation-model/tests/test_evaluator.py>)

These tests helped discover not only surface bugs, but also deeper structural issues in package generation, scoring, and feedback behavior.

## 14. Solutions Implemented to Overcome the Problems

### 14.1 Shift to Deterministic-First Scoring

The most important change in the project was moving away from LLM-first grading and toward deterministic-first scoring.

The system now gives priority to:

- hidden-test execution
- accepted-solution equivalence
- incorrect-pattern matches
- family-specific deterministic overrides

This reduced evaluation instability significantly.

### 14.2 Creation of Reusable Question Packages

Instead of rediscovering question logic every time, the system now creates reusable packages. These packages act as permanent scoring rulebooks.

This solved several problems:

- improved consistency
- reduced rework
- enabled reuse across many student submissions
- preserved question-specific evaluation logic

### 14.3 Persistent Question Profile Storage

The system stores packages in a persistent profile store. This means accepted solutions, hidden tests, incorrect patterns, and readiness metadata are available for later evaluations.

This turned the evaluator into a reusable system rather than a stateless comparison engine.

### 14.4 Shared Signature Normalization

The project introduced centralized question signature normalization. Registration and evaluation now use the same normalized signature builder, reducing drift between the two workflows.

### 14.5 Strict Registration Quality Gates

The project added stronger quality requirements during registration. Packages are checked for:

- sufficient confidence
- template specificity
- test coverage
- incorrect-pattern quality
- faculty-answer validation

This prevented weak or generic packages from silently becoming trusted live packages.

### 14.6 Family-Aware and Parameter-Aware Reuse

Stored packages are now reused only when both family logic and important parameters match. This prevents wrong-package reuse across similar-looking questions.

### 14.7 Expansion of Deterministic Question Families

To support more new questions without failure, deterministic family coverage was expanded. Important supported Python families now include:

- zero check
- divisibility by constant
- greater-than threshold
- odd checks
- empty and non-empty collection checks
- list length rules
- list length comparison rules
- element-at-index rules
- first, prefix, and suffix string rules
- lowercase and uppercase string conversion
- middle character extraction
- list membership checks

This dramatically improved new-question handling for many academy-style exercises.

### 14.8 Automatic Package Bootstrap During Evaluation

If evaluation receives full inline question context and a valid stored package is missing, the system can attempt to build a usable package automatically. This reduces evaluation-time failures.

### 14.9 Final Response Guardrails

The project added final-response repair logic so that contradictory outputs are corrected before they are returned.

Examples of what this protects against:

- score `100` with corrective feedback
- overscored incorrect-pattern matches
- vague feedback when exact deterministic evidence exists
- package-backed hidden-test failure being ignored by final feedback

### 14.10 Hidden-Test Cleanup and Sanitization

The project introduced controls such as:

- duplicate hidden-test removal
- positive and negative rebucketing corrections
- edge-case reinforcement
- template-specific pattern sanitization

### 14.11 Test Isolation and Regression Protection

The project added isolated test-store configuration and stronger regression tests so that local stored package data would not interfere with automated test outcomes.

<<<PAGE_BREAK>>>

## 15. Measures Taken to Improve Accuracy

Because the target use case is academic evaluation, accuracy improvement has been a central goal. The following measures were taken:

1. Validation of question packages against faculty model answers.
2. Hidden-test-driven scoring for supported runnable languages.
3. Incorrect-pattern matching with feedback and score caps.
4. Family-specific deterministic feedback protection.
5. Restriction of generic fallback package reuse.
6. Parameter-aware package matching.
7. Automatic repair of weak final feedback.
8. Suspicious evaluation monitoring for audit.
9. Benchmark and regression-driven development.

## 16. System Requirements

The current project is designed to run in a local development environment with the following practical requirements:

- Python `3.12`
- Windows PowerShell or a compatible command-line environment
- FastAPI-compatible Python environment
- writable project storage directory
- SQLite-compatible runtime for persistent package storage
- local model path when GGUF-assisted flows are used

Important package dependencies currently listed in the project include:

- `fastapi`
- `uvicorn`
- `pytest`
- `llama-cpp-python`
- `pyyaml`

Typical runtime folders used by the project include:

- `data/`
- `models/`
- `tests/`
- `evaluator/`

The system can still perform many deterministic tasks even when the LLM is unavailable, because the protected path is designed to depend primarily on package-backed rules rather than free-form model scoring.

## 17. Sample Workflow and API Usage

The following simplified workflow shows how the project behaves in practice.

### 17.1 Registration Workflow

```text
Question Input
    ->
Question Analysis
    ->
Template Family Detection
    ->
Accepted Solutions + Hidden Tests + Incorrect Patterns
    ->
Package Validation
    ->
Question Profile Store
```

### 17.2 Evaluation Workflow

```text
Student Submission
    ->
Question Signature Lookup
    ->
Stored Question Package Retrieved
    ->
Hidden Tests / Pattern Rules / Accepted Solutions Applied
    ->
Deterministic Score Computed
    ->
Final Feedback Guardrails Applied
    ->
Result Returned
```

### 17.3 Example Registration Request

```json
{
  "questions": [
    {
      "question_id": "q1",
      "question": "Check if number is zero",
      "model_answer": "def is_zero(n): return n == 0",
      "language": "python"
    }
  ]
}
```

### 17.4 Example Registration Outcome

The expected useful registration output includes fields such as:

- `template_family`
- `accepted_solutions`
- `hidden_tests`
- `test_sets`
- `incorrect_patterns`
- `package_status`
- `package_confidence`

### 17.5 Example Student Evaluation Request

```json
{
  "students": [
    {
      "student_id": "S001",
      "submissions": [
        {
          "question_id": "q1",
          "question": "Check if number is zero",
          "model_answer": "def is_zero(n): return n == 0",
          "student_answer": "def is_zero(n): return not n",
          "language": "python"
        }
      ]
    }
  ]
}
```

### 17.6 Example Evaluation Result

A successful evaluation typically returns:

- question-level score
- concept-wise evaluation
- logic summary
- detailed feedback
- total student score

This structured output is important because the project is designed not only to score answers, but also to explain the result in a reusable academic format.

## 18. Results and Achievements

The project produced several important outcomes.

### 18.1 Architectural Achievements

- The evaluator moved from a more LLM-centered design to a deterministic-first design.
- Reusable question packages became the core unit of evaluation.
- The question profile store became a persistent rulebook repository for future use.

### 18.2 Functional Achievements

- New questions can often be registered automatically through family inference and model-answer-derived logic.
- Student evaluation now reuses stored package fields instead of re-guessing question logic.
- Hidden tests and incorrect patterns now influence scoring directly in the protected path.

### 18.3 Quality Achievements

- Contradictory score and feedback combinations were reduced through final guardrails.
- Reuse of stale or mismatched question packages was reduced through parameter-aware matching.
- More deterministic Python question families were supported than in earlier versions.

### 18.4 Engineering Achievements

- The project now includes regression protection for known bugs.
- Focused tests protect package generation, deterministic scoring, and monitoring behavior.
- Test isolation was improved so local stored data does not easily corrupt automated results.

### 18.5 Academic Value

From an academic perspective, the most important achievement is that the system now evaluates repeated questions more fairly and consistently by using stored structured logic rather than unstable one-time AI judgment.

<<<PAGE_BREAK>>>

## 19. Key Files and Their Role

- [app.py](</c:/DSA ICT/Internship/ai-intelligent-evaluation-model/app.py>)
  Main API layer, package bootstrap logic, evaluation orchestration, and final response repair.

- [evaluator/question_rule_generator.py](</c:/DSA ICT/Internship/ai-intelligent-evaluation-model/evaluator/question_rule_generator.py>)
  Core question package generation logic, family inference, hidden-test generation, and pattern sanitization.

- [evaluator/question_package/workflow.py](</c:/DSA ICT/Internship/ai-intelligent-evaluation-model/evaluator/question_package/workflow.py>)
  Registration workflow for preparing and validating packages.

- [evaluator/question_profile_repository.py](</c:/DSA ICT/Internship/ai-intelligent-evaluation-model/evaluator/question_profile_repository.py>)
  Persistent storage logic for question packages.

- [evaluator/orchestration/pipeline.py](</c:/DSA ICT/Internship/ai-intelligent-evaluation-model/evaluator/orchestration/pipeline.py>)
  Deterministic scoring pipeline, package-backed logic, and accuracy overrides.

- [evaluator/execution/shared.py](</c:/DSA ICT/Internship/ai-intelligent-evaluation-model/evaluator/execution/shared.py>)
  Shared execution helpers and universal evaluation support.

- [tests/test_monitoring_and_registration.py](</c:/DSA ICT/Internship/ai-intelligent-evaluation-model/tests/test_monitoring_and_registration.py>)
  Protects question registration quality and monitoring behavior.

- [tests/test_deterministic_guardrails.py](</c:/DSA ICT/Internship/ai-intelligent-evaluation-model/tests/test_deterministic_guardrails.py>)
  Protects deterministic package-backed behavior and guardrail logic.

- [tests/test_regressions.py](</c:/DSA ICT/Internship/ai-intelligent-evaluation-model/tests/test_regressions.py>)
  Protects previously fixed bugs from returning.

## 20. Testing and Validation Strategy

The project uses multiple layers of testing:

- unit tests
- deterministic guardrail tests
- registration quality tests
- regression tests
- benchmark tests
- suspicious output monitoring

This layered approach is important because different errors appear at different stages. One issue may affect registration while another affects scoring or feedback. Therefore a single test type would not be enough.

## 21. Current Strengths of the Model

The current system has the following strengths:

- package-backed reusable evaluation
- deterministic-first scoring
- improved support for repeated academy-style questions
- persistent question logic storage
- better feedback reliability
- stronger hidden-test-based evaluation
- safer handling of new but structurally familiar question types
- better development safety through tests and monitoring

## 22. Current Limitations

Even though the project has improved substantially, some limitations remain.

### 19.1 Absolute perfect accuracy for every unseen future question is not realistic

For covered families, the system can be made highly reliable and deterministic. However, for completely new, ambiguous, or advanced question structures, perfect fully automatic evaluation is still difficult.

### 19.2 New family support is an ongoing requirement

Whenever new question structures appear, the system may still need:

- new deterministic families
- stronger hidden-test generation
- improved incorrect-pattern rules
- new regression cases

### 19.3 Some cases may still require review

For truly novel questions, stronger manual review or admin approval logic may still be appropriate until the new family is properly supported.

## 23. Future Enhancements

The following improvements are recommended for future work:

1. Expand deterministic family support across more languages and question types.
2. Add stronger registration coverage requirements for all families.
3. Create better review tools for weak or draft packages.
4. Build dashboards for suspicious evaluations and package health.
5. Keep converting real failures into regression tests.
6. Add more benchmark coverage for newly introduced topics.
7. Improve automatic package generation for more advanced question structures.

<<<PAGE_BREAK>>>

## 24. Conclusion

The AI Intelligent Evaluation Model has developed into a much stronger and more reliable academic evaluation system than a simple prompt-driven grader.

During the project, many serious issues were faced, including:

- dependence on unstable LLM grading
- weak package generation
- registration failures
- wrong package reuse
- feedback contradictions
- hidden-test weaknesses
- instability for new question types

These problems were overcome through architectural redesign, deterministic scoring, persistent question package storage, stronger registration rules, final response guardrails, and a disciplined regression-testing strategy.

As a result, the project now has a strong foundation for academy-level deployment. Its most important achievement is that it treats each question as a reusable evaluation asset, not just as a one-time prompt. That makes the system more accurate, more explainable, and more suitable for long-term educational use.

## 25. References

The report is based on the current project implementation and documentation available in the repository, especially:

- [README.md](</c:/DSA ICT/Internship/ai-intelligent-evaluation-model/README.md>)
- [app.py](</c:/DSA ICT/Internship/ai-intelligent-evaluation-model/app.py>)
- [config.py](</c:/DSA ICT/Internship/ai-intelligent-evaluation-model/config.py>)
- [schemas.py](</c:/DSA ICT/Internship/ai-intelligent-evaluation-model/schemas.py>)
- [evaluator/question_rule_generator.py](</c:/DSA ICT/Internship/ai-intelligent-evaluation-model/evaluator/question_rule_generator.py>)
- [evaluator/question_package/workflow.py](</c:/DSA ICT/Internship/ai-intelligent-evaluation-model/evaluator/question_package/workflow.py>)
- [evaluator/question_profile_repository.py](</c:/DSA ICT/Internship/ai-intelligent-evaluation-model/evaluator/question_profile_repository.py>)
- [evaluator/orchestration/pipeline.py](</c:/DSA ICT/Internship/ai-intelligent-evaluation-model/evaluator/orchestration/pipeline.py>)
- [tests/test_monitoring_and_registration.py](</c:/DSA ICT/Internship/ai-intelligent-evaluation-model/tests/test_monitoring_and_registration.py>)
- [tests/test_deterministic_guardrails.py](</c:/DSA ICT/Internship/ai-intelligent-evaluation-model/tests/test_deterministic_guardrails.py>)
- [tests/test_regressions.py](</c:/DSA ICT/Internship/ai-intelligent-evaluation-model/tests/test_regressions.py>)

<<<PAGE_BREAK>>>

## 26. Appendix A: Sample API Outputs

This appendix includes representative examples of the kinds of payloads and outputs used in the system.

### A.1 Sample Question Registration Request

```json
{
  "questions": [
    {
      "question_id": "q1",
      "question": "Check if number is zero",
      "model_answer": "def is_zero(n): return n == 0",
      "language": "python"
    }
  ]
}
```

### A.2 Sample Question Registration Response Structure

```json
[
  {
    "question_id": "q1",
    "question": "Check if number is zero",
    "model_answer": "def is_zero(n): return n == 0",
    "language": "python",
    "template_family": "python::zero_check",
    "accepted_solutions": [
      "def is_zero(n): return n == 0"
    ],
    "hidden_tests": [
      {
        "input": "[0]",
        "expected_output": "true"
      }
    ],
    "test_sets": {
      "positive": [
        {
          "input": "[0]",
          "expected_output": "true"
        }
      ],
      "negative": [
        {
          "input": "[1]",
          "expected_output": "false"
        }
      ]
    },
    "incorrect_patterns": [
      {
        "pattern": "return n != 0",
        "feedback": "This checks the opposite condition."
      }
    ],
    "package_status": "validated",
    "package_confidence": 1.0
  }
]
```

### A.3 Sample Student Evaluation Request

```json
{
  "students": [
    {
      "student_id": "S001",
      "submissions": [
        {
          "question_id": "q1",
          "question": "Check if number is zero",
          "model_answer": "def is_zero(n): return n == 0",
          "student_answer": "def is_zero(n): return not n",
          "language": "python"
        }
      ]
    }
  ]
}
```

### A.4 Sample Student Evaluation Response Structure

```json
{
  "execution_time": 0.47,
  "students": [
    {
      "student_id": "S001",
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
            "logic_evaluation": "The student used a different approach, but the logic is correct.",
            "feedback": "The function correctly checks whether the number is zero."
          }
        }
      ]
    }
  ]
}
```

### A.5 Sample Failure Scenario from Registration

One of the practical failure cases observed during the project was a registration-time `422` response when the package generator produced a weak or incomplete package. A simplified structure of that kind of error is shown below.

```json
{
  "detail": {
    "error": "Question package generation failed to produce fully correct packages.",
    "items": [
      {
        "question_id": "q2",
        "package_status": "draft",
        "package_confidence": 0.1,
        "review_required": true,
        "flags": [
          "review_required",
          "low_confidence",
          "package_not_ready"
        ]
      }
    ]
  }
}
```

<<<PAGE_BREAK>>>

## 27. Appendix B: Actual Test Results and Benchmark Snapshot

This appendix records a current snapshot of selected automated verification results collected during report preparation on April 17, 2026.

### B.1 Focused Registration and Monitoring Test Snapshot

Command executed:

```powershell
python -m pytest tests/test_monitoring_and_registration.py -q
```

Observed result:

- `41 passed`
- `1 failed`

Current failing case:

- `test_register_sanitizes_lowercase_and_second_element_incorrect_pattern_feedback`

Observed issue from the failure output:

- the lowercase question package still produced only a reduced incorrect-pattern set
- the expected specific sanitized feedback for `def lower(s): return s.lower` was missing

### B.2 Deterministic Guardrail Test Snapshot

Command executed:

```powershell
python -m pytest tests/test_deterministic_guardrails.py -q
```

Observed result:

- `43 passed`
- `1 failed`

Current failing case:

- `test_registered_packages_are_specific_and_ready`

Observed issue from the failure output:

- at least one registered package currently has only one positive test instead of the expected minimum of two
- this indicates that package coverage for a core family still needs strengthening

### B.3 Benchmark Snapshot

Command executed:

```powershell
python -m pytest tests/test_benchmark.py::test_accuracy_benchmark_cases -q
```

Observed result:

- `1 passed`

This indicates that the benchmark case suite targeted by that test currently passes under the present code state.

### B.4 Benchmark Threshold Configuration Snapshot

Current threshold configuration from the project benchmark settings includes:

- overall minimum accuracy: `85.0`
- Python minimum accuracy: `85.0`
- Java minimum accuracy: `85.0`
- JavaScript minimum accuracy: `50.0`
- HTML minimum accuracy: `50.0`
- CSS minimum accuracy: `50.0`
- React minimum accuracy: `50.0`
- MySQL minimum accuracy: `50.0`
- MongoDB minimum accuracy: `50.0`

### B.5 Interpretation of the Snapshot

The current snapshot shows an important engineering reality of the project:

- the evaluator has become much stronger and many protected paths are working
- benchmark protection is active and passing for the targeted benchmark test
- however, some registration-quality and package-sanitization issues still remain in focused tests

This is actually consistent with the project’s development model. The system is being strengthened through repeated failure discovery and correction, and the focused failing tests help identify exactly what still needs improvement.

<<<PAGE_BREAK>>>

## 28. Appendix C: Swagger Screenshot Placement Notes

This terminal environment does not provide direct browser screenshot capture for the locally running Swagger UI. For that reason, this appendix provides the exact screenshot slots that should be inserted into the final submitted Word or PDF version after opening the API in a browser.

Swagger UI location:

- `http://127.0.0.1:8000/docs`

Recommended screenshots to insert:

### C.1 Swagger Home Page

Suggested caption:

`Figure C.1: Swagger UI home page showing the available question registration and student evaluation APIs.`

### C.2 Question Registration API

Suggested screenshot content:

- `POST /questions/register`
- sample request body
- sample successful response body

Suggested caption:

`Figure C.2: Swagger request and response example for question registration.`

### C.3 Student Evaluation API

Suggested screenshot content:

- `POST /evaluate/students`
- multi-student or single-student request body
- evaluation response body with total score and question-level feedback

Suggested caption:

`Figure C.3: Swagger request and response example for student evaluation.`

### C.4 Monitoring or Review API

Suggested screenshot content:

- pending review packages
- suspicious evaluation monitoring endpoint

Suggested caption:

`Figure C.4: Swagger example for review or monitoring endpoints used for evaluation quality control.`

### C.5 Placement Recommendation

For final academic submission, these screenshots should ideally be inserted:

- either in this appendix section
- or in a separate `List of Figures` and `Appendix` section of the report

This will make the report stronger because it will visually demonstrate that the APIs were actually tested and that the project is not only theoretical but operational.
