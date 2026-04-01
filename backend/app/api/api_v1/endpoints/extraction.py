from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import Optional, List
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
    activity_logger.log_event("Extraction", "START", target, "Executing 1-Pass Faithful Extraction (Restored Logic)")
    
    # Credentials from Settings
    api_key = settings.AZURE_OPENAI_API_KEY
    raw_endpoint = settings.AZURE_OPENAI_ENDPOINT
    aoai_base = raw_endpoint.split("/openai")[0] if "/openai" in raw_endpoint else raw_endpoint
    api_version = re.search(r'api-version=([^&]+)', raw_endpoint).group(1) if "api-version=" in raw_endpoint else "2025-01-01-preview"
    
    deployment_id = "gpt-4o" 
    if "/deployments/" in raw_endpoint:
        deployment_id = raw_endpoint.split("/deployments/")[1].split("/")[0]

    client = AsyncAzureOpenAI(azure_endpoint=aoai_base, api_key=api_key, api_version=api_version)

    try:
        raw_result = None
        
        # --- PHASE 1: CHAT COMPLETION VISION OCR (RESTORED ONE-PASS LOGIC) ---
        if request.file_path and os.path.exists(request.file_path):
            try:
                activity_logger.log_event("Extraction", "INFO", request.file_path, "Phase 1: High-Fidelity capture")
                doc = fitz.open(request.file_path)
                base64_images = []
                # Using 2.0x matrix for even sharper OCR text capture
                zoom_matrix = fitz.Matrix(2.0, 2.0)
                for i in range(min(len(doc), 5)):
                    page = doc.load_page(i)
                    pix = page.get_pixmap(matrix=zoom_matrix)
                    base64_images.append(base64.b64encode(pix.tobytes("png")).decode("utf-8"))
                doc.close()

                # RESTORED PROMPT: Combined one-pass instruction to prevent AI summarization
                one_pass_prompt = """[SENIOR LEGAL DATA ENGINEER] Extract every numbered paragraph verbatim from these legal scans. 
Return the result in a strict JSON object with a list called 'points'. 
Each point MUST have:
1. 'paragraph_number' (The digit/numeral)
2. 'allegation_text' (The FULL verbatim text of that paragraph)
3. 'legal_category' (Default to 'General Employment Law' unless it is clearly Sex, Race, or Disability)

Respond with ONLY the JSON object. Do not summarize or provide descriptions of the images."""

                content_items = [{"type": "text", "text": one_pass_prompt}]
                for b64 in base64_images:
                    content_items.append({"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}", "detail": "high"}})

                response = await client.chat.completions.create(
                    model=deployment_id,
                    messages=[{"role": "user", "content": content_items}],
                    max_completion_tokens=4096
                )
                raw_result = response.choices[0].message.content
                activity_logger.log_event("Extraction", "SUCCESS", target, "One-Pass capture complete.")
            except Exception as e:
                activity_logger.log_event("Extraction", "ERROR", target, f"Phase 1 failure: {str(e)}")

        # --- PHASE 2: NATIVE ASSISTANTS (BACKUP/FILE_ID) ---
        if not raw_result and (request.file_id or request.file_path):
            try:
                activity_logger.log_event("Extraction", "INFO", target, "Phase 2: Native Assistant Fallback")
                file_id = request.file_id
                if not file_id and request.file_path:
                    with open(request.file_path, "rb") as f:
                        f_obj = await client.files.create(file=f, purpose="assistants")
                        file_id = f_obj.id
                
                if file_id:
                    thread = await client.beta.threads.create(
                        messages=[{"role": "user", "content": one_pass_prompt, "attachments": [{"file_id": file_id, "tools": [{"type": "file_search"}]}]}]
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
            raise Exception("Capture failed.")

        # --- PHASE 3: FINAL CLEANUP & PARSE ---
        clean_json = repair_json(preprocess_text(raw_result))
        json_match = re.search(r'(\{.*\})', clean_json.replace('\\n', '').replace('\\r', ''), re.DOTALL)
        
        activity_logger.log_event("Extraction", "SUCCESS", target, "Extraction Finalized (Logic Restored).")
        return JSONResponse(content=json.loads(json_match.group(1) if json_match else clean_json))

    except Exception as e:
        activity_logger.log_event("Extraction", "ERROR", target, f"Pipeline Error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
