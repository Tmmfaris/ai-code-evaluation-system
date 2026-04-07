# AI Intelligent Evaluation Model

FastAPI service for evaluating student answers across coding, markup, query, and web-stack questions using deterministic rules first, execution checks where possible, reusable question packages, and LLM fallback only when necessary.

## Quick Start

1. Create and activate a virtual environment.
2. Install dependencies.
3. Start the FastAPI server.
4. Open Swagger at `http://127.0.0.1:8000/docs`.
5. Try a sample evaluation request.

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install fastapi uvicorn pydantic requests llama-cpp-python
python -m uvicorn app:app --reload
```

Open:

- `http://127.0.0.1:8000/docs`

Sample request for `POST /evaluate/students`:

```json
{
  "students": [
    {
      "student_id": "demo-1",
      "submissions": [
        {
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

## Environment And Requirements

Recommended local environment:

- Python `3.12`
- Windows PowerShell commands in this README assume the current repository layout
- local writable `data/` directory for SQLite databases
- local `models/` directory for GGUF model files

Required local model:

- `models/Phi-3-mini-4k-instruct-q4.gguf`

Optional Ollama setup:

- the project can be configured to use `ollama` as a fallback provider
- default Ollama endpoint in config is `http://localhost:11434/api/generate`
- default Ollama model name in config is `mistral`
- this is optional when `llama_cpp` with the GGUF model is available

## Overview

This project is designed for academy-style and exam-style evaluation where consistency, repeatability, and explainability matter.

It supports:

- direct evaluation from `question + model_answer + student_answer + language`
- reusable package registration through `POST /questions/register`
- deterministic template-family routing for common question types
- hidden-test execution for runnable languages
- syntax and structure checks for markup and query languages
- stored package reuse and learning-signal accumulation
- local GGUF LLM fallback only when deterministic coverage is insufficient

The main design principle is:

- deterministic first
- execution second
- LLM last

## Main Routes

- `GET /`
- `GET /health`
- `POST /evaluate/students`
- `POST /questions/register`

Swagger UI:

- `http://127.0.0.1:8000/docs`

## API Endpoint Reference

### `GET /`

Use this as a simple service-availability check.

Typical use:

- verify that the FastAPI app is running
- confirm the current runtime process is reachable

### `GET /health`

Use this for runtime health inspection.

Typical response includes:

- service health status
- runtime marker
- evaluator fingerprint

Useful for:

- confirming the server restarted correctly
- checking that the expected evaluator code is active

### `POST /evaluate/students`

Primary evaluation endpoint.

Input:

- one or more students
- one or more submissions per student
- direct question context or package-aligned question context

Output:

- `execution_time`
- per-student totals
- per-question `score`, `concepts`, `logic_evaluation`, and `feedback`
- per-question `error` when evaluation could not complete normally

Best for:

- batch exam evaluation
- benchmarking
- direct faculty-side scoring

### `POST /questions/register`

Question package registration endpoint.

Input:

- one or more questions
- each with `question`, `model_answer`, and `language`
- optional `question_id`

Output:

- generated or reused package metadata
- `template_family`
- `accepted_solutions`
- `test_sets`
- `incorrect_patterns`
- `package_status`
- `package_confidence`
- package reuse and review hints

Best for:

- building reusable hidden-test packages
- stabilizing future evaluation
- improving deterministic scoring before live usage

## Request Schema Reference

The request models are defined in [schemas.py](/c:/DSA%20ICT/Internship/ai-intelligent-evaluation-model/schemas.py).

### `HiddenTestCase`

Optional hidden tests can be attached directly to a submission in direct mode.

- `input`
  serialized input payload such as `[1,2,3]`
- `expected_output`
  serialized expected result such as `6`
- `description`
  short note about the purpose of the test

### `QuestionSubmission`

Represents one student answer for one question.

- `question_id`
  optional external key such as `q1`
- `question`
  prompt text shown to the student
- `model_answer`
  faculty or reference solution
- `alternative_answers`
  optional reference variants for direct mode
- `hidden_tests`
  optional direct-mode hidden tests
- `student_answer`
  required student submission
- `language`
  language or question type such as `python`, `html`, `react`, `mysql`, or `mongodb`

### `StudentEvaluationRequest`

Represents one student and all of that student's submissions.

- `student_id`
  required student identifier
- `submissions`
  required list of `QuestionSubmission`

### `MultiStudentEvaluationRequest`

Top-level request body for `POST /evaluate/students`.

- `students`
  required list of `StudentEvaluationRequest`

### `QuestionPackageRequest`

Represents one question to register as a reusable package.

- `question_id`
  optional mapping key
- `question`
  required prompt text
- `model_answer`
  required faculty answer
- `language`
  required language label

### `MultiQuestionPackageRequest`

Top-level request body for `POST /questions/register`.

- `questions`
  required list of `QuestionPackageRequest`

## Supported Languages

- `python`
- `java`
- `javascript`
- `html`
- `css`
- `react`
- `mongodb`
- `mysql`

## Evaluation Architecture

At a high level, the evaluation pipeline runs through these layers:

1. validate and normalize the request
2. load direct question context or a stored package
3. infer a deterministic template family when possible
4. apply exact-match and accepted-solution shortcuts
5. run syntax, structure, deterministic rule, and execution checks
6. apply package hidden tests and incorrect-pattern penalties
7. fall back to the local LLM only when the deterministic path is too weak
8. calibrate and return structured scoring plus feedback

## Runtime Behavior

The service layer in [app.py](/c:/DSA%20ICT/Internship/ai-intelligent-evaluation-model/app.py) also manages evaluator freshness and response normalization.

Important runtime details:

- evaluator source files are fingerprinted
- if the fingerprint changes, the evaluator modules are reloaded before the next live evaluation
- `GET /health` returns both a runtime marker and the current evaluator fingerprint
- final API responses are sanitized before being returned to the client
- a small number of known score-correction rules are applied at API level for stability on benchmarked edge cases

Why this matters:

- if the code was changed but scores still look old, `GET /health` is the fastest sanity check
- if multiple local server processes exist, the runtime marker helps identify the live one
- the final API response can be slightly more stable than raw evaluator output because of response normalization

## Evaluation Modes

### Direct Mode

Use direct mode when you want immediate evaluation without package registration.

Send:

- `question`
- `model_answer`
- `student_answer`
- `language`

Best for:

- quick testing
- experimentation
- faculty-side spot checks

### Package Mode

Use package mode when you want stable reuse and stronger hidden tests.

Flow:

1. register questions with `POST /questions/register`
2. let the system generate or reuse package support data
3. evaluate students later against those stored packages

Best for:

- repeated exams
- standardized assessments
- stronger deterministic grading
- long-term package improvement through learning signals

## Question Packages

Question packages store reusable evaluation support data such as:

- `accepted_solutions`
- `test_sets`
- `incorrect_patterns`
- `template_family`
- `package_status`
- `package_confidence`
- question profile metadata

Important behavior:

- `question_id` is optional at registration time
- package reuse is driven by normalized question content, signature, language, and template family
- `question_id` mainly acts as an evaluation-time label or mapping key
- registration output is intended to power later evaluation

## Package Lifecycle

Question packages act as the reusable memory layer for repeated evaluation.

Typical lifecycle:

1. register a question through `POST /questions/register`
2. infer a profile and deterministic template family
3. generate or reuse accepted solutions, tests, and incorrect-pattern rules
4. assign status and confidence metadata
5. reuse that package in future `POST /evaluate/students` calls
6. store evaluation history and learning signals for later improvement

Key package fields:

- `question_signature`
  normalized question identity used for reuse
- `template_family`
  deterministic family such as `python::string_length`
- `accepted_solutions`
  known good answers or normalized variants
- `test_sets`
  positive and negative hidden tests with weights and required flags
- `incorrect_patterns`
  common wrong-answer patterns and score caps
- `package_status`
  readiness state such as `validated` or `generated`
- `package_confidence`
  confidence score used for stricter exam scenarios
- `review_required`
  signals whether manual review is still recommended

## Deterministic Coverage

Current strongest deterministic coverage is on:

- `python`
- `java`
- `javascript`

especially for common academy-style basics and structured questions.

### Python Basics

- basic math
- basic string tasks
- common list/array tasks
- palindrome
- reverse string
- reverse number
- uppercase/lowercase
- string length
- count vowels
- count words
- remove spaces
- only digits / only alphabets
- max/min
- sum collection
- first/last element
- empty checks
- list length
- balanced parentheses
- anagram
- Armstrong number
- leap year
- GCD / LCM
- power of two / power of three

### Java Basics

- beginner math and string tasks
- common array/list tasks
- palindrome, reverse string, reverse number
- uppercase/lowercase, string length, count vowels, count words
- remove spaces
- only digits / only alphabets
- even, prime, Armstrong, leap year
- GCD / LCM
- power of two / power of three
- balanced parentheses and anagram
- basic URL, email, IPv4, and JSON validation
- safe division with exception handling
- safe string-to-integer parsing
- null-safe string length

### JavaScript Basics

- beginner math and string tasks
- common array/list tasks
- palindrome, reverse string, reverse number
- uppercase/lowercase, string length, count vowels, count words
- first character / last character
- remove spaces
- only digits / only alphabets
- even, prime, Armstrong, leap year
- GCD / LCM
- power of two / power of three
- balanced parentheses and anagram
- string-to-integer conversion
- basic URL, email, IPv4, and JSON validation

### HTML Basics

- basic page structure and balanced markup
- headings and paragraphs
- links and images
- audio and video elements
- lists and tables
- forms, inputs, labels, textarea, and select/dropdown controls
- buttons
- div/span/container-style structure
- semantic layout with `header`, `nav`, `main`, `section`, and `footer`

### CSS Basics

- basic selector/declaration structure
- text color and background styling
- typography basics such as font size, font family, font weight, and text alignment
- spacing with margin and padding
- borders and border radius
- sizing with width and height
- display, inline/block, and basic positioning
- flex and grid layout prompts
- center alignment
- button, card, and hover styling

### MongoDB Basics

- basic query shape and balanced command structure
- find/filter queries
- insert, update, and delete operations
- projection and sort
- count, limit, and distinct operations
- simple aggregation and grouping prompts

### MySQL Basics

- basic query shape and balanced SQL structure
- select/filter queries
- insert, update, and delete operations
- joins
- group by and aggregate prompts
- order by, limit, and distinct
- having-clause prompts

## Brochure-Aligned Coverage

The deterministic layer has also been expanded to recognize syllabus-style wording from institute course brochures.

### Data Science And AI/ML

Currently aligned areas include:

- SQL joins, grouping, ordering, and CRUD-style query families
- Python data-science families such as:
  - train/test split
  - stratified train/test split
  - shuffle with feature/label alignment
  - classification accuracy
  - precision, recall, F1, confusion matrix, ROC-AUC, and log loss
  - MSE and RMSE
  - missing-value detection and fill strategies
  - label encoding and one-hot encoding wording
  - min-max normalization, MinMaxScaler wording, mean normalization
  - z-score standardization and basic outlier handling
  - feature/label split
  - simple linear regression prediction
  - correlation matrix and multicollinearity checks
  - k-fold cross validation
  - logistic regression, decision tree, KNN, SVM, and random forest training prompts
  - dataframe sorting and datetime year extraction
  - sigmoid, softmax, binary cross-entropy, and gradient-descent-step prompts

Partially aligned brochure wording:

- NumPy, Pandas, preprocessing, statistics, and feature-engineering phrasing
- supervised learning wording around regression, metrics, and model training
- unsupervised learning wording where deterministic families already exist
- neural-network math prompts such as activation functions and gradient-descent updates

### Cyber Security

Currently aligned areas include:

- web-security-adjacent coding prompts across supported languages
- basic URL, email, IPv4, and validation-style questions
- HTML, CSS, JavaScript, SQL, and web-stack questions often used in web-app security exercises

Still needing specialized evaluators later:

- nmap, Wireshark, netcat, Metasploit, Burp Suite, ZAP, OpenVAS, Nessus
- SSRF, request smuggling, JWT/OAuth attack labs
- Evil Twin, ARP spoofing, malware analysis
- OSINT, phishing, incident response, SIEM, IDS, and threat-intelligence labs

### SDET

Currently aligned areas include:

- API-testing-adjacent prompts such as JSON, URL, email, and IP validation
- Java, JavaScript, HTML, CSS, SQL, and web-stack families commonly used in testing exercises
- deterministic grading for parsing, validation, transformation, and expected-output style questions

Still needing specialized evaluators later:

- Selenium WebDriver flows
- JMeter performance/load testing
- Jenkins, Docker, and CI/CD pipelines
- integration and environment-driven testing labs

### MERN

Currently aligned areas include:

- HTML5 and CSS3 prompts including responsive-layout and Bootstrap-style wording
- JavaScript prompts for validation, transformation, and JSON-style API data handling
- React prompts for component-driven UI, state, forms, events, and fetch/useEffect-style loading
- MongoDB prompts for basic query, collection, CRUD, and NoSQL wording
- combined frontend, styling, client-logic, and database-question routing

Still needing specialized evaluators later:

- full Node.js and Express.js runtime behavior
- end-to-end REST API and authentication workflows
- deployment, cloud integration, and production environment tasks
- Generative AI integrations that depend on external services or models

## Evaluation Request

Use `POST /evaluate/students` to score one or more students in a single request.

Core request shape:

- `students`
  - `student_id`
  - `submissions`
    - `question_id` optional
    - `question` optional in package-driven flows but recommended
    - `model_answer`
    - `student_answer`
    - `language`

Important request behavior:

- direct mode works even without prior package registration
- package mode becomes stronger when the same normalized question has already been registered
- `question_id` acts as a mapping key, especially when strict question-ID mode is enabled
- supported languages are validated against the app configuration

```json
{
  "students": [
    {
      "student_id": "101",
      "submissions": [
        {
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

Request limits:

- max `20` students per request
- max `20` submissions per student

## Evaluation Response

Typical response shape:

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
            "logic_evaluation": "The student answer matches the model answer, and the logic is correct.",
            "feedback": "The student answer exactly matches the expected function."
          }
        }
      ]
    }
  ]
}
```

Per-question result items may contain:

- `question_id`
- `data`
- `error`

The API returns `error` when a submission could not be evaluated safely enough to build a normal score response.

## Response Schema Reference

The response models are also defined in [schemas.py](/c:/DSA%20ICT/Internship/ai-intelligent-evaluation-model/schemas.py).

### `ConceptEvaluation`

Each successful question result includes concept labels for:

- `logic`
- `edge_cases`
- `completeness`
- `efficiency`
- `readability`

These are descriptive labels, not raw percentage sub-scores.

### `EvaluationResponse`

Normal successful per-question result:

- `score`
  integer score out of `100`
- `concepts`
  concept-label summary
- `logic_evaluation`
  short explanation of how correct the core logic is
- `feedback`
  final feedback text returned to the caller

### `StudentQuestionResultItem`

Wrapper object inside each student result:

- `question_id`
  optional external question key
- `data`
  populated on normal success
- `error`
  populated when normal evaluation could not complete

### `StudentEvaluationResponse`

Per-student aggregate result:

- `student_id`
- `question_count`
- `total_score`
- `questions`

### `MultiStudentEvaluationResponse`

Batch-level response:

- `execution_time`
  total response time in seconds
- `students`
  list of `StudentEvaluationResponse`

### `QuestionPackageResponse`

Registration response shape for `POST /questions/register`.

Includes:

- original question fields
- inferred `profile`
- `question_signature`
- `template_family`
- `accepted_solutions`
- `test_sets`
- `incorrect_patterns`
- `package_status`
- `package_summary`
- `package_confidence`
- `review_required`
- positive and negative test counts
- reuse hints in `reused_from_questions`

## Scoring

Each question is scored out of `100`.

High-level split:

- rubric: `90`
- concepts: `10`

Rubric split:

- correctness: `40`
- efficiency: `20`
- readability: `15`
- structure: `15`

Concept scoring weights from configuration:

- logic: `4`
- edge_cases: `2`
- completeness: `2`
- efficiency: `1`
- readability: `1`

## Evaluation Output

Each evaluated question returns:

- `score`
- `concepts`
- `logic_evaluation`
- `feedback`

Each student result returns:

- `student_id`
- `question_count`
- `total_score`
- per-question results

## Package Registration Example

Use `POST /questions/register` to build reusable question packages.

Registration produces metadata such as:

- detected `profile`
- normalized `question_signature`
- deterministic `template_family`
- `accepted_solutions`
- `test_sets`
- `incorrect_patterns`
- `package_status`
- `package_summary`
- `package_confidence`
- `review_required`
- test counts and reuse hints

When registration succeeds well, later evaluation can use:

- registered accepted solutions
- registered hidden tests
- registered incorrect-pattern penalties
- deterministic family-specific scoring improvements

```json
{
  "questions": [
    {
      "question": "Write a function to add two numbers",
      "model_answer": "def add(a,b): return a+b",
      "language": "python"
    },
    {
      "question": "Reverse a string",
      "model_answer": "def reverse(s): return s[::-1]",
      "language": "python"
    }
  ]
}
```

## Setup And Run

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install fastapi uvicorn pydantic requests llama-cpp-python
python -m uvicorn app:app --reload
```

After startup:

- `http://127.0.0.1:8000/docs`

Expected local model file:

- `models/Phi-3-mini-4k-instruct-q4.gguf`

Configured LLM/runtime defaults from [config.py](/c:/DSA%20ICT/Internship/ai-intelligent-evaluation-model/config.py):

- provider: `llama_cpp`
- fallback provider support: `ollama`
- GGUF path: `models/Phi-3-mini-4k-instruct-q4.gguf`
- context size: `1024`
- default execution timeout: `8` seconds
- default score on evaluation error: `50`
- strict JSON output enabled for LLM parsing

Runtime feature flags:

- auto question-rule generation: enabled
- auto-activate validated questions: enabled
- require validated package for evaluation: disabled by default
- strict evaluation by `question_id`: enabled
- require faculty approval for live exam use: enabled
- minimum package confidence for exam use: `0.75`

Hidden-test runtime support:

- enabled: `python`, `java`, `javascript`
- disabled: `html`, `css`, `react`, `mysql`, `mongodb`

Health endpoints:

- `GET /health` reports service health and active runtime marker
- `GET /` can be used as a simple availability check

## Configuration Reference

Primary runtime settings live in [config.py](/c:/DSA%20ICT/Internship/ai-intelligent-evaluation-model/config.py).

### App Settings

- `APP_NAME`
  service name
- `VERSION`
  version string
- `ENABLE_LOGGING`
  controls runtime logging helpers
- `ENABLE_RAG`
  currently disabled

### LLM Settings

- `LLM_PROVIDER`
  default provider, currently `llama_cpp`
- `GGUF_MODEL_PATH`
  local GGUF path
- `N_CTX`
  context window
- `N_THREADS`
  CPU thread count
- `N_GPU_LAYERS`
  GPU offload depth, currently `0`
- `LLM_MODEL`
  fallback Ollama model
- `OLLAMA_BASE_URL`
  fallback Ollama endpoint
- `LLM_TEMPERATURE`
  low value for stable output
- `LLM_MAX_TOKENS`
  response token cap

### Scoring Settings

- `RUBRIC_WEIGHTS`
  correctness, efficiency, readability, and structure weighting
- `TOTAL_SCORE`
  maximum per-question score
- `CONCEPT_WEIGHTS`
  relative weighting for concept labels

### Analysis Settings

- `ENABLE_SYNTAX_CHECK`
- `ENABLE_LINE_ANALYSIS`
- `ENABLE_STRUCTURE_ANALYSIS`

These decide which local analyzers can contribute to evaluation.

### Error Handling

- `DEFAULT_SCORE_ON_ERROR`
- `DEFAULT_FEEDBACK_ON_ERROR`

These are used when evaluation cannot complete normally.

### Package and Exam Controls

- `AUTO_GENERATE_QUESTION_RULES`
- `AUTO_GENERATE_MAX_ALTERNATIVES`
- `AUTO_GENERATE_MAX_HIDDEN_TESTS`
- `AUTO_ACTIVATE_VALIDATED_QUESTIONS`
- `REQUIRE_VALIDATED_QUESTION_PACKAGE`
- `STRICT_EVALUATION_BY_QUESTION_ID`
- `REQUIRE_FACULTY_APPROVAL_FOR_LIVE`
- `MIN_PACKAGE_CONFIDENCE_FOR_EXAM`

### Storage Paths

- `QUESTION_PROFILE_DB_PATH`
- `EVALUATION_HISTORY_DB_PATH`
- `QUESTION_LEARNING_DB_PATH`

### Hidden-Test Runtime Matrix

From `HIDDEN_TEST_RUNTIME_FEATURES`:

- enabled: `python`, `java`, `javascript`
- disabled: `html`, `css`, `react`, `mysql`, `mongodb`

Non-runnable languages still use deterministic and static evaluation where available.

## Testing

The project includes both benchmark-style validation and regular test modules.

Available test and benchmark files:

- [tests/run_benchmark.py](/c:/DSA%20ICT/Internship/ai-intelligent-evaluation-model/tests/run_benchmark.py)
- [tests/test_benchmark.py](/c:/DSA%20ICT/Internship/ai-intelligent-evaluation-model/tests/test_benchmark.py)
- [tests/test_evaluator.py](/c:/DSA%20ICT/Internship/ai-intelligent-evaluation-model/tests/test_evaluator.py)
- [tests/test_regressions.py](/c:/DSA%20ICT/Internship/ai-intelligent-evaluation-model/tests/test_regressions.py)
- [tests/test_language_support.py](/c:/DSA%20ICT/Internship/ai-intelligent-evaluation-model/tests/test_language_support.py)
- `tests/benchmark_cases.json`
- `tests/benchmark_thresholds.json`
- `tests/regression_cases.json`

Run the benchmark:

```powershell
python tests/run_benchmark.py
```

What the benchmark does:

- loads benchmark cases from `tests/benchmark_cases.json`
- evaluates them through the live evaluator logic
- checks score ranges against expected thresholds
- reports overall accuracy
- reports accuracy by language
- reports accuracy by category
- exits with failure when configured threshold checks are not met

Run unit and integration-style tests:

```powershell
python -m pytest tests/test_benchmark.py tests/test_evaluator.py tests/test_regressions.py tests/test_language_support.py
```

What the test files are for:

- [tests/test_benchmark.py](/c:/DSA%20ICT/Internship/ai-intelligent-evaluation-model/tests/test_benchmark.py)
  benchmark and threshold checks
- [tests/test_evaluator.py](/c:/DSA%20ICT/Internship/ai-intelligent-evaluation-model/tests/test_evaluator.py)
  evaluator behavior checks
- [tests/test_regressions.py](/c:/DSA%20ICT/Internship/ai-intelligent-evaluation-model/tests/test_regressions.py)
  exact known bug-fix cases that should not silently regress
- [tests/test_language_support.py](/c:/DSA%20ICT/Internship/ai-intelligent-evaluation-model/tests/test_language_support.py)
  language support and routing checks

How to use the regression layer:

1. when you fix a scoring bug, add one case to `tests/regression_cases.json`
2. include the original question, reference answer, student answer, and expected score range
3. include a small expected feedback phrase when practical
4. run `python -m pytest tests/test_regressions.py`
5. keep the case permanently so the same bug cannot quietly return

Recommended verification flow after changing scoring logic:

1. restart the FastAPI server
2. register representative questions
3. evaluate a small sample batch
4. run `python tests/run_benchmark.py`
5. run the pytest suite

If benchmark thresholds fail:

- inspect the printed failures list from the benchmark runner
- confirm the correct deterministic family was selected
- check whether the score is too high, too low, or only phrased differently
- confirm the live API process has reloaded the updated evaluator

Use testing when:

- adding new deterministic families
- changing package-generation logic
- adjusting scoring overrides
- validating that benchmark accuracy has not regressed

## Storage

Deterministic rules and static evaluators live in code:

- `evaluator/rules/`
- `evaluator/execution/shared.py`
- `evaluator/question_rule_generator.py`
- `analysis/syntax_checker/`

Dynamic data is stored in SQLite:

- question packages: `data/question_profiles.db`
- evaluation history: `data/evaluation_history.db`
- learning signals: `data/question_learning.db`

Stored data roles:

- `question_profiles.db`
  registered question packages and reusable metadata
- `evaluation_history.db`
  saved evaluation results for audit and debugging
- `question_learning.db`
  learning signals collected from past runs

Legacy JSON profile seed:

- `data/question_profiles.json`

Additional working directories commonly present:

- `models/` for local GGUF models
- `logs/` for runtime logging output
- `tests/` for evaluator and benchmark validation

## Project Structure

```text
ai-intelligent-evaluation-model/
|-- app.py
|-- config.py
|-- schemas.py
|-- README.md
|
|-- analysis/
|   |-- line_analyzer.py
|   |-- structure_analyzer.py
|   `-- syntax_checker/
|       |-- __init__.py
|       |-- python_checker.py
|       |-- java_checker.py
|       |-- javascript_checker.py
|       |-- html_checker.py
|       |-- css_checker.py
|       |-- react_checker.py
|       |-- mysql_checker.py
|       `-- mongodb_checker.py
|
|-- evaluator/
|   |-- concept_evaluator.py
|   |-- evaluation_history_repository.py
|   |-- evaluation_history_store.py
|   |-- execution_engine.py
|   |-- main_evaluator.py
|   |-- question_classifier.py
|   |-- question_learning_repository.py
|   |-- question_learning_store.py
|   |-- question_profile_repository.py
|   |-- question_profile_store.py
|   |-- question_rule_generator.py
|   |-- comparison/
|   |   |-- answer_comparator.py
|   |   |-- feedback_generator.py
|   |   |-- llm_comparator.py
|   |   |-- logic_checker.py
|   |   |-- logic_summary.py
|   |   `-- score_calibrator.py
|   |-- execution/
|   |   |-- __init__.py
|   |   |-- shared.py
|   |   `-- python_families/
|   |       |-- __init__.py
|   |       |-- strings.py
|   |       |-- lists.py
|   |       `-- numbers.py
|   |-- orchestration/
|   |   |-- __init__.py
|   |   |-- confidence.py
|   |   `-- pipeline.py
|   |-- question_package/
|   |   |-- __init__.py
|   |   |-- approvals.py
|   |   |-- generator.py
|   |   |-- learning.py
|   |   |-- reuser.py
|   |   |-- validator.py
|   |   `-- workflow.py
|   |-- rubric_engine.py
|   |-- rule_engine.py
|   |-- scoring_engine.py
|   `-- rules/
|       |-- __init__.py
|       |-- shared.py
|       |-- javascript_rules.py
|       |-- javascript_families/
|       |   |-- __init__.py
|       |   |-- strings.py
|       |   |-- lists.py
|       |   `-- numbers.py
|       `-- python_families/
|           |-- __init__.py
|           |-- strings.py
|           |-- lists.py
|           `-- numbers.py
|
|-- llm/
|   |-- llm_engine.py
|   |-- prompt_builder.py
|   `-- response_parser.py
|
|-- data/
|   |-- question_profiles.json
|   |-- question_profiles.db
|   |-- evaluation_history.db
|   `-- question_learning.db
|
|-- tests/
|   |-- benchmark_cases.json
|   |-- benchmark_thresholds.json
|   |-- test_benchmark.py
|   |-- test_evaluator.py
|   `-- test_language_support.py
|
`-- utils/
    |-- formatter.py
    |-- helpers.py
    `-- logger.py
```

## Benchmarking And Quality Gates

Benchmark support lives in:

- [tests/run_benchmark.py](/c:/DSA%20ICT/Internship/ai-intelligent-evaluation-model/tests/run_benchmark.py)
- `tests/benchmark_cases.json`
- `tests/benchmark_thresholds.json`

What the benchmark does:

- loads benchmark cases
- runs them through `evaluate_submission`
- checks whether scores fall inside expected score ranges
- reports overall pass rate
- reports pass rate by language
- reports pass rate by category
- fails the process when configured accuracy thresholds are not met

This is useful for:

- regression detection
- validating new deterministic families
- checking that scoring changes do not silently reduce accuracy

## Troubleshooting

### The API is running but scores still look old

- call `GET /health`
- compare the returned runtime marker and evaluator fingerprint with the expected live code
- restart the server if the fingerprint did not change after evaluator edits

### A registered question is not being reused

- confirm the language matches exactly
- confirm `question_id` usage is consistent if strict question-ID mode is enabled
- check whether the faculty wording changed enough to alter the normalized signature
- re-register the question if the prompt was intentionally changed

### A package shows `generated` instead of `validated`

- the question may have fallen into a generic template family
- hidden tests may have failed validation against the model answer
- the family may need a stronger deterministic implementation

### Hidden tests are not running for some languages

That is expected for:

- `html`
- `css`
- `react`
- `mysql`
- `mongodb`

These depend more on static and deterministic checks than executable hidden tests.

### LLM-backed evaluation is weak or unavailable

- confirm the GGUF file exists at `models/Phi-3-mini-4k-instruct-q4.gguf`
- if using Ollama fallback, confirm Ollama is running locally
- verify the selected provider in [config.py](/c:/DSA%20ICT/Internship/ai-intelligent-evaluation-model/config.py)

### Benchmark accuracy dropped after a scoring change

- run `python tests/run_benchmark.py`
- inspect the failing cases carefully
- check whether a broad override or family detector changed unrelated categories
- retest one failing case through the live API if needed

## Development Workflow

Recommended maintenance loop:

1. identify the failing benchmark or question family
2. decide whether the issue belongs to package generation, deterministic rules, execution logic, or API normalization
3. patch the smallest responsible layer
4. restart the server
5. confirm `GET /health` shows the expected runtime marker and evaluator fingerprint
6. re-register representative questions if package generation changed
7. evaluate a small student batch
8. run the benchmark and pytest suite

Where changes usually belong:

- new or expanded family detection:
  [evaluator/question_rule_generator.py](/c:/DSA%20ICT/Internship/ai-intelligent-evaluation-model/evaluator/question_rule_generator.py)
- execution-specific runtime handling:
  [evaluator/execution/shared.py](/c:/DSA%20ICT/Internship/ai-intelligent-evaluation-model/evaluator/execution/shared.py)
- deterministic rule behavior:
  [evaluator/rules/shared.py](/c:/DSA%20ICT/Internship/ai-intelligent-evaluation-model/evaluator/rules/shared.py)
- API normalization, health, and runtime marker behavior:
  [app.py](/c:/DSA%20ICT/Internship/ai-intelligent-evaluation-model/app.py)
- request and response contracts:
  [schemas.py](/c:/DSA%20ICT/Internship/ai-intelligent-evaluation-model/schemas.py)

## Limitations

This project performs best on:

- controlled academy-style questions
- deterministic-friendly beginner and intermediate prompts
- questions whose intent can be mapped to a known family

It is weaker on:

- highly open-ended design questions
- environment-dependent tooling labs
- full runtime integrations that depend on external services
- domains that require broader library or system support than the current evaluator sandbox provides
- highly dynamic frontend/backend behavior that needs a real browser, real database, or deployed service

## Notes

- expanding deterministic coverage improves both speed and consistency
- post-exam learning can promote repeated strong answers and repeated mistakes into future package improvements
- hidden review routes exist internally for package approval and inspection
- benchmark guards live in `tests/test_benchmark.py`
- the strongest results come from registering questions first, then evaluating against the resulting packages

- best accuracy is on controlled academy-style questions
- expanding deterministic coverage improves both speed and consistency
- package workflow is: `generated -> validated -> live`
- post-exam learning can promote repeated strong answers and repeated mistakes into future package improvements
- hidden review routes exist internally for package approval and inspection
- benchmark guards live in `tests/test_benchmark.py`
