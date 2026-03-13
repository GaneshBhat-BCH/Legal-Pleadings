import os
import json
import requests
import time
from dotenv import load_dotenv

load_dotenv(".env")

def test_gpt5_no_tools():
    api_key = os.getenv("AZURE_OPENAI_API_KEY")
    base_url = "https://ai-automationanywhere-prd-eus2-01.openai.azure.com/openai"
    deployment_name = "gpt-5"
    file_path = "C:\\Users\\GaneshBhat\\Downloads\\Samples\\Samples\\Race\\Charge\\523-2022-04007_AmendedChargeofDiscrimination_1 (1).pdf"
    
    # 1. Upload
    print("Uploading file...")
    files_url = f"{base_url}/files?api-version=2024-05-01-preview"
    with open(file_path, "rb") as f:
        res = requests.post(files_url, headers={"api-key": api_key}, files={"file": (os.path.basename(file_path), f, "application/pdf")}, data={"purpose": "assistants"})
    
    file_id = res.json()["id"]
    print(f"File ID: {file_id}")

    # 2. Responses API WITHOUT tools
    print("Calling GPT-5 Native Extraction (No Code Interpreter)...")
    start_time = time.time()
    responses_url = f"{base_url}/v1/responses"
    
    payload = {
        "model": deployment_name,
        "input": [
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": "Extract document_metadata (charging_party, respondent, date_filed, legal_case_summary) and allegations_list from this PDF into JSON."},
                    {"type": "input_file", "file_id": file_id}
                ]
            }
        ]
    }
    
    res = requests.post(responses_url, headers={"api-key": api_key, "Content-Type": "application/json"}, json=payload)
    end_time = time.time()
    
    print(f"Status: {res.status_code}")
    print(f"Time Taken: {end_time - start_time:.2f} seconds")
    if res.status_code == 200:
        print("RESULT:")
        print(json.dumps(res.json(), indent=2))
    else:
        print(f"ERROR: {res.text}")

if __name__ == "__main__":
    test_gpt5_no_tools()
