import requests
import json

BASE_URL = "http://127.0.0.1:8000"

def test_signature_migration():
    print("--- 1. Registering Question with Temporary ID 'id_01' ---")
    reg_payload = {
        "questions": [
            {
                "question_id": "id_01",
                "question": "Write a function to add two numbers",
                "model_answer": "def add(a, b): return a + b",
                "language": "python"
            }
        ]
    }
    r = requests.post(f"{BASE_URL}/questions/register", json=reg_payload)
    print(f"Status: {r.status_code}")
    reg_res = r.json()
    signature = reg_res[0]["question_signature"]
    print(f"Acquired Signature: {signature}")

    print("\n--- 2. Evaluating Student with NO ID (Pure Content) ---")
    # We send the exact same question text, but NO ID.
    eval_payload = {
        "students": [
            {
                "student_id": "ST_99",
                "submissions": [
                    {
                        "question": "Write a function to add two numbers",
                        "model_answer": "def add(a, b): return a + b",
                        "student_answer": "def add(x, y): return x + y",
                        "language": "python"
                    }
                ]
            }
        ]
    }
    r = requests.post(f"{BASE_URL}/evaluate/students", json=eval_payload)
    print(f"Status: {r.status_code}")
    eval_res = r.json()
    
    # Check if it used the logic (score should be 100)
    score = eval_res["students"][0]["questions"][0]["data"]["score"]
    print(f"Evaluation Score: {score}")
    if score == 100:
        print("SUCCESS: Content-based evaluation worked without ID!")
    else:
        print("FAILURE: Score was not 100, might not have used the validated package.")

if __name__ == "__main__":
    try:
        test_signature_migration()
    except Exception as e:
        print(f"Error during test: {e}")
