import os
import json
import requests
import time
from dotenv import load_dotenv

load_dotenv(".env")

def verify_final_logic():
    api_key = os.getenv("AZURE_OPENAI_API_KEY")
    base_url = "https://ai-automationanywhere-prd-eus2-01.openai.azure.com/openai"
    deployment_name = "gpt-5"
    file_path = "C:\\Users\\GaneshBhat\\Downloads\\Samples\\Samples\\Race\\Charge\\523-2022-04007_AmendedChargeofDiscrimination_1 (1).pdf"
    
    headers = {"api-key": api_key}
    
    # 1. Upload
    print("Step 1: Uploading file...")
    files_url = f"{base_url}/files?api-version=2024-05-01-preview"
    with open(file_path, "rb") as f:
        res = requests.post(files_url, headers=headers, files={"file": (os.path.basename(file_path), f, "application/pdf")}, data={"purpose": "assistants"})
    
    if res.status_code != 200:
        print(f"Upload failed: {res.text}")
        return
        
    file_id = res.json()["id"]
    print(f"File ID: {file_id}")

    # 2. GPT-5 Native Extraction (No Tools)
    print("Step 2: GPT-5 Native Extraction (No Code Interpreter)...")
    system_prompt = """[SYSTEM ROLE: EXPERT LEGAL EXTRACTION ENGINE] ... [Minified JSON Schema] ...""" # Shortened for test
    
    payload = {
        "model": deployment_name,
        "tools": [], 
        "input": [
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": "Extract document_metadata and allegations_list into JSON."},
                    {"type": "input_file", "file_id": file_id}
                ]
            }
        ]
    }
    
    responses_url = f"{base_url}/v1/responses"
    start_time = time.time()
    res = requests.post(responses_url, headers={"api-key": api_key, "Content-Type": "application/json"}, json=payload)
    end_time = time.time()
    
    print(f"Status: {res.status_code}")
    print(f"Extraction Time: {end_time - start_time:.2f} seconds")
    
    if res.status_code == 200:
        print("Final Verification SUCCESS.")
    else:
        print(f"Verification FAILED: {res.text}")

if __name__ == "__main__":
    verify_final_logic()
