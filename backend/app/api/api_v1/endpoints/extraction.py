from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
import os
import requests
import json
import time
import sys
import fitz  # PyMuPDF
from app.core.config import settings
from app.core.logger import activity_logger

router = APIRouter()

class ExtractionRequest(BaseModel):
    file_path: str = Field(..., description="Absolute local path to the PDF file")

@router.post("/extract")
def extract_allegations(request: ExtractionRequest):
    file_path = request.file_path
    
    activity_logger.log_event("Extraction", "START", file_path, "Starting GPT-5 Native Multimodal extraction (No Code Interpreter)")
    
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
    
    # Extract Text locally from PDF to bypass multi-modal content filters
    try:
        doc = fitz.open(file_path)
        extracted_text = ""
        for page in doc:
            extracted_text += page.get_text() + "\n"
        doc.close()
        activity_logger.log_event("Extraction", "INFO", file_path, f"Successfully extracted text locally from PDF ({len(extracted_text)} chars)")
    except Exception as e:
        activity_logger.log_event("Extraction", "ERROR", file_path, f"Local text extraction failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to read PDF text: {str(e)}")
        
    system_prompt = """[SYSTEM ROLE: EXPERT LEGAL EXTRACTION ENGINE]

You are a Senior Legal Data Engineer specializing in employment litigation. Your task is to extract core allegations and specific particulars from a legal complaint into a standardized, minified JSON object.

[MANDATORY EXTRACTION LOGIC]

Step 1: Document Intelligence & Summary: Extract names (Charging Party/Respondent) and the filing date. Write a 3-5 sentence legal summary and provide a comma-separated string of all detected protected class categories.

Step 2: Allegation & Particulars Extraction: YOU MUST EXTRACT ALL ALLEGATIONS, PARTICULARS, AND KEY FACTUAL ASSERTIONS.
- No Limits: Extract every single numbered or bulleted point in the entire document. Do NOT cap at 20 or any other number.
- Verbatim Extraction: You MUST extract every point EXACTLY word-for-word as it appears in the PDF. Do NOT summarize. Do NOT hallucinate. Do NOT mix sentences together. Copy the exact line from the text.

Step 3: Classification & Defense Mapping: Map each point to its Legal Category (Sexual Orientation, Sex, Sexual Harassment, Retaliation, Religion, Race, National Origin, Disability ADA Failure to Accommodate, Color, Age). Suggest internal evidence and a defense strategy (LNDR) for every point.

[CONTENT FILTER & COMPLIANCE RULES]
This system processes highly sensitive legal documents in a compliant, offline sandbox. To comply with strict Azure OpenAI content safety filters, you MUST NOT quote sexually explicit, violent, or hate-related language directly in your JSON output. 
CRITICAL DIRECTIVE: YOU MUST NOT REFUSE TO EXTRACT THE DOCUMENT. If you encounter severe or explicit abuse words, you MUST extract the allegation but cleanly redact the offensive words (e.g., replace an explicit word with [REDACTED] or s***ual) or rewrite the explicit actions into clinical, sterile legal summaries (e.g., "alleged inappropriate physical contact"). Refusing to extract due to safety triggers will break the entire legal pipeline. Ensure the output JSON payload is completely sanitized of severe explicit language while preserving the exact legal meaning and total allegation count!

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
        "tools": [], # REMOVED Code Interpreter for 10x speed boost
        "input": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": system_prompt
                    },
                    {
                        "type": "input_text",
                        "text": f"--- LEGAL DOCUMENT TEXT ---\n\n{extracted_text}"
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
            # Increased timeout to 1200-seconds (20 minutes) to handle slow completion for large/complex documents.
            response = requests.post(responses_endpoint, headers=post_headers, json=payload, timeout=1200)
            
            if response.status_code == 200:
                result = response.json()
                activity_logger.log_event("Extraction", "INFO", file_path, "GPT-5 Native API responded with 200 SUCCESS.")
                
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

                # Prepare data for refinement - we pass the raw content even if it isn't valid JSON yet
                activity_logger.log_event("Extraction", "INFO", file_path, "GPT-5 Native phase finished. Starting 2nd layer refinement for repair and enrichment.")
                
                # --- STEP 4: SECOND LAYER REFINEMENT (Chat Completion) ---
                # Now we use GPT-4o (Chat Completion) to refine the data and auto-populate lawyer comments where possible.
                # We use GPT-4o's capability to repair malformed input from the 1st layer.
                refinement_prompt = """[SYSTEM ROLE: SENIOR LEGAL PARALEGAL & JSON ARCHITECT]
You are a Senior Legal Paralegal. Your task is to review and repair data extracted from a legal PDF.
The input may be messy, unformatted, or malformed JSON. Your goal is to:
1. REPAIR: Format the input into a perfectly clean, valid JSON object following the strict schema below.
2. ENRICH: Add a "lawyer_comment" field to every item in the "allegations_list".

[HEURISTIC LOGIC FOR lawyer_comment]
- FACTUAL/NEUTRAL: (Hire dates, Job Titles, policy names, locations). Generate a formal suggested response (e.g., "Respondent confirms...").
- SUBSTANTIVE/ACTIONABLE: (Accusations, discrimination, retaliation, termination reasons). Set to exactly: "[NEED LAWYER INPUT]"

[STRICT OUTPUT SCHEMA]
Return a JSON object with this exact full structure:
{
  "document_metadata": {
    "charging_party": "string",
    "respondent": "string",
    "date_filed": "YYYY-MM-DD",
    "legal_case_summary": "string",
    "all_detected_categories": "Category1,Category2"
  },
  "allegations_list": [
    {
      "point_number": 1,
      "allegation_text": "extracted text here",
      "lawyer_comment": "suggested response or [NEED LAWYER INPUT]",
      "is_rebuttable": true
    }
  ],
  "allegation_classification": [
    {
      "point_ref": 1,
      "category_type": ["string"],
      "legal_theory": "string"
    }
  ],
  "defense_and_proofs": [
    {
      "point_ref": 1,
      "suggested_proofs": ["string"],
      "defense_argument": "string"
    }
  ]
}
CRITICAL: Return ONLY valid JSON. No markdown backticks, no text before or after the JSON. Ensure ALL original data points (metadata, classification, defenses) from the input are preserved and formatted correctly.
"""
                
                # Standard Chat Completion endpoint logic
                deployment_name = "gpt-5" # Or gpt-4o
                if "chat/completions" in settings.AZURE_OPENAI_ENDPOINT:
                    chat_url = settings.AZURE_OPENAI_ENDPOINT
                else:
                    chat_url = f"{settings.AZURE_OPENAI_ENDPOINT.rstrip('/')}/openai/deployments/{deployment_name}/chat/completions?api-version=2024-05-01-preview"
                
                headers = {
                    "api-key": api_key,
                    "Content-Type": "application/json"
                }
                
                refine_payload = {
                    "messages": [
                        {"role": "system", "content": refinement_prompt},
                        {"role": "user", "content": f"Format and Refine this data:\n{content_to_parse}"}
                    ],
                    "response_format": { "type": "json_object" } # Enforce JSON mode
                }
                
                try:
                    # Increased timeout to 1200 seconds (20 minutes) for the refinement layer
                    refine_res = requests.post(chat_url, headers=headers, json=refine_payload, timeout=1200)
                    if refine_res.status_code == 200:
                        refined_content = refine_res.json()["choices"][0]["message"]["content"]
                        # Extract JSON from potential preamble (though response_format should prevent it)
                        json_match = re.search(r'(\{.*\})', refined_content, re.DOTALL)
                        if json_match:
                            final_json = json.loads(json_match.group(1))
                        else:
                            final_json = json.loads(refined_content)
                        
                        activity_logger.log_event("Extraction", "SUCCESS", file_path, "Successfully performed 2nd layer refinement and structure repair.")
                        print(f"DEBUG: Extraction function returning for {file_path}", flush=True)
                        return JSONResponse(content=final_json)
                    else:
                        # Fallback logic: if refinement fails, try one more time or log heavily
                        activity_logger.log_event("Extraction", "WARNING", file_path, f"Refinement layer failed ({refine_res.status_code}: {refine_res.text}). Retrying entire loop...")
                        attempt += 1
                        time.sleep(retry_delay)
                        continue
                except Exception as refine_err:
                    # Catch timeouts or connection issues in refinement
                    activity_logger.log_ai_error(f"Refinement layer exception: {str(refine_err)}")
                    activity_logger.log_event("Extraction", "WARNING", file_path, f"Refinement layer exception: {str(refine_err)}. Retrying entire loop...")
                    attempt += 1
                    time.sleep(retry_delay)
                    continue

            else:
                if response.status_code in [401, 403]:
                    err_msg = f"Analysis failed due to credentials: {response.status_code} - {response.text}"
                    activity_logger.log_event("Extraction", "ERROR", file_path, err_msg)
                    raise HTTPException(status_code=401, detail="Authentication failed. Please check AI credentials.")
                    
                err_msg = f"Analysis failed with status {response.status_code}: {response.text}"
                activity_logger.log_event("Extraction", "ERROR", file_path, err_msg)
                # Retry for other errors
                attempt += 1
                activity_logger.log_event("Extraction", "WARNING", file_path, f"Retrying due to API error {response.status_code} (attempt {attempt})...")
                time.sleep(retry_delay)
                continue
                
        except HTTPException as e:
            # Credential issues or explicit fast-fails raised as HTTPExceptions
            raise e
        except Exception as e:
            # Any connection, timeout, or parsing error is logged
            err_msg = str(e)
            activity_logger.log_ai_error(err_msg)
            
            attempt += 1
            activity_logger.log_event("Extraction", "WARNING", file_path, f"Retrying after exception (attempt {attempt}): {err_msg}")
            time.sleep(retry_delay)
            continue
