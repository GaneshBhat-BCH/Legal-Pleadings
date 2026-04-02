from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import Optional, List
import os
import json
import base64
import re
import asyncio
import requests
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
    activity_logger.log_event("Extraction", "START", target, "Executing Fully Restored a6a73fa REST Native Logic")
    
    # Credentials from Settings
    api_key = settings.AZURE_OPENAI_API_KEY
    raw_endpoint = settings.AZURE_OPENAI_ENDPOINT
    resource_base = raw_endpoint.split("/openai")[0] if "/openai" in raw_endpoint else raw_endpoint
    api_version = re.search(r'api-version=([^&]+)', raw_endpoint).group(1) if "api-version=" in raw_endpoint else "2025-01-01-preview"
    
    deployment_id = "gpt-5.4-mini" 
    if "/deployments/" in raw_endpoint:
        deployment_id = raw_endpoint.split("/deployments/")[1].split("/")[0]

    # PASS 1: NATIVE REST API (Commit a6a73fa)
    responses_url = f"{resource_base}/openai/v1/responses?api-version={api_version}"
    
    try:
        raw_result = None
        
        # Use existing file_id or upload one
        file_id = request.file_id
        if not file_id and request.file_path:
            # We still use the SDK for File Upload as it's more stable
            temp_client = AsyncAzureOpenAI(azure_endpoint=resource_base, api_key=api_key, api_version=api_version)
            with open(request.file_path, "rb") as f:
                f_obj = await temp_client.files.create(file=f, purpose="assistants")
                file_id = f_obj.id
            await temp_client.close()

        if file_id:
            activity_logger.log_event("Extraction", "INFO", target, f"Pass 1: Native REST capture via {deployment_id}")
            # The EXACT payload from a6a73fa logic but with current model
            raw_payload = {
                "model": deployment_id,
                "input": [{"role": "user", "content": [{"type": "input_text", "text": "Extract all text from this legal document faithfully."}, {"type": "input_file", "file_id": file_id}]}],
                "max_completion_tokens": 4096
            }
            
            headers = {"api-key": api_key, "Content-Type": "application/json"}
            raw_res = requests.post(responses_url, headers=headers, json=raw_payload, timeout=1200)
            
            if raw_res.status_code == 200:
                res_data = raw_res.json()
                # Parse the /v1/responses format (as used 3 days ago)
                if "output" in res_data:
                    for item in res_data["output"]:
                        if "role" in item and item["role"] == "assistant":
                            for content in item["content"]:
                                if "text" in content:
                                    raw_result = content["text"]
            else:
                activity_logger.log_event("Extraction", "ERROR", target, f"REST Phase failed: {raw_res.text}")

        # Vision Fallback if Native REST fails
        if not raw_result and request.file_path:
            import fitz
            doc = fitz.open(request.file_path)
            pix = doc[0].get_pixmap(matrix=fitz.Matrix(2.0, 2.0))
            b64 = base64.b64encode(pix.tobytes("png")).decode("utf-8")
            doc.close()
            
            async with AsyncAzureOpenAI(azure_endpoint=resource_base, api_key=api_key, api_version=api_version) as client:
                res_v = await client.chat.completions.create(model=deployment_id, messages=[{"role": "user", "content": [{"type": "text", "text": "Extract text faithfully."}, {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}}]}], max_completion_tokens=4096)
                raw_result = res_v.choices[0].message.content

        if not raw_result:
            raise Exception("Total Native Extraction failed.")

        # PASS 2: STRUCTURED REFINEMENT (SDK)
        activity_logger.log_event("Extraction", "INFO", target, "Pass 2: Structured Logic Restoration")
        clean_text = preprocess_text(raw_result)
        system_prompt = """[SENIOR LEGAL DATA ENGINEER] Extract allegations from the sanitized text into JSON structure. Follow the strict 6-section metadata format. Ensure points contain 'paragraph_number', 'allegation', 'lawyer_note', and 'legal_category'."""
        
        async with AsyncAzureOpenAI(azure_endpoint=resource_base, api_key=api_key, api_version=api_version) as client_s:
            try:
                 res_f = await client_s.chat.completions.create(model=deployment_id, messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": f"CLEAN DATA:\n{clean_text}"}], response_format={"type": "json_object"}, max_completion_tokens=4096)
            except:
                 res_f = await client_s.chat.completions.create(model=deployment_id, messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": f"CLEAN DATA:\n{clean_text}"}], response_format={"type": "json_object"}, max_tokens=4096)
            
            final_content = res_f.choices[0].message.content
        
        json_match = re.search(r'(\{.*\})', final_content.replace('\\n', '').replace('\\r', ''), re.DOTALL)
        return JSONResponse(content=json.loads(repair_json(json_match.group(1) if json_match else final_content)))

    except Exception as e:
        activity_logger.log_event("Extraction", "ERROR", target, f"Pipeline Error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
