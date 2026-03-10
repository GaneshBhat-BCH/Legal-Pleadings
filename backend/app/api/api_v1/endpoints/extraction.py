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
- Scenario 1 (<= 20 point-by-point allegations): If the charge contains explicit numbered points (e.g., 1., 2., 3...) representing allegations or particulars, and there are 20 or fewer points, you MUST extract every point EXACTLY word-for-word as it appears in the PDF. Do NOT summarize. Do NOT hallucinate. Do NOT mix sentences together. Copy the exact line from the text.
- Scenario 2 (> 20 points or no clear numbering): If there are more than 20 points, extract a maximum of 20 core meaningful, actionable allegations. You must still strive to maintain the original phrasing and exact sentences from the document as much as possible. Do NOT hallucinate entirely new language.

Step 3: Classification & Defense Mapping: Map each point to its Protected Class (Age, Race, ADA, etc.) and Legal Theory (Disparate Treatment, Retaliation, etc.). Suggest internal evidence and a defense strategy (LNDR) for every point.

[CONTENT FILTER & COMPLIANCE RULES]
This system processes sensitive legal documents. To comply with strict Azure OpenAI content safety filters, you MUST NOT quote sexually explicit, violent, or hate-related language directly in your JSON output. 
Instead, you must self-censor explicit words (e.g., replace an explicit word with s***ual) or rewrite the explicit actions into clinical, sterile legal summaries (e.g., "alleged inappropriate physical contact"). Ensure the output JSON payload is completely sanitized of severe explicit language while preserving the exact legal meaning and total allegation count.

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
    retry_delay = 5
    attempt = 0
    
    while True:
        try:
            # Added a 300-second timeout to handle slow completion while preventing indefinite hanging.
            response = requests.post(responses_endpoint, headers=post_headers, json=payload, timeout=300)
            
            if response.status_code == 200:
                result = response.json()
                
                # Try to extract the response content
                    
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
                                if msg_content.get("type") in ["text", "output_text"] and "text" in msg_content:
                                    text_parts.append(msg_content["text"])
                    if text_parts:
                        content = "".join(text_parts)
                    else:
                        content = json.dumps(outputs)
                else:
                    content = result
                    
                    pass
                    
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
                    
                # Remove any unwanted whitespace (newlines/tabs) that might have slipped through
                content = content.replace('\\n', '').replace('\\r', '').replace('\\t', '')
                
                # Robust JSON extraction using python regex to find the outermost JSON object
                import re
                json_match = re.search(r'(\{.*\})', content, re.DOTALL)
                if json_match:
                    content_to_parse = json_match.group(1)
                else:
                    content_to_parse = content

                # Try parsing the cleanup response to confirm it's valid JSON
                try:
                    parsed_json = json.loads(content_to_parse)
                    activity_logger.log_event("Extraction", "SUCCESS", file_path, f"Successfully parsed {len(content_to_parse)} characters.")
                    return parsed_json
                except json.JSONDecodeError:
                    err_msg = "Output formatting failed to produce valid JSON."
                    err_details = f"{err_msg} Raw Content: {content} | Full API Response: {json.dumps(result)}"
                    activity_logger.log_event("Extraction", "ERROR", file_path, err_details)
                    raise Exception(err_details)
            else:
                if response.status_code in [401, 403]:
                    err_msg = f"Analysis failed due to credentials: {response.status_code} - {response.text}"
                    activity_logger.log_event("Extraction", "ERROR", file_path, err_msg)
                    raise HTTPException(status_code=401, detail="Authentication failed. Please check AI credentials.")
                    
                err_msg = f"Analysis failed: {response.status_code} - {response.text}"
                activity_logger.log_event("Extraction", "ERROR", file_path, err_msg)
                raise Exception(err_msg)
                
        except HTTPException as e:
            # Credential issues or explicit fast-fails raised as HTTPExceptions
            raise e
        except Exception as e:
            # Any connection, timeout, or parsing error is logged to the new CSV
            err_msg = str(e)
            activity_logger.log_ai_error(err_msg)
            
            attempt += 1
            activity_logger.log_event("Extraction", "WARNING", file_path, f"Retrying infinite loop (attempt {attempt})...")
            time.sleep(retry_delay)
            continue
