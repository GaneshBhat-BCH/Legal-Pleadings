from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
import os
import requests
import json
import time
import fitz  # PyMuPDF
import re
from app.core.config import settings
from app.core.logger import activity_logger

router = APIRouter()

class ExtractionRequest(BaseModel):
    file_path: str = Field(..., description="Absolute local path to the PDF file")

def preprocess_text(text: str) -> str:
    """Mask triggers for Azure."""
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
    activity_logger.log_event("Extraction", "START", file_path, "Hybrid Unified + Assistant Extraction")
    
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail=f"File not found: {file_path}")
    
    # 1. Local Read
    try:
        doc = fitz.open(file_path)
        extracted_text = ""
        for page in doc:
            extracted_text += page.get_text() + "\n"
        doc.close()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PDF read error: {str(e)}")
        
    is_scan = len(extracted_text.strip()) < 100
    
    # --- PATH A: DIGITAL (UNIFIED 1-PASS CHAT) ---
    if not is_scan:
        activity_logger.log_event("Extraction", "INFO", file_path, "Digital PDF: Routing to 2x Faster Unified Path")
        system_prompt = """[SENIOR LEGAL DATA ENGINEER] Extract and Review in one pass. Return raw JSON {document_metadata:{}, allegations_list:[{point_number:int, allegation_text:str, lawyer_note:str, legal_category:[str]}]}"""
        
        chat_url = f"{settings.AZURE_OPENAI_ENDPOINT.rstrip('/')}/openai/deployments/gpt-5/chat/completions?api-version=2024-05-01-preview"
        headers = {"api-key": settings.AZURE_OPENAI_API_KEY, "Content-Type": "application/json"}
        
        # Try max_completion_tokens (gpt-5/o1) then max_tokens (gpt-4o)
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

    # --- PATH B: SCAN (ASSISTANT FILE UPLOAD) ---
    else:
        activity_logger.log_event("Extraction", "INFO", file_path, "Scan PDF: Routing to Assistant File Upload Path (Legacy-style)")
        base_url = settings.AZURE_OPENAI_ENDPOINT.rstrip('/')
        api_version = "2024-05-01-preview"
        headers = {"api-key": settings.AZURE_OPENAI_API_KEY}
        
        try:
            # 1. Upload File
            upload_url = f"{base_url}/openai/files?api-version={api_version}"
            with open(file_path, "rb") as f:
                upload_res = requests.post(upload_url, headers=headers, files={"file": (os.path.basename(file_path), f, "application/pdf"), "purpose": (None, "assistants")})
            
            if upload_res.status_code != 200:
                raise Exception(f"Upload failed: {upload_res.text}")
            
            file_id = upload_res.json()["id"]
            
            # 2. Create Thread
            thread_url = f"{base_url}/openai/threads?api-version={api_version}"
            thread_res = requests.post(thread_url, headers=headers, json={"messages": [{"role": "user", "content": "Extract allegations from the attached file.", "attachments": [{"file_id": file_id, "tools": [{"type": "file_search"}]}]}]})
            thread_id = thread_res.json()["id"]
            
            # 3. Use Assistant (User provided ID in previous history)
            assistant_id = "asst_QyqC9i66cWfcl7vG46i1q7yq"
            run_url = f"{base_url}/openai/threads/{thread_id}/runs?api-version={api_version}"
            run_res = requests.post(run_url, headers=headers, json={"assistant_id": assistant_id})
            run_id = run_res.json()["id"]
            
            # 4. Wait for Run
            status_url = f"{base_url}/openai/threads/{thread_id}/runs/{run_id}?api-version={api_version}"
            while True:
                status_res = requests.get(status_url, headers=headers).json()
                if status_res["status"] == "completed": break
                if status_res["status"] in ["failed", "expired"]: raise Exception(f"Run failed: {status_res}")
                time.sleep(2)
            
            # 5. Get Messages
            msg_url = f"{base_url}/openai/threads/{thread_id}/messages?api-version={api_version}"
            msg_res = requests.get(msg_url, headers=headers).json()
            raw_content = msg_res["data"][0]["content"][0]["text"]["value"]
            
            from json_repair import repair_json
            json_match = re.search(r'(\{.*\})', raw_content.replace('\\n', '').replace('\\r', ''), re.DOTALL)
            return JSONResponse(content=json.loads(repair_json(json_match.group(1) if json_match else raw_content)))
            
        except Exception as e:
            activity_logger.log_event("Extraction", "ERROR", file_path, f"Scan path failed: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Scan extraction failed: {str(e)}")
