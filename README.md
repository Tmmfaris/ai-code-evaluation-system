# AI Intelligent Evaluation Model

FastAPI service for deterministic-first evaluation of student answers across coding and selected static/web question types. The system is built for repeatable academic scoring with reusable question packages, hidden tests, incorrect-pattern matching, guarded feedback generation, suspicious-output monitoring, and regression protection.

The project is no longer centered on free-form LLM grading. The current system is:
- package-backed
- deterministic-first
- hidden-test-driven where supported
- guarded against contradictory output
- monitored for suspicious results
- protected by CI and regression suites

## Contents

- Overview
- Current Design Principles
- What Changed Recently
- Current Deterministic Families
- Main Endpoints
- Quick Start
- Current Important Defaults
- Question Package Lifecycle
- Registration Deep Dive
- Evaluation Deep Dive
- Deterministic Guardrails
- New Question Handling
- Storage and Stores
- Monitoring and Suspicious Evaluations
- Testing and CI
- Troubleshooting
- Where to Change What
- Limitations

## Overview

This project evaluates student answers using reusable question packages instead of relying on ad hoc comparison for every request.

At a high level:
1. a question is registered into a reusable package
2. the package stores accepted solutions, tests, patterns, and readiness metadata
3. later evaluations reuse that package for deterministic scoring
4. final response guardrails repair weak or contradictory feedback before it is returned
5. suspicious results are stored for later inspection

This is especially useful for:
- repeated assessments
- academy-style exercises
- benchmarkable question families
- local/offline evaluation workflows

## Current Design Principles

The current architecture is guided by these rules:
- deterministic evidence decides score whenever possible
- validated question packages are the source of truth for live scoring
- hidden tests, accepted solutions, and incorrect patterns matter more than LLM guesses
- LLM score invention is disabled in the protected package-backed path
- LLM is mainly used for package generation and safe wording improvements
- generic template fallbacks are rejected during registration
- final API output is guarded so correct score plus wrong feedback contradictions do not leak out

## What Changed Recently

The project was hardened significantly. The most important recent changes now reflected in the code are below.

### Deterministic-first scoring

- package-backed deterministic scoring is enforced
- package-backed evaluations do not use LLM scoring as the source of truth
- hidden tests are used directly in the evaluation pipeline for runnable languages
- incorrect-pattern matches can cap or force low scores
- final family-specific overrides can replace vague execution summaries with exact deterministic feedback

### Shared signature normalization

- question signature normalization is centralized
- registration and evaluation both use the same shared signature builder
- this prevents register/evaluate drift from punctuation or wording normalization mismatches

### Strict registration quality gates

- weak generic package output is rejected
- low-confidence reviewed packages do not silently pass as ready
- registration checks required case coverage
- placeholder or fallback-style feedback in incorrect patterns is rejected
- stale stored packages from the wrong specific family are not reused
- low-confidence or review-required stored packages are not reused as trusted live profiles

### Final response guardrails

- `100` score cannot return corrective feedback
- incorrect patterns cannot remain overscored
- required hidden-test failures force low scores
- specific deterministic feedback beats generic fallback feedback
- weak package-backed feedback is repaired before the response is returned
- broad incorrect-pattern rules are constrained so simple patterns like `return s` or `return len(lst)` do not overmatch related but different code
- boolean tests are rebucketed so `expected_output: false` never stays inside `test_sets.positive`
- duplicate hidden tests are removed before storage and before API response export

### Template-specific final feedback protection

The final deterministic response layer now explicitly protects several Python families, including:
- `python::zero_check`
- `python::list_length`
- `python::string_endswith`
- `python::uppercase_string`
- `python::lowercase_string`
- `python::odd_check`
- `python::empty_collection_check`
- `python::greater_than_threshold`
- `python::second_element`

### New-question resilience

New question handling is much stronger than before:
- question-text family inference
- model-answer-based family inference
- deterministic model-answer-derived package baselines
- non-generic fallback family `python::model_answer_derived`
- automatic package bootstrap during evaluation when inline context is present
- family-compatible reuse only when specific parameters also match, such as the same threshold, divisor, prefix length, or target index

### Monitoring and audit

- suspicious evaluations are stored for review
- package and evaluation history are persisted
- low-quality patterns can be observed and later converted into better deterministic rules

### CI and regression protection

- focused CI suite for evaluation guardrails
- regression tests for bug fixes
- monitoring tests
- deterministic guardrail tests
- universal Python tests

## Current Deterministic Families

The system now supports a broader deterministic registry for common beginner and intermediate question shapes.

Important Python families currently covered in registration and evaluation include:
- `python::zero_check`
- `python::greater_than_threshold`
- `python::divisible_by_constant`
- `python::odd_check`
- `python::empty_collection_check`
- `python::non_empty_collection_check`
- `python::list_length`
- `python::list_length_equals_constant`
- `python::second_element`
- `python::element_at_index_constant`
- `python::first_two_characters`
- `python::prefix_characters_constant`
- `python::uppercase_string`
- `python::lowercase_string`
- `python::string_endswith`
- fallback `python::model_answer_derived`

These families now cover several parameterized question classes that were previously a major source of `422` registration failures or vague evaluation feedback:
- divisible by `N`
- greater than `N`
- list length equals `N`
- first `N` characters
- element at index `N`
- empty / non-empty collection checks

## LLM Role

The project still supports GGUF/LLM assistance, but the current role of the LLM is intentionally limited.

In practice:
- deterministic template detection and model-answer analysis are the primary path
- GGUF is used as a helper for enrichment, repair, or wording improvement
- bad GGUF output cannot silently become a validated package
- validated package-backed scoring does not depend on LLM score invention

This design reduces:
- inconsistent scoring
- slow or hanging evaluation due to overreliance on model calls
- contradictory score/feedback combinations
- repeated failures on new but structurally simple question shapes

## Main Endpoints

### `GET /`
Simple availability check.

### `GET /health`
Health and runtime check.

Useful for:
- confirming the app is up
- checking the runtime marker
- checking the evaluator fingerprint

### `POST /questions/register`
Registers one or more reusable question packages.

Use this before live evaluation whenever possible.

### `GET /questions/get`
Fetch a stored package by question text and language.

### `PATCH /questions/edit`
Edit a stored package.

### `GET /questions/review/pending`
List packages still pending review.

### `POST /questions/approve`
Approve a single package, optionally with edits.

### `POST /questions/approve-all`
Approve all pending packages.

### `POST /evaluate/students`
Evaluate one or more students and one or more submissions per student.

### `GET /monitor/suspicious-evaluations`
List evaluation history records marked suspicious.

Swagger UI:
- `http://127.0.0.1:8000/docs`

## Quick Start

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m uvicorn app:app --reload
```

Open:
- `http://127.0.0.1:8000/docs`

## Environment

Recommended local environment:
- Python `3.12`
- Windows PowerShell
- writable `data/` directory
- local `models/` directory

Expected local GGUF model path:
- `models/Phi-3-mini-4k-instruct-q4.gguf`

LLM provider defaults are defined in [config.py](./config.py).

## Current Important Defaults

Current behavior is centered on package-backed deterministic evaluation.

Important settings from [config.py](./config.py):
- `LLM_PROVIDER = "llama_cpp"`
- `GGUF_MODEL_PATH = "models/Phi-3-mini-4k-instruct-q4.gguf"`
- `N_CTX = 512`
- `AUTO_GENERATE_QUESTION_RULES = True`
- `AUTO_ACTIVATE_VALIDATED_QUESTIONS = True`
- `REQUIRE_VALIDATED_QUESTION_PACKAGE = True`
- `STRICT_EVALUATION_BY_QUESTION_ID = True`
- `REQUIRE_FACULTY_APPROVAL_FOR_LIVE = False`
- `FORCE_LLM_WHEN_NOT_DETERMINISTIC = False`
- `ALWAYS_LLM_REVIEW = False`
- `LLM_ALLOW_SCORE_AUDIT = False`
- `DETERMINISTIC_PACKAGE_SCORING_ONLY = True`
- `REQUIRE_PACKAGE_COVERAGE_FOR_REGISTRATION = True`
- `REGISTER_STRICT_VALIDATE = True`
- `REGISTER_STRICT_MIN_CONFIDENCE = 0.9`
- `REGISTER_REJECT_GENERIC_TEMPLATES = True`
- `AUTO_REPAIR_BAD_PACKAGES = True`
- `LLM_REPHRASE_FEEDBACK = True`
- `LLM_GENERATE_FEEDBACK_ALWAYS = True`
- `MONITOR_SUSPICIOUS_EVALUATIONS = True`

Meaning in practice:
- evaluation expects a validated package
- generic registration output is blocked
- package-backed deterministic scoring is the truth source
- LLM score invention is disabled in the protected path
- weak final feedback can be repaired before response return
- suspicious output is logged and queryable

## Supported Languages

Supported request languages:
- `python`
- `java`
- `javascript`
- `html`
- `css`
- `react`
- `mongodb`
- `mysql`

Hidden-test execution support:
- enabled: `python`, `java`, `javascript`
- disabled: `html`, `css`, `react`, `mysql`, `mongodb`

Non-runnable languages still use deterministic/static checks where available.

## Request Models

API schemas are defined in [schemas.py](./schemas.py).

Main request models:
- `QuestionPackageRequest`
- `MultiQuestionPackageRequest`
- `QuestionSubmission`
- `StudentEvaluationRequest`
- `MultiStudentEvaluationRequest`

### `POST /questions/register` request example

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

### `POST /evaluate/students` request example

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

## Question Package Lifecycle

Question packages are the reusable memory layer of the evaluator.

Typical lifecycle:
1. register a question with `POST /questions/register`
2. infer or derive a template family
3. build accepted solutions, hidden tests, and incorrect patterns
4. validate the package against the model answer
5. store the package in the profile store
6. reuse it during `/evaluate/students`
7. collect evaluation history and learning signals

Key package fields:
- `question_signature`
- `template_family`
- `accepted_solutions`
- `hidden_tests`
- `test_sets`
- `incorrect_patterns`
- `package_status`
- `package_confidence`
- `review_required`
- `approval_status`
- `exam_ready`

## Registration Deep Dive

`POST /questions/register` is the preferred entry point for stable evaluation.

Registration currently does all of the following:
- builds a normalized question signature
- tries question-text family inference
- tries model-answer family inference when wording is unfamiliar
- uses a non-generic fallback family for new simple Python question shapes
- builds deterministic baseline package content
- optionally merges oracle-generated test coverage
- validates the package against the provided model answer
- stores the result for later reuse

### Current family inference strategy

Current family selection order is:
1. specific question-text family inference
2. model-answer-based family inference
3. fallback `python::model_answer_derived` for simple Python callable answers
4. only then broad generic families if the question is still not classifiable

This means many new questions can now register successfully even if the wording is unfamiliar, as long as the model answer shape is recognizable.

### Parameter-aware family reuse

Stored packages are no longer reused only because they are "close enough" in wording.

Reuse is now guarded by both:
- family compatibility
- parameter compatibility

Examples:
- `greater than 10` does not reuse `greater than 5`
- `divisible by 10` does not reuse `divisible by 4`
- `list length equals 5` does not reuse `list length equals 3`
- `first two characters` does not reuse `first three characters`
- `third element` does not reuse `second element`

This blocks stale or mismatched packages from poisoning new registrations.

### Fields reused later during evaluation

These fields from registration are directly reused:
- `question_signature`
- `template_family`
- `accepted_solutions`
- `hidden_tests`
- `test_sets`
- `incorrect_patterns`
- `package_status`
- `package_confidence`
- `review_required`
- `approval_status`
- `exam_ready`

These are the most scoring-critical fields:
- `accepted_solutions`
- `hidden_tests`
- `test_sets`
- `incorrect_patterns`
- `template_family`
- `package_status`
- `review_required`
- `question`
- `language`

These are mostly informational/debug metadata:
- `profile`
- `package_summary`
- `reused_from_questions`
- `positive_test_count`
- `negative_test_count`
- `validation_options`

### Registration quality gates

Registration is considered ready only if the package is:
- not a weak generic fallback
- `validated` or `live`
- above the confidence threshold
- not marked `review_required`
- not carrying placeholder tests
- not carrying fallback-style incorrect-pattern feedback
- covered enough for live use

### Registration response behavior

The register response now includes:
- `hidden_tests`
- `exam_ready`
- richer `validation_options`

The response is intended to be reviewable by humans, but `/evaluate/students` only consumes the evaluation-relevant package fields, not every informational field in the response.

### Test normalization and final package cleanup

Before a package is returned or stored as ready:
- boolean oracle tests are normalized into the correct `positive` or `negative` bucket
- duplicate hidden tests are removed
- family-incompatible reused tests are pruned
- stale generic or placeholder-style content is rejected

This is important because many earlier failures were caused by structurally wrong but superficially plausible test sets.

This makes the response more useful as a debugging and review object for future evaluation.

## Evaluation Deep Dive

The live evaluation flow is now strongly package-centered.

Rough path:
1. normalize request input
2. build the shared `question_signature`
3. look up the stored package
4. if full inline context exists and no ready package is available, try to bootstrap a new package automatically
5. gather `accepted_solutions`, `hidden_tests`, and `incorrect_patterns`
6. execute hidden tests for runnable languages
7. score from deterministic evidence
8. apply template-specific final response overrides
9. repair weak generic feedback if a better package-backed message is available
10. persist evaluation history and suspicious markers

### Automatic package bootstrap during evaluation

If `/evaluate/students` receives:
- `question`
- `model_answer`
- `language`

and a valid package is missing, the evaluator now attempts to register/build a package automatically before failing.

This reduces evaluation-time errors for new inline questions.

### Package-backed scoring behavior

For validated package-backed submissions:
- hidden tests are used directly
- incorrect patterns are used directly
- accepted-solution matching is used directly
- deterministic scoring wins over LLM scoring
- specific family overrides can replace generic execution summaries when the code shape clearly matches a known correct or incorrect pattern

### What `/evaluate/students` actually uses

The evaluation path uses the package content that becomes `question_metadata`, especially:
- `question`
- `language`
- `accepted_solutions`
- `hidden_tests`
- `test_sets`
- `incorrect_patterns`
- `template_family`
- `package_status`
- `review_required`

It does not use every field returned by `/questions/register` for scoring. Fields such as `validation_options`, `generation_sources`, `llm_assisted`, and `reused_from_questions` are mainly informational.

### Final response behavior

Before the response is returned:
- contradictory score/feedback combinations are repaired
- specific package feedback can override vague generic text
- package-backed families in the guarded registry bypass unsafe feedback drift

This now includes explicit protection against recurring feedback failures such as:
- valid equivalent syntax being scored as wrong
- generic “whole string” feedback being used for wrong slice direction
- generic “return length itself” feedback being used for boolean comparisons like `>=`
- generic execution summaries being used when a family-specific deterministic message exists
- broad substring matches in incorrect patterns catching larger or different expressions

## Deterministic Guardrails

The final API layer now enforces important consistency rules.

Protected rules include:
- `100` score cannot return corrective feedback
- incorrect-pattern matches cannot remain overscored
- required hidden-test failures force low scores
- specific deterministic feedback beats generic LLM feedback
- package-backed vague feedback is repaired when a better pattern-based or template-specific message exists
- family-specific overrides run before legacy or broader pattern feedback where necessary
- simple incorrect patterns are matched conservatively to avoid false positives on related code

### Current protected Python families

The final deterministic feedback registry currently covers:
- `python::zero_check`
- `python::list_length`
- `python::list_length_equals_constant`
- `python::string_endswith`
- `python::first_two_characters`
- `python::prefix_characters_constant`
- `python::uppercase_string`
- `python::lowercase_string`
- `python::odd_check`
- `python::empty_collection_check`
- `python::non_empty_collection_check`
- `python::divisible_by_constant`
- `python::greater_than_threshold`
- `python::second_element`
- `python::element_at_index_constant`

These are protected because they have:
- deterministic package scoring
- template-aware final feedback
- regression tests

## New Question Handling

The system is now much more resilient for new Python questions than it was earlier.

What currently reduces new-question errors:
- question-text template inference
- model-answer-based family inference
- deterministic model-answer-derived baselines
- fallback family `python::model_answer_derived`
- auto-bootstrap during evaluation when full inline context is provided
- package auto-repair when stored packages are weak
- family-parameter-aware reuse filters
- boolean test rebucketing and hidden-test deduplication
- matcher-level protection against overbroad incorrect-pattern rules

What this means in practice:
- many new simple Python questions register without falling into `python::generic`
- many evaluation requests can self-heal instead of returning package-missing errors

Honest limitation:
- no system can guarantee zero errors for every possible new question shape
- but the current design is much more robust than earlier LLM-heavy or wording-only approaches
- the realistic goal is deterministic correctness for supported families and graceful rejection or fallback for unsupported shapes

## Storage and Stores

Dynamic data is stored in SQLite.

Primary stores:
- question packages: `data/question_profiles.db`
- evaluation history: `data/evaluation_history.db`
- learning signals: `data/question_learning.db`

### What each store is for

Question profile store:
- reusable per-question rulebook
- accepted solutions
- tests
- incorrect patterns
- package metadata

Evaluation history store:
- actual past evaluation results
- audit trail
- suspicious-output retrieval

Learning store:
- repeated good/bad answer patterns
- future package-improvement signals

Legacy file that may still exist:
- `data/question_profiles.json`

## Monitoring and Suspicious Evaluations

Suspicious evaluation monitoring is enabled.

Examples of suspicious reasons:
- full credit with corrective feedback
- low score with generic feedback
- accepted solution not receiving full credit
- incorrect-pattern overscoring
- generic template family usage
- package not ready for live use
- feedback too short

Query endpoint:
- `GET /monitor/suspicious-evaluations`

## Testing and CI

The repo now includes focused protection around deterministic-first evaluation.

Important suites:
- [tests/test_monitoring_and_registration.py](./tests/test_monitoring_and_registration.py)
- [tests/test_deterministic_guardrails.py](./tests/test_deterministic_guardrails.py)
- [tests/test_regressions.py](./tests/test_regressions.py)
- [tests/test_python_universal.py](./tests/test_python_universal.py)

Useful additional suites and assets:
- [tests/test_evaluator.py](./tests/test_evaluator.py)
- [tests/test_language_support.py](./tests/test_language_support.py)
- [tests/test_benchmark.py](./tests/test_benchmark.py)
- [tests/run_benchmark.py](./tests/run_benchmark.py)
- `tests/regression_cases.json`
- `tests/benchmark_cases.json`
- `tests/benchmark_thresholds.json`

### Recommended verification commands

```powershell
pytest tests/test_monitoring_and_registration.py -q
pytest tests/test_deterministic_guardrails.py -q
pytest tests/test_regressions.py -q
pytest tests/test_python_universal.py -q
```

Benchmark:

```powershell
python tests/run_benchmark.py
```

### What the focused suites currently protect

`tests/test_monitoring_and_registration.py` protects:
- generic template rejection behavior
- suspicious evaluation detection
- deterministic registry coverage
- package-backed generic-feedback repair
- registration of new supported families
- model-answer-based family inference
- model-answer-derived fallback registration
- auto-bootstrap during evaluation
- reuse compatibility for specific parameterized families
- boolean test rebucketing
- hidden-test deduplication

`tests/test_deterministic_guardrails.py` protects:
- shared signature normalization
- package-backed deterministic scoring
- avoidance of LLM scoring in protected paths
- template-specific final feedback for guarded Python families
- exact deterministic feedback for recurring wrong-answer patterns
- matcher-level protection against overbroad `contains` patterns

## CI

Guardrail CI:
- [.github/workflows/ci-evaluation-guardrails.yml](./.github/workflows/ci-evaluation-guardrails.yml)

Nightly benchmark workflow:
- [.github/workflows/nightly-benchmark.yml](./.github/workflows/nightly-benchmark.yml)

## Troubleshooting

### `POST /questions/register` returns 422

Common causes:
- package still fell back to a weak generic family
- package validation against the model answer failed
- confidence or coverage rules were not met
- a reused stored package was incompatible and got filtered out, leaving the new package below readiness thresholds

What to inspect:
- `template_family`
- `package_status`
- `package_confidence`
- `review_required`
- returned `detail.items`

### Evaluation returns a package-related error

If full inline context is present, the evaluator now tries to bootstrap a package automatically.

If it still fails:
- the model answer may be too weak to derive a safe package
- the generated package may still not satisfy registration quality gates

### Correct score but weak feedback

Likely causes:
- missing template-specific final feedback override
- incorrect-pattern fallback winning before a more specific template branch
- generic low-quality feedback not yet recognized by the repair layer
- a family is supported for deterministic scoring but not yet fully covered for deterministic wording

Look at:
- `template_family`
- `incorrect_patterns`
- final overrides in [app.py](./app.py)
- tests in [tests/test_deterministic_guardrails.py](./tests/test_deterministic_guardrails.py)

### Hidden tests are not running

Expected for:
- `html`
- `css`
- `react`
- `mysql`
- `mongodb`

### LLM context warning

A message such as:
- `n_ctx_seq (512) < n_ctx_train (4096)`

is only a capacity warning, not a crash.

## Where to Change What

If the issue is about reusable per-question logic:
- [evaluator/question_rule_generator.py](./evaluator/question_rule_generator.py)
- [evaluator/question_package/workflow.py](./evaluator/question_package/workflow.py)
- [evaluator/question_profile_repository.py](./evaluator/question_profile_repository.py)

If the issue is about evaluation-time scoring or feedback:
- [evaluator/orchestration/pipeline.py](./evaluator/orchestration/pipeline.py)
- [app.py](./app.py)

If the issue is about persistence or audit behavior:
- [evaluator/question_profile_store.py](./evaluator/question_profile_store.py)
- [evaluator/evaluation_history_store.py](./evaluator/evaluation_history_store.py)
- [evaluator/evaluation_history_repository.py](./evaluator/evaluation_history_repository.py)
- [evaluator/question_learning_store.py](./evaluator/question_learning_store.py)

If the issue is about API contracts:
- [schemas.py](./schemas.py)

## Project Structure

```text
ai-intelligent-evaluation-model/
|-- app.py
|-- config.py
|-- schemas.py
|-- README.md
|-- analysis/
|-- evaluator/
|-- llm/
|-- data/
|-- models/
|-- tests/
|-- scripts/
`-- utils/
```

Important evaluator subareas:
- `evaluator/question_rule_generator.py`
- `evaluator/question_package/`
- `evaluator/orchestration/pipeline.py`
- `evaluator/execution/shared.py`
- `evaluator/comparison/llm_comparator.py`
- `evaluator/question_profile_repository.py`

## Limitations

This project performs best on:
- controlled academic questions
- deterministic-friendly beginner and intermediate prompts
- prompts that can map to a known family or model-answer pattern

It is weaker on:
- highly open-ended design questions
- environment-dependent labs
- full browser/database/service integrations
- prompts that need broad external context beyond the evaluator sandbox

## Summary

The strongest operational flow is:
1. register questions first
2. verify packages are specific and validated
3. evaluate students against stored packages
4. monitor suspicious outputs
5. add regressions whenever a bad case appears

The current system is designed to be:
- deterministic-first
- package-backed
- strict about registration quality
- parameter-aware during reuse
- guarded against contradictory results
- more resilient for new questions
- monitored for suspicious output
- protected by tests and CI
