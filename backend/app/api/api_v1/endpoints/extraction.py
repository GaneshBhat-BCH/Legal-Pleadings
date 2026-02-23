from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
import os
import requests
import json
from app.core.config import settings

router = APIRouter()

class ExtractionRequest(BaseModel):
    file_path: str = Field(..., description="Absolute local path to the PDF file")

@router.post("/extract")
async def extract_allegations(request: ExtractionRequest):
    file_path = request.file_path
    
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail=f"File not found: {file_path}")
    
    api_key = settings.AZURE_OPENAI_API_KEY
    # Use exact endpoint URLs as provided
    base_url = "https://ai-automationanywhere-prd-eus2-01.openai.azure.com/openai"
    files_endpoint = f"{base_url}/files?api-version=2024-05-01-preview"
    responses_endpoint = f"{base_url}/v1/responses"
    
    headers = {
        "api-key": api_key
    }
    
    # Upload File
    try:
        with open(file_path, "rb") as f:
            files = {"file": (os.path.basename(file_path), f, "application/pdf")}
            data = {"purpose": "assistants"}
            upload_res = requests.post(files_endpoint, headers=headers, files=files, data=data)
            
        if upload_res.status_code != 200:
            raise Exception(f"Upload failed: {upload_res.status_code} - {upload_res.text}")
            
        file_id = upload_res.json()["id"]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
        
    system_prompt = """[SYSTEM ROLE: EXPERT LEGAL EXTRACTION ENGINE]

You are a Senior Legal Data Engineer specializing in employment litigation. Your task is to extract core allegations and specific particulars from a legal complaint into a standardized, minified JSON object.

[MANDATORY EXTRACTION LOGIC]

Step 1: Document Intelligence & Summary: Extract names (Charging Party/Respondent) and the filing date. Write a 3-5 sentence legal summary and provide a comma-separated string of all detected protected class categories.

Step 2: Allegation & Particulars Extraction: Group related factual sentences into distinct "Actionable Allegations" representing specific legal claims that require a rebuttal.

Step 3: Classification & Defense Mapping: Map each point to its Protected Class (Age, Race, ADA, etc.) and Legal Theory (Disparate Treatment, Retaliation, etc.). Suggest internal evidence and a defense strategy (LNDR) for every point.

[STRICT OUTPUT & MINIFICATION REQUIREMENTS]

Compact Format: Output must be a single, continuous string of raw JSON.

No Whitespace: Strictly remove all line breaks (\\n), carriage returns (\\r), and tabs.

No Double Spaces: Ensure no double spaces exist within strings or between keys.

No Markdown: Do not use backticks (```), markdown tags, or preambles.

Escape Characters: Properly escape all internal quotes and special characters to ensure valid RFC 8259 compliance.

[FIXED JSON SCHEMA]

{"document_metadata":{"charging_party":"string","respondent":"string","date_filed":"YYYY-MM-DD","legal_case_summary":"string","all_detected_categories":"Category1,Category2"},"allegations_list":[{"point_number":1,"allegation_text":"string","is_rebuttable":true}],"allegation_classification":[{"point_ref":1,"category_type":["string"],"legal_theory":"string"}],"defense_and_proofs":[{"point_ref":1,"suggested_proofs":["string"],"defense_argument":"string"}]} .. After that pass the valid JSON Which will not have any parsing issue back as a result in fast api"""

    payload = {
        "model": "gpt-5",
        "tools": [
            {
                "type": "code_interpreter",
                 "container": {
                    "type": "auto"
                  }
            }
        ],
        "input": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": system_prompt
                    },
                    {
                        "type": "input_file",
                        "file_id": file_id
                    }
                ]
            }
        ]
    }
    
    post_headers = {
        "api-key": api_key,
        "Content-Type": "application/json"
    }

    # Run Code Interpreter Extraction
    try:
        response = requests.post(responses_endpoint, headers=post_headers, json=payload)
        
        if response.status_code == 200:
            result = response.json()
            content = None
            if "choices" in result and len(result["choices"]) > 0:
                content = result["choices"][0]["message"]["content"]
            elif "output" in result:
                content = result["output"]
            else:
                content = json.dumps(result)
                
            # Clean minified string output ensuring it's valid JSON
            # 1. strip formatting tags
            if content.startswith("```json"):
                content = content[7:]
            if content.endswith("```"):
                content = content[:-3]
            
            # Remove any unwanted whitespace (newlines/tabs) that might have slipped through
            content = content.replace('\\n', '').replace('\\r', '').replace('\\t', '')
            # Try parsing the cleanup response to confirm it's valid JSON
            try:
                parsed_json = json.loads(content)
                return parsed_json
            except json.JSONDecodeError:
                # Fallback to returning the raw content if parsing fails, but hope the prompt strictly generated minified JSON
                raise HTTPException(status_code=500, detail="Output formatting failed to produce valid JSON.")
        else:
            raise Exception(f"Analysis failed: {response.status_code} - {response.text}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
