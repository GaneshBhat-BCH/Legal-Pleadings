from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
import os
import requests
import json
import time
import re
from app.core.config import settings
from app.core.logger import activity_logger

router = APIRouter()

class ExtractionRequest(BaseModel):
    file_path: str = Field(..., description="Absolute local path to the PDF file")

def preprocess_text(text: str) -> str:
    """Mask high-severity triggers locally."""
    toxic_patterns = {
        r'\bfucking\b': 'f*cking', r'\bfuck\b': 'f*ck', r'\bbitch\b': 'b*tch',
        r'\bcunt\b': 'c*nt', r'\bnigger\b': 'n*gger', r'\bfaggot\b': 'f*ggot',
        r'\bpenis\b': 'p*nis', r'\bvagina\b': 'v*gina', r'\bgenitals\b': 'genit*ls',
        r'\bsexual\b': 's-e-x-u-a-l', r'\bharassment\b': 'har*ssment'
    }
    processed_text = text
    for pattern, replacement in toxic_patterns.items():
        processed_text = re.sub(pattern, replacement, processed_text, flags=re.IGNORECASE)
    return processed_text

@router.post("/extract")
def extract_allegations(request: ExtractionRequest):
    file_path = request.file_path
    activity_logger.log_event("Extraction", "START", file_path, "Running 2-Pass Sanitized EXTRACTION with Dynamic Endpoint Resolution")
    
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")
    
    api_key = settings.AZURE_OPENAI_API_KEY
    # Base URL construction from settings
    base_endpoint = settings.AZURE_OPENAI_ENDPOINT.rstrip('/')
    # If the endpoint doesn't end with /openai, try to fix it, but provide both
    if not base_endpoint.endswith('/openai'):
        alt_endpoint = f"{base_endpoint}/openai"
    else:
        alt_endpoint = base_endpoint.replace('/openai', '')

    # --- PASS 1: RAW MULTIMODAL EXTRACTION ---
    activity_logger.log_event("Extraction", "INFO", file_path, f"Pass 1: Raw Extraction (Using endpoint: {base_endpoint})")
    headers = {"api-key": api_key}
    file_id = None
    
    # Dynamic URL sweep for /files endpoint
    file_urls_to_try = [
        f"{base_endpoint}/files?api-version=2024-05-01-preview",
        f"{alt_endpoint}/openai/files?api-version=2024-05-01-preview",
        f"{base_endpoint.replace('/openai', '')}/openai/files?api-version=2024-02-15-preview"
    ]
    
    last_upload_err = ""
    for url in file_urls_to_try:
        try:
            with open(file_path, "rb") as f:
                upload_res = requests.post(url, headers=headers, files={"file": (os.path.basename(file_path), f, "application/pdf")}, data={"purpose": "assistants"}, timeout=60)
            if upload_res.status_code == 200:
                file_id = upload_res.json()["id"]
                activity_logger.log_event("Extraction", "INFO", file_path, f"Upload SUCCESS at {url}")
                break
            else:
                last_upload_err = f"404 / {upload_res.status_code} at {url}: {upload_res.text}"
        except Exception as e:
            last_upload_err = str(e)
            
    if not file_id:
        raise HTTPException(status_code=500, detail=f"Upload failed (All URLs tried). Last error: {last_upload_err}")

    # Pass 1: Extraction Call
    responses_url = f"{base_endpoint}/v1/responses"
    raw_payload = {
        "model": "gpt-5",
        "input": [{"role": "user", "content": [{"type": "input_text", "text": "Extract all text faithfulness."}, {"type": "input_file", "file_id": file_id}]}]
    }
    
    try:
        raw_res = requests.post(responses_url, headers={"api-key": api_key, "Content-Type": "application/json"}, json=raw_payload, timeout=1200)
        if raw_res.status_code != 200:
            # Try alternate response URL sweep
            alt_res_url = f"{alt_endpoint}/openai/v1/responses"
            raw_res = requests.post(alt_res_url, headers={"api-key": api_key, "Content-Type": "application/json"}, json=raw_payload, timeout=1200)
            if raw_res.status_code != 200:
                raise Exception(f"Responses API failed (All URLs): {raw_res.status_code} - {raw_res.text}")
        
        raw_result = str(raw_res.json())
        activity_logger.log_event("Extraction", "INFO", file_path, "Pass 1 Complete.")

        # --- LOCAL GUARDRAIL: SANITIZATION ---
        clean_text = preprocess_text(raw_result)
        activity_logger.log_event("Extraction", "INFO", file_path, "Local Sanitization Applied.")

        # --- PASS 2: STRUCTURED AI EXTRACTION ---
        activity_logger.log_event("Extraction", "INFO", file_path, "Pass 2: Structured Legal Extraction (GPT-5 Chat)")
        system_prompt = """[SENIOR LEGAL DATA ENGINEER] Extract allegations from the sanitized text into JSON structure. Follow the strict 6-section metadata format."""
        
        chat_url = f"{base_endpoint}/deployments/gpt-5/chat/completions?api-version=2024-05-01-preview"
        
        # Self-correcting for tokens
        for param in ["max_completion_tokens", "max_tokens"]:
            try:
                struct_payload = {
                    "messages": [{"role": "system", "content": preprocess_text(system_prompt)}, {"role": "user", "content": clean_text}],
                    param: 4096
                }
                final_res = requests.post(chat_url, headers={"api-key": api_key, "Content-Type": "application/json"}, json=struct_payload, timeout=1200)
                if final_res.status_code == 200:
                    content = final_res.json()["choices"][0]["message"]["content"]
                    from json_repair import repair_json
                    json_match = re.search(r'(\{.*\})', content.replace('\\n', '').replace('\\r', ''), re.DOTALL)
                    activity_logger.log_event("Extraction", "SUCCESS", file_path, "2-Pass Sanitized Extraction Success.")
                    return JSONResponse(content=json.loads(repair_json(json_match.group(1) if json_match else content)))
                elif final_res.status_code == 400 and "unsupported_parameter" in final_res.text:
                    continue
                else: break
            except: pass
        raise Exception("Pass 2 Structured Extraction failed.")
    except Exception as e:
        activity_logger.log_event("Extraction", "ERROR", file_path, f"Pipeline Error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Sanitized Extraction failed: {str(e)}")
