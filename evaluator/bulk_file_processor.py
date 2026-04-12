import json
import os
import time
import shutil
from pathlib import Path
from utils.logger import log_info, log_error
from evaluator.bulk_processor import process_bulk_evaluations
from schemas import MultiStudentEvaluationRequest

QUEUED_DIR = "data/evaluation_queue"
RESULTS_DIR = "data/evaluation_results"
ARCHIVE_DIR = "data/evaluation_archive"

def discover_and_process_files(evaluate_submission_func):
    """
    Scans the queued directory for .json files and processes them.
    This is intended to be run in a background loop.
    """
    queued_files = list(Path(QUEUED_DIR).glob("*.json"))
    if not queued_files:
        return

    log_info(f"Found {len(queued_files)} files in evaluation queue. Starting processing...")

    for file_path in queued_files:
        try:
            process_single_file(file_path, evaluate_submission_func)
        except Exception as e:
            log_error(f"Failed to process queued file {file_path.name}: {str(e)}")

def process_single_file(file_path: Path, evaluate_submission_func):
    """Processes a single JSON file and saves results."""
    log_info(f"Processing evaluation file: {file_path.name}")
    
    with open(file_path, "r") as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError as e:
            # Attempt a logic repair for common mangled JSON (shell issues)
            f.seek(0)
            raw_content = f.read()
            repaired_data = attempt_json_repair(raw_content)
            if repaired_data:
                data = repaired_data
            else:
                raise e

    from fastapi.encoders import jsonable_encoder
    # Wrap in Pydantic to validate
    req = MultiStudentEvaluationRequest(**data)
    
    # Process
    results = process_bulk_evaluations(req, evaluate_submission_func)
    
    # Save Results
    result_filename = f"result_{file_path.stem}_{int(time.time())}.json"
    result_path = Path(RESULTS_DIR) / result_filename
    
    with open(result_path, "w") as f:
        # jsonable_encoder safely converts Pydantic objects (like EvaluationResponse)
        # nested within 'results' to standard Python types like dict, which can be json serialized.
        json.dump(jsonable_encoder(results), f, indent=2)
        
    log_info(f"Evaluation results saved to {result_path}")
    
    # Archive original
    archive_path = Path(ARCHIVE_DIR) / f"{file_path.name}.{int(time.time())}.bak"
    shutil.move(str(file_path), str(archive_path))
    log_info(f"Original file archived to {archive_path}")

def attempt_json_repair(raw_content: str):
    """
    Attempts to fix common JSON errors caused by shell mangling.
    Uses yaml.safe_load (since YAML is a superset of JSON that allows unquoted keys)
    and ast.literal_eval (for Python-style single quotes) as robust fallbacks.
    """
    if not raw_content or not raw_content.strip():
        return None
    
    # 1. Try PyYAML (Extremely robust for unquoted keys/shell mangling)
    try:
        import yaml
        # YAML handles { students: [...] } and other mangled structures perfectly
        data = yaml.safe_load(raw_content.strip())
        if isinstance(data, (dict, list)):
            return data
    except Exception:
        pass

    # 2. Try ast.literal_eval (Handles Python-style single quotes)
    import ast
    try:
        data = ast.literal_eval(raw_content.strip())
        if isinstance(data, (dict, list)):
            return data
    except Exception:
        pass

    # 3. Naive fallback: replace ' with "
    import re
    try:
        repaired = re.sub(r"\'(.*?)\'", r'"\1"', raw_content)
        return json.loads(repaired)
    except:
        return None
