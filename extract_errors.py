import json
import subprocess
import os

subprocess.run(["python", "-m", "pytest", "tests/test_benchmark.py", "tests/test_regressions.py", "--tb=short", "-q"], capture_output=True, text=True)

# actually let's just make pytest output xml
subprocess.run(["python", "-m", "pytest", "tests/test_benchmark.py", "tests/test_regressions.py", "--junitxml=report.xml", "-q"], capture_output=True, text=True)

import xml.etree.ElementTree as ET
try:
    tree = ET.parse('report.xml')
    for tc in tree.findall('.//testcase'):
        for failure in tc.findall('failure'):
            print(f"FAIL: {tc.get('name')}")
            print(failure.get('message')[:1000])  # limit length
            print('-' * 80)
except Exception as e:
    print('Error parsing xml:', e)
