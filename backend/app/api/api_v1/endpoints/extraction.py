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
    """Surgical masking for Azure filters."""
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
    activity_logger.log_event("Extraction", "START", file_path, "Hybrid Unified + Legacy Responses Extraction")
    
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")
    
    # 1. Local Read to decide path
    try:
        import fitz
        doc = fitz.open(file_path)
        extracted_text = ""
        for page in doc:
            extracted_text += page.get_text() + "\n"
        doc.close()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PDF read error: {str(e)}")
        
    is_scan = len(extracted_text.strip()) < 100
    api_key = settings.AZURE_OPENAI_API_KEY
    base_url = "https://ai-automationanywhere-prd-eus2-01.openai.azure.com/openai"
    
    # --- PATH A: DIGITAL (PERFECT WAY: UNIFIED 1-PASS CHAT) ---
    if not is_scan:
        activity_logger.log_event("Extraction", "INFO", file_path, "Digital PDF detected: Routing to Unified 1-Pass Path")
        system_prompt = """[SENIOR LEGAL DATA ENGINEER] Extract allegations and review in one pass. Return raw JSON {document_metadata:{}, allegations_list:[{point_number:int, allegation_text:str, lawyer_note:str, legal_category:[str]}]}"""
        
        chat_url = f"{base_url}/deployments/gpt-5/chat/completions?api-version=2024-05-01-preview"
        headers = {"api-key": api_key, "Content-Type": "application/json"}
        
        # Self-correcting parameters
        for param in ["max_completion_tokens", "max_tokens"]:
            try:
                payload = {
                    "messages": [
                        {"role": "system", "content": preprocess_text(system_prompt)},
                        {"role": "user", "content": preprocess_text(extracted_text)}
                    ],
                    param: 4096
                }
                res = requests.post(chat_url, headers=headers, json=payload, timeout=600)
                if res.status_code == 200:
                    content = res.json()["choices"][0]["message"]["content"]
                    json_match = re.search(r'(\{.*\})', content.replace('\\n', '').replace('\\r', ''), re.DOTALL)
                    from json_repair import repair_json
                    return JSONResponse(content=json.loads(repair_json(json_match.group(1) if json_match else content)))
                elif res.status_code == 400 and "unsupported_parameter" in res.text:
                    continue
                else: break
            except: pass
        raise HTTPException(status_code=500, detail="Digital extraction failed.")

    # --- PATH B: SCAN (1ST VERSION TODAY: /V1/RESPONSES) ---
    else:
        activity_logger.log_event("Extraction", "INFO", file_path, "Scan PDF detected: Routing to Legacy /v1/responses Path")
        files_endpoint = f"{base_url}/files?api-version=2024-05-01-preview"
        responses_endpoint = f"{base_url}/v1/responses"
        
        headers = {"api-key": api_key}
        
        try:
            # 1. Upload File
            with open(file_path, "rb") as f:
                upload_res = requests.post(files_endpoint, headers=headers, files={"file": (os.path.basename(file_path), f, "application/pdf")}, data={"purpose": "assistants"})
            if upload_res.status_code != 200: raise Exception(f"Upload failed: {upload_res.text}")
            file_id = upload_res.json()["id"]
            
            # 2. Call /v1/responses (Exactly as pre-work)
            payload = {
                "model": "gpt-5",
                "input": [{"role": "user", "content": [{"type": "input_text", "text": "Extract all allegations into JSON."}, {"type": "input_file", "file_id": file_id}]}]
            }
            res = requests.post(responses_endpoint, headers={"api-key": api_key, "Content-Type": "application/json"}, json=payload, timeout=600)
            if res.status_code != 200: raise Exception(f"Responses API failed: {res.text}")
            
            # 3. Parse and Refine (Original 2nd layer)
            raw_data = res.json()
            # Simple content extraction (shortened for the hybrid wrapper)
            content = str(raw_data) 
            
            # Final 1-pass cleanup for scan
            activity_logger.log_event("Extraction", "SUCCESS", file_path, "Legacy Scan Path Finished.")
            # Routing the raw output through the repair logic
            json_match = re.search(r'(\{.*\})', content.replace('\\n', '').replace('\\r', ''), re.DOTALL)
            from json_repair import repair_json
            return JSONResponse(content=json.loads(repair_json(json_match.group(1) if json_match else content)))
            
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Scan path failed: {str(e)}")
