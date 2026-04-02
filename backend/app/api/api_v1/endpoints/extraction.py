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

def validate_extraction_format(data: dict) -> bool:
    """Verifies that the required keys for the user's CSV script are present."""
    required_top_keys = ["document_metadata", "allegations_list", "defense_and_proofs"]
    for key in required_top_keys:
        if key not in data: return False
    
    if not data["allegations_list"] or not isinstance(data["allegations_list"], list): return False
    
    # Check first item for critical CSV keys
    first_item = data["allegations_list"][0]
    if "point_number" not in first_item or "allegation_text" not in first_item: return False
    
    if data["defense_and_proofs"]:
        first_defense = data["defense_and_proofs"][0]
        if "point_ref" not in first_defense or "defense_argument" not in first_defense: return False
        
    return True

@router.post("/extract")
async def extract_allegations(request: ExtractionRequest):
    target = request.file_id or request.file_path
    activity_logger.log_event("Extraction", "START", target, "Executing Cross-System Aligned Extraction (CSV Support)")
    
    # Credentials from Settings
    api_key = settings.AZURE_OPENAI_API_KEY
    raw_endpoint = settings.AZURE_OPENAI_ENDPOINT
    resource_base = raw_endpoint.split("/openai")[0] if "/openai" in raw_endpoint else raw_endpoint
    api_version = re.search(r'api-version=([^&]+)', raw_endpoint).group(1) if "api-version=" in raw_endpoint else "2025-01-01-preview"
    
    deployment_id = settings.AZURE_OPENAI_MODEL

    try:
        raw_result = None
        
        # --- PASS 1: NATIVE REST API (VERBATIM CAPTURE) ---
        responses_url = f"{resource_base}/openai/v1/responses?api-version={api_version}"
        file_id = request.file_id
        if not file_id and request.file_path:
            async with AsyncAzureOpenAI(azure_endpoint=resource_base, api_key=api_key, api_version=api_version) as temp_client:
                with open(request.file_path, "rb") as f:
                    f_obj = await temp_client.files.create(file=f, purpose="assistants")
                    file_id = f_obj.id

        if file_id:
            raw_payload = {
                "model": deployment_id,
                "input": [{"role": "user", "content": [{"type": "input_text", "text": "Extract all text verbatim."}, {"type": "input_file", "file_id": file_id}]}],
                "max_completion_tokens": 4096
            }
            res_rest = requests.post(responses_url, headers={"api-key": api_key, "Content-Type": "application/json"}, json=raw_payload, timeout=1200)
            if res_rest.status_code == 200:
                out = res_rest.json().get("output", [])
                for item in out:
                    if item.get("role") == "assistant":
                        for c in item.get("content", []):
                            if "text" in c: raw_result = c["text"]

        # Vision Fallback
        if not raw_result and request.file_path:
            import fitz
            doc = fitz.open(request.file_path)
            pix = doc[0].get_pixmap(matrix=fitz.Matrix(2.0, 2.0))
            b64 = base64.b64encode(pix.tobytes("png")).decode("utf-8")
            doc.close()
            async with AsyncAzureOpenAI(azure_endpoint=resource_base, api_key=api_key, api_version=api_version) as cl:
                res_v = await cl.chat.completions.create(model=deployment_id, messages=[{"role": "user", "content": [{"type": "text", "text": "Extract text verbatim."}, {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}}]}], max_completion_tokens=4096)
                raw_result = res_v.choices[0].message.content

        if not raw_result:
            raise Exception("Capture failed.")

        # --- PASS 2: STRUCTURED REFINEMENT (CSV-CONVERSION ALIGNMENT) ---
        clean_text = preprocess_text(raw_result)
        
        system_prompt = """[SENIOR LEGAL DATA ENGINEER] Format this legal text into a strict JSON object.
You must harvest EVERY possible allegation. Do not miss any paragraph or sentence.

Return exactly this structure:
{
  "document_metadata": {
    "charging_party": "Name",
    "respondent": "Name",
    "date_filed": "Date",
    "all_detected_categories": ["List"],
    "legal_case_summary": "Summary"
  },
  "allegations_list": [
    {
      "point_number": "1",
      "allegation_text": "Verbatim text",
      "legal_category": "Category"
    }
  ],
  "defense_and_proofs": [
    {
      "point_ref": "1", 
      "defense_argument": "Recommended defense argument",
      "suggested_proofs": ["Proof 1", "Proof 2"]
    }
  ]
}

Respond ONLY with the JSON object. Do not summarize or explain."""

        final_json = None
        for attempt in range(2): # Max 2 attempts for format correctness
            activity_logger.log_event("Extraction", "INFO", target, f"Pass 2: Structured Logic (Attempt {attempt+1})")
            async with AsyncAzureOpenAI(azure_endpoint=resource_base, api_key=api_key, api_version=api_version) as cl_s:
                try: # Try newer parameter
                     res_f = await cl_s.chat.completions.create(model=deployment_id, messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": f"DATA:\n{clean_text}"}], response_format={"type": "json_object"}, max_completion_tokens=4096)
                except: # Fallback for older SDK
                     res_f = await cl_s.chat.completions.create(model=deployment_id, messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": f"DATA:\n{clean_text}"}], response_format={"type": "json_object"}, max_tokens=4096)
                
                content = res_f.choices[0].message.content
                match = re.search(r'(\{.*\})', content.replace('\\n', '').replace('\\r', ''), re.DOTALL)
                parsed_data = json.loads(repair_json(match.group(1) if match else content))
                
                if validate_extraction_format(parsed_data):
                    final_json = parsed_data
                    break
                else:
                    activity_logger.log_event("Extraction", "WARNING", target, "Format mismatch, retrying...")

        if not final_json:
            raise Exception("Failed to produce validated JSON schema after 2 attempts.")

        activity_logger.log_event("Extraction", "SUCCESS", target, "Final Schema Aligned Extraction Success.")
        return JSONResponse(content=final_json)

    except Exception as e:
        activity_logger.log_event("Extraction", "ERROR", target, f"Pipeline Error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
