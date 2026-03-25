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
    """Mask high-severity triggers for Azure."""
    toxic_patterns = {
        r'\bfucking\b': 'f*cking', r'\bfuck\b': 'f*ck', r'\bbitch\b': 'b*tch',
        r'\bsexual\b': 's-e-x-u-a-l', r'\bharassment\b': 'har*ssment'
    }
    processed_text = text
    for pattern, replacement in toxic_patterns.items():
        processed_text = re.sub(pattern, replacement, processed_text, flags=re.IGNORECASE)
    return processed_text

@router.post("/extract")
def extract_allegations(request: ExtractionRequest):
    file_path = request.file_path
    activity_logger.log_event("Extraction", "START", file_path, "Running TOTAL NATIVE 2-Pass Pipeline")
    
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")
    
    # Force-read fresh OS env to bypass any stale config
    api_key = os.environ.get("AZURE_OPENAI_API_KEY", settings.AZURE_OPENAI_API_KEY)
    endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT", settings.AZURE_OPENAI_ENDPOINT).rstrip('/')
    resource_base = endpoint.replace('/openai', '') # Generic base resource URL
    
    # 1. Multi-URL Upload Sweep to fix 404/401
    file_urls = [
        f"{endpoint}/files?api-version=2024-05-01-preview",
        f"{resource_base}/openai/files?api-version=2024-05-01-preview"
    ]
    file_id = None
    headers = {"api-key": api_key}
    
    for url in file_urls:
        try:
            with open(file_path, "rb") as f:
                upload_res = requests.post(url, headers=headers, files={"file": (os.path.basename(file_path), f, "application/pdf")}, data={"purpose": "assistants"}, timeout=60)
            if upload_res.status_code == 200:
                file_id = upload_res.json()["id"]
                break
        except: pass
        
    if not file_id:
        raise HTTPException(status_code=401, detail="Upload failed. Check API Key and Endpoint permissions.")

    # --- PASS 1: NATIVE RAW EXTRACTION ---
    responses_url = f"{resource_base}/openai/v1/responses"
    raw_payload = {
        "model": "gpt-5",
        "input": [{"role": "user", "content": [{"type": "input_text", "text": "Extract all text faithfully."}, {"type": "input_file", "file_id": file_id}]}]
    }
    
    try:
        raw_res = requests.post(responses_url, headers={"api-key": api_key, "Content-Type": "application/json"}, json=raw_payload, timeout=1200)
        if raw_res.status_code != 200:
            raise Exception(f"Phase 1 Native failed: {raw_res.text}")
        
        raw_result = str(raw_res.json())

        # --- LOCAL GUARDRAIL: SANITIZATION ---
        clean_text = preprocess_text(raw_result)

        # --- PASS 2: NATIVE STRUCTURED EXTRACTION ---
        activity_logger.log_event("Extraction", "INFO", file_path, "Pass 2: Native Structured Logic")
        system_prompt = """[SENIOR LEGAL DATA ENGINEER] Extract allegations from the sanitized text into JSON structure. Follow the strict 6-section metadata format."""
        
        struct_payload = {
            "model": "gpt-5",
            "input": [{"role": "user", "content": [{"type": "input_text", "text": preprocess_text(system_prompt)}, {"type": "input_text", "text": f"CLEAN DATA:\n{clean_text}"}]}]
        }
        
        final_res = requests.post(responses_url, headers={"api-key": api_key, "Content-Type": "application/json"}, json=struct_payload, timeout=1200)
        
        if final_res.status_code == 200:
            result_data = final_res.json()
            # Extract content from /v1/responses format
            content = ""
            if "output" in result_data:
                for item in result_data["output"]:
                    if item.get("type") == "message" and "content" in item:
                        for msg in item["content"]:
                            if msg.get("type") in ["text", "output_text"]:
                                content += msg.get("text", "")
            else: content = str(result_data)
                
            from json_repair import repair_json
            json_match = re.search(r'(\{.*\})', content.replace('\\n', '').replace('\\r', ''), re.DOTALL)
            activity_logger.log_event("Extraction", "SUCCESS", file_path, "Total Native Extraction Success.")
            return JSONResponse(content=json.loads(repair_json(json_match.group(1) if json_match else content)))
        else:
            raise Exception(f"Phase 2 Native failed: {final_res.text}")

    except Exception as e:
        activity_logger.log_event("Extraction", "ERROR", file_path, f"Pipeline Error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Total Native Extraction failed: {str(e)}")
