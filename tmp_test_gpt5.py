import os
import base64
import json
import requests
from dotenv import load_dotenv

# Load .env from the current directory (project root)
load_dotenv(".env")

class Settings:
    AZURE_OPENAI_API_KEY = os.getenv("AZURE_OPENAI_API_KEY")
    AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")

settings = Settings()

def test_gpt5_native():
    api_key = settings.AZURE_OPENAI_API_KEY
    # Based on extraction.py
    base_url = "https://ai-automationanywhere-prd-eus2-01.openai.azure.com/openai"
    deployment_name = "gpt-5"
    
    # Target file
    file_path = "C:\\Users\\GaneshBhat\\Downloads\\Samples\\Samples\\Race\\Charge\\523-2022-04007_AmendedChargeofDiscrimination_1 (1).pdf"
    
    if not os.path.exists(file_path):
        print(f"File not found: {file_path}")
        return

    print(f"Testing GPT-5 Native Extraction for: {file_path}")

    # 1. Upload File
    files_url = f"{base_url}/files?api-version=2024-05-01-preview"
    headers = {"api-key": api_key}
    
    print("1. Uploading file...")
    with open(file_path, "rb") as f:
        files = {"file": (os.path.basename(file_path), f, "application/pdf")}
        data = {"purpose": "assistants"}
        upload_res = requests.post(files_url, headers=headers, files=files, data=data)
    
    if upload_res.status_code != 200:
        print(f"Upload failed: {upload_res.status_code} - {upload_res.text}")
        return
    
    file_id = upload_res.json()["id"]
    print(f"File uploaded successfully. ID: {file_id}")

    # 2. Call Chat Completions with the file ID (The "Native" multimodal way)
    chat_url = f"{base_url}/deployments/{deployment_name}/chat/completions?api-version=2025-01-01-preview"
    
    chat_payload = {
        "messages": [
            {
                "role": "system",
                "content": "You are a professional legal extraction engine. Extract metadata and allegations from the attached document into JSON."
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": "Please analyze this document."
                    },
                    {
                        "type": "input_file", # Expected multimodal type for files in some previews
                        "file_id": file_id
                    }
                ]
            }
        ],
        "response_format": { "type": "json_object" }
    }
    
    print("2. Calling GPT-5 Chat Completions (Native Document Test)...")
    headers["Content-Type"] = "application/json"
    response = requests.post(chat_url, headers=headers, json=chat_payload)
    
    if response.status_code == 200:
        print("SUCCESS! GPT-5 Chat Completions handled the PDF natively.")
        print(json.dumps(response.json(), indent=2))
    else:
        print(f"Chat Completions failed with status {response.status_code}: {response.text}")
        print("Falling back to testing multimodal Responses API without Code Interpreter...")
        
        # Method 2: Use Responses API (v1/responses) but WITHOUT Code Interpreter tool
        responses_url = f"{base_url}/v1/responses?api-version=2024-05-01-preview"
        
        resp_payload = {
            "model": deployment_name,
            "input": [
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": "Extract all allegations from this PDF into valid JSON."},
                        {"type": "input_file", "file_id": file_id}
                    ]
                }
            ]
        }
        
        print("3. Calling GPT-5 Responses API (No tools test)...")
        resp_res = requests.post(responses_url, headers=headers, json=resp_payload)
        
        if resp_res.status_code == 200:
            print("SUCCESS! GPT-5 Responses API handled the PDF natively without Code Interpreter.")
            print(json.dumps(resp_res.json(), indent=2))
        else:
            print(f"Responses API failed: {resp_res.status_code} - {resp_res.text}")

if __name__ == "__main__":
    test_gpt5_native()
