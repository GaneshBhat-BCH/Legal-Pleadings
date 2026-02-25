from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
import os
import requests
import json
import time
from app.core.config import settings
from app.core.logger import activity_logger

router = APIRouter()

class ExtractionRequest(BaseModel):
    file_path: str = Field(..., description="Absolute local path to the PDF file")

@router.post("/extract")
async def extract_allegations(request: ExtractionRequest):
    file_path = request.file_path
    
    activity_logger.log_event("Extraction", "START", file_path, "Starting Code Interpreter extraction")
    
    if not os.path.exists(file_path):
        err_msg = f"File not found: {file_path}"
        activity_logger.log_event("Extraction", "ERROR", file_path, err_msg)
        raise HTTPException(status_code=404, detail=err_msg)
    
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
            upload_res = requests.post(files_endpoint, headers=headers, files=files, data=data, timeout=60)
            
        if upload_res.status_code != 200:
            err_msg = f"Upload failed: {upload_res.status_code} - {upload_res.text}"
            activity_logger.log_event("Extraction", "ERROR", file_path, err_msg)
            raise Exception(err_msg)
            
        file_id = upload_res.json()["id"]
    except Exception as e:
        activity_logger.log_event("Extraction", "ERROR", file_path, str(e))
        raise HTTPException(status_code=500, detail=str(e))
        
    system_prompt = """[SYSTEM ROLE: EXPERT LEGAL EXTRACTION ENGINE]

You are a Senior Legal Data Engineer specializing in employment litigation. Your task is to extract core allegations and specific particulars from a legal complaint into a standardized, minified JSON object.

[MANDATORY EXTRACTION LOGIC]

Step 1: Document Intelligence & Summary: Extract names (Charging Party/Respondent) and the filing date. Write a 3-5 sentence legal summary and provide a comma-separated string of all detected protected class categories.

Step 2: Allegation & Particulars Extraction: Extract the allegations from the charging party based on the following scenarios:
- Scenario 1 (<= 10 point-by-point allegations): If the charge contains explicit point-by-point allegations (e.g., 1., 2., 3...) and there are 10 or fewer points, extract these EXACT points with zero data loss (no need to merge them).
- Scenario 2 (No clear section or > 10 points): If there is no specific allegation section or there are more than 10 allegation points, merge the meaningful points to identify the core allegations the lawyer needs to reply to. Extract a maximum of 10 points, trying to maximize the count up to 10 while keeping them highly meaningful "Actionable Allegations" requiring a rebuttal.

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
    max_retries = 3
    retry_delay = 5
    
    for attempt in range(max_retries):
        try:
            # Added a 300-second timeout to handle slow completion while preventing indefinite hanging.
            response = requests.post(responses_endpoint, headers=post_headers, json=payload, timeout=300)
            
            if response.status_code == 200:
                result = response.json()
                content = None
                if "choices" in result and len(result["choices"]) > 0:
                    content = result["choices"][0]["message"].get("content", "")
                elif "output" in result:
                    # new gpt-5 / Assistants standard format
                    outputs = result["output"]
                    text_parts = []
                    for item in outputs:
                        if item.get("type") == "message" and "content" in item:
                            for msg_content in item.get("content", []):
                                if msg_content.get("type") == "output_text" and "text" in msg_content:
                                    text_parts.append(msg_content["text"])
                    if text_parts:
                        content = "".join(text_parts)
                    else:
                        content = json.dumps(outputs)
                else:
                    content = result
                    
                if isinstance(content, list):
                    # Handle cases where content is a list of dictionaries (e.g., text blocks)
                    try:
                        content = "".join([c.get("text", "") if isinstance(c, dict) else str(c) for c in content])
                    except Exception:
                        content = json.dumps(content)
                elif isinstance(content, dict):
                    content = json.dumps(content)
                elif content is None:
                    content = ""
                else:
                    content = str(content)
                    
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
                    activity_logger.log_event("Extraction", "SUCCESS", file_path, f"Successfully parsed {len(content)} minified characters.")
                    return parsed_json
                except json.JSONDecodeError:
                    # Fallback to returning the raw content if parsing fails, but hope the prompt strictly generated minified JSON
                    err_msg = "Output formatting failed to produce valid JSON."
                    activity_logger.log_event("Extraction", "ERROR", file_path, f"{err_msg} Raw Content: {content} | Full API Response: {json.dumps(result)}")
                    raise HTTPException(status_code=500, detail=err_msg)
            else:
                err_msg = f"Analysis failed: {response.status_code} - {response.text}"
                activity_logger.log_event("Extraction", "ERROR", file_path, err_msg)
                raise Exception(err_msg)
                
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
            activity_logger.log_event("Extraction", "WARNING", file_path, f"Connection error on attempt {attempt + 1}: {str(e)}")
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
                continue
            else:
                activity_logger.log_event("Extraction", "ERROR", file_path, f"Max retries reached. Error: {str(e)}")
                raise HTTPException(status_code=500, detail="The connection to the AI extraction service was aborted. Please try again later.")
        except Exception as e:
            activity_logger.log_event("Extraction", "ERROR", file_path, str(e))
            raise HTTPException(status_code=500, detail=str(e))
