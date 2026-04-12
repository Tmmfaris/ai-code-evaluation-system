import json
import os
import time
import sys
from pathlib import Path

# Add current directory to path so we can import app and evaluator
sys.path.append(os.getcwd())

QUEUED_DIR = "data/evaluation_queue"
RESULTS_DIR = "data/evaluation_results"

def test_robust_system():
    # 1. Prepare a "mangled" JSON (similar to what happens in shell)
    # We use single quotes for keys and values, which is INVALID JSON but common in mangled CURLs.
    mangled_json = """
    {
      'students': [
        {
          'student_id': 'TEST_ROBUST_001',
          'submissions': [
            {
              'question': 'Simple addition',
              'model_answer': '1+1',
              'student_answer': '2',
              'language': 'python'
            }
          ]
        }
      ]
    }
    """
    
    test_file = Path(QUEUED_DIR) / "test_mangled.json"
    with open(test_file, "w") as f:
        f.write(mangled_json)
    
    print(f"Placed mangled JSON in {test_file}")
    print("Waiting for background task (max 40s) or you can run the processor manually...")
    
    # In a real environment, the background task in app.py would pick this up.
    # For this verification script, we can wait or just check if it's gone and a result appeared.
    
    start_wait = time.time()
    found = False
    while time.time() - start_wait < 45:
        results = list(Path(RESULTS_DIR).glob("result_test_mangled_*.json"))
        if results:
            print(f"SUCCESS: Results found: {results[0].name}")
            with open(results[0], "r") as f:
                res_data = json.load(f)
                score = res_data["students"][0]["questions"][0]["data"]["score"]
                print(f"Graded Score: {score}")
            found = True
            break
        time.sleep(5)
    
    if not found:
        print("TIMED OUT: Results not found. Attempting manual trigger for verification...")
        from evaluator.bulk_file_processor import discover_and_process_files
        from app import _evaluate_single_submission
        discover_and_process_files(_evaluate_single_submission)
        
        results = list(Path(RESULTS_DIR).glob("result_test_mangled_*.json"))
        if results:
             print(f"SUCCESS (Manual Trigger): Results found: {results[0].name}")
        else:
             print("FAILURE: System could not repair or process the mangled file.")

if __name__ == "__main__":
    test_robust_system()
