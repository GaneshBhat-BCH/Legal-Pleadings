from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import Optional
import os
import json
import base64
import fitz # PyMuPDF
import re
import asyncio
from openai import AsyncAzureOpenAI
from json_repair import repair_json
from app.core.config import settings
from app.core.logger import activity_logger

router = APIRouter()

class ExtractionRequest(BaseModel):
    file_path: Optional[str] = Field(None, description="Absolute local path to the PDF file")
    file_id: Optional[str] = Field(None, description="Existing Azure OpenAI File ID")

def preprocess_text(text: str) -> str:
    toxic_patterns = {
        r'\bfucking\b': 'f*cking', r'\bfuck\b': 'f*ck', r'\bbitch\b': 'b*tch',
        r'\bsexual\b': 's-e-x-u-a-l', r'\bharassment\b': 'har*ssment'
    }
    processed_text = text
    for pattern, replacement in toxic_patterns.items():
        processed_text = re.sub(pattern, replacement, processed_text, flags=re.IGNORECASE)
    return processed_text

@router.post("/extract")
async def extract_allegations(request: ExtractionRequest):
    target = request.file_id or request.file_path
    activity_logger.log_event("Extraction", "START", target, "Executing Optimized Multimodal Extraction (Vision Primary)")
    
    # Credentials from Settings
    api_key = settings.AZURE_OPENAI_API_KEY
    raw_endpoint = settings.AZURE_OPENAI_ENDPOINT
    aoai_base = raw_endpoint.split("/openai")[0] if "/openai" in raw_endpoint else raw_endpoint
    api_version = re.search(r'api-version=([^&]+)', raw_endpoint).group(1) if "api-version=" in raw_endpoint else "2025-01-01-preview"
    
    # Deployment Resolution
    deployment_id = "gpt-4o" # default to a known vision-capable model
    if "/deployments/" in raw_endpoint:
        deployment_id = raw_endpoint.split("/deployments/")[1].split("/")[0]

    client = AsyncAzureOpenAI(azure_endpoint=aoai_base, api_key=api_key, api_version=api_version)

    try:
        raw_result = None
        
        # --- PHASE 1: CHAT COMPLETION VISION OCR (PROVEN PATH) ---
        if request.file_path and os.path.exists(request.file_path):
            try:
                activity_logger.log_event("Extraction", "INFO", request.file_path, "Phase 1: Local Vision capture for Chat Completion")
                
                doc = fitz.open(request.file_path)
                base64_images = []
                # Use slightly smaller matrix (1.5x) for better Azure quota compatibility
                zoom_matrix = fitz.Matrix(1.5, 1.5)
                for i in range(min(len(doc), 5)):
                    page = doc.load_page(i)
                    pix = page.get_pixmap(matrix=zoom_matrix)
                    base64_images.append(base64.b64encode(pix.tobytes("png")).decode("utf-8"))
                doc.close()

                content_items = [{"type": "text", "text": "Extract text faithfully from these legal scans."}]
                for b64 in base64_images:
                    content_items.append({"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}", "detail": "auto"}})

                # Try with gpt-4o first (Vision leader), then fallback to current deployment
                for model_candidate in ["gpt-4o", deployment_id]:
                    try:
                        response = await client.chat.completions.create(
                            model=model_candidate,
                            messages=[{"role": "user", "content": content_items}],
                            max_completion_tokens=4096
                        )
                        raw_result = response.choices[0].message.content
                        if raw_result: break
                    except: pass
                
                if raw_result:
                    activity_logger.log_event("Extraction", "SUCCESS", target, f"Vision OCR Success using {model_candidate}.")
            except Exception as e:
                activity_logger.log_event("Extraction", "ERROR", target, f"Vision Phase failed: {str(e)}")

        # --- PHASE 2: NATIVE ASSISTANTS (The Backup/User-Requested Legacy logic) ---
        if not raw_result and (request.file_id or request.file_path):
            try:
                activity_logger.log_event("Extraction", "INFO", target, "Phase 2: Native Assistant/Files Fallback")
                
                # Use existing file_id or upload one
                file_id = request.file_id
                if not file_id and request.file_path:
                    with open(request.file_path, "rb") as f:
                        f_obj = await client.files.create(file=f, purpose="assistants")
                        file_id = f_obj.id
                
                if file_id:
                    thread = await client.beta.threads.create(
                        messages=[{"role": "user", "content": "Extract allegations.", "attachments": [{"file_id": file_id, "tools": [{"type": "file_search"}]}]}]
                    )
                    run = await client.beta.threads.runs.create(thread_id=thread.id, assistant_id=deployment_id, max_completion_tokens=4096)
                    while run.status in ["queued", "in_progress"]:
                        await asyncio.sleep(2)
                        run = await client.beta.threads.runs.retrieve(thread_id=thread.id, run_id=run.id)
                    
                    if run.status == "completed":
                        msgs = await client.beta.threads.messages.list(thread_id=thread.id)
                        raw_result = msgs.data[0].content[0].text.value
            except: pass

        if not raw_result:
            raise Exception("All multimodality paths (Vision OCR, Assistants API) are restricted on this resource.")

        # --- PHASE 3: FINAL REFINEMENT & PARSING ---
        clean_data = preprocess_text(raw_result)
        refine_prompt = "[SENIOR LEGAL DATA ENGINEER] Format into 6-section JSON list."
        
        try:
             res_f = await client.chat.completions.create(
                model=deployment_id,
                messages=[{"role": "system", "content": refine_prompt}, {"role": "user", "content": clean_data}],
                response_format={"type": "json_object"},
                max_completion_tokens=4096
             )
        except:
             res_f = await client.chat.completions.create(
                model=deployment_id,
                messages=[{"role": "system", "content": refine_prompt}, {"role": "user", "content": clean_data}],
                response_format={"type": "json_object"},
                max_tokens=4096
             )
        
        f_content = res_f.choices[0].message.content
        j_match = re.search(r'(\{.*\})', f_content.replace('\\n', '').replace('\\r', ''), re.DOTALL)
        
        return JSONResponse(content=json.loads(repair_json(j_match.group(1) if j_match else f_content)))

    except Exception as e:
        activity_logger.log_event("Extraction", "ERROR", target, f"Pipeline Failure: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
