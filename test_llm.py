# test_llm.py
from llm.llm_engine import call_llm

prompt = "Explain factorial in simple terms"

response = call_llm(prompt)

print(response)