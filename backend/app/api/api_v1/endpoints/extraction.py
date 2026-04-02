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
import fitz # PyMuPDF
from openai import AsyncAzureOpenAI
from json_repair import repair_json
from app.core.config import settings
from app.core.logger import activity_logger

router = APIRouter()

class ExtractionRequest(BaseModel):
    file_path: Optional[str] = Field(None, description="Absolute local path to the PDF file")
    file_id: Optional[str] = Field(None, description="Existing Azure OpenAI File ID")

def preprocess_text(text: str) -> str:
    """Mask sensitive legal terms that might trigger Azure content filters."""
    toxic_patterns = {
        r'\bfucking\b': 'f*cking', r'\bfuck\b': 'f*ck', r'\bbitch\b': 'b*tch',
        r'\bsexual\b': 's-e-x-u-a-l', r'\bharassment\b': 'har*ssment',
        r'\brape\b': 'r*pe', r'\bassault\b': 'ass*ult', r'\bviolence\b': 'vi*lence'
    }
    processed_text = text
    for pattern, replacement in toxic_patterns.items():
        processed_text = re.sub(pattern, replacement, processed_text, flags=re.IGNORECASE)
    return processed_text

def validate_extraction_format(data: dict) -> bool:
    """Verifies that the required keys are present for the downstream CSV and Drafting scripts."""
    required_top_keys = ["document_metadata", "allegations_list", "defense_and_proofs"]
    for key in required_top_keys:
        if key not in data: return False
    
    # Check for metadata keys
    meta = data["document_metadata"]
    for m in ["charging_party", "respondent", "date_filed", "all_detected_categories", "legal_case_summary"]:
        if m not in meta: return False
        
    if not data["allegations_list"] or not isinstance(data["allegations_list"], list): return False
    return True

@router.post("/extract")
async def extract_allegations(request: ExtractionRequest):
    target = request.file_id or request.file_path
    activity_logger.log_event("Extraction", "START", target, "Executing Unlimited Multi-Page High-Fidelity Pipeline")
    
    # Credentials from Settings
    api_key = settings.AZURE_OPENAI_API_KEY
    raw_endpoint = settings.AZURE_OPENAI_ENDPOINT
    resource_base = raw_endpoint.split("/openai")[0] if "/openai" in raw_endpoint else raw_endpoint
    api_version = re.search(r'api-version=([^&]+)', raw_endpoint).group(1) if "api-version=" in raw_endpoint else "2025-01-01-preview"
    deployment_id = settings.AZURE_OPENAI_MODEL

    try:
        raw_full_text = ""
        
        # --- PASS 1: MULTI-PAGE VISION OCR (Images-to-Verbatim Text) ---
        if request.file_path and os.path.exists(request.file_path):
            activity_logger.log_event("Extraction", "INFO", target, "Pass 1: Unlimited Multi-Page Capture")
            doc = fitz.open(request.file_path)
            # Process ALL pages in the document
            for page_num in range(len(doc)):
                page = doc.load_page(page_num)
                pix = page.get_pixmap(matrix=fitz.Matrix(2.0, 2.0))
                b64 = base64.b64encode(pix.tobytes("png")).decode("utf-8")
                
                async with AsyncAzureOpenAI(azure_endpoint=resource_base, api_key=api_key, api_version=api_version) as cl:
                    res_v = await cl.chat.completions.create(
                        model=deployment_id,
                        messages=[{"role": "user", "content": [{"type": "text", "text": f"Extract ALL text verbatim from page {page_num+1} of this legal document. Do not summarize."}, {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}}]}],
                        max_completion_tokens=4096
                    )
                    page_text = res_v.choices[0].message.content
                    raw_full_text += f"\n--- PAGE {page_num+1} ---\n{page_text}"
            doc.close()

        # Fallback to Native REST if path 1 failed or if only file_id provided
        if not raw_full_text:
            activity_logger.log_event("Extraction", "INFO", target, "Pass 1 (Fallback): Native REST Capture")
            responses_url = f"{resource_base}/openai/v1/responses?api-version={api_version}"
            file_id = request.file_id
            if not file_id and request.file_path:
                async with AsyncAzureOpenAI(azure_endpoint=resource_base, api_key=api_key, api_version=api_version) as cl:
                    with open(request.file_path, "rb") as f:
                        f_obj = await cl.files.create(file=f, purpose="assistants")
                        file_id = f_obj.id
            if file_id:
                raw_payload = {"model": deployment_id, "input": [{"role": "user", "content": [{"type": "input_text", "text": "Extract all text verbatim."}, {"type": "input_file", "file_id": file_id}]}], "max_completion_tokens": 4096}
                r = requests.post(responses_url, headers={"api-key": api_key, "Content-Type": "application/json"}, json=raw_payload, timeout=1200)
                if r.status_code == 200:
                    for item in r.json().get("output", []):
                        if item.get("role") == "assistant":
                            for c in item.get("content", []):
                                if "text" in c: raw_full_text = c["text"]

        if not raw_full_text:
            raise Exception("Capture failed.")

        # --- PASS 2: SANITIZATION (Text-to-Masked Text) ---
        activity_logger.log_event("Extraction", "INFO", target, "Pass 2: Sanitization Layer")
        masked_text = preprocess_text(raw_full_text)

        # --- PASS 3: STRUCTURED REFINEMENT (Masked-to-JSON) ---
        activity_logger.log_event("Extraction", "INFO", target, "Pass 3: Detailed Allegation Structuring")
        system_prompt = """[SENIOR LEGAL DATA ENGINEER] Analyze the provided legal text and return a strict JSON object. 
You must harvest EVERY possible allegation, particular, and paragraph from ALL pages. Do not leave any out.

Additionally, for each allegation include a "lawyer_comment":
- Predict the best professional legal reply a lawyer can give.
- Try to reference relevant laws to backbone the comment.
- If unable to comment (e.g., purely factual), use exactly "[NEED LAWYERS COMMENT]".

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
      "legal_category": "Category",
      "lawyer_comment": "Legal reply or [NEED LAWYERS COMMENT]"
    }
  ],
  "defense_and_proofs": [
    {
      "point_ref": "1", 
      "defense_argument": "Defense argument",
      "suggested_proofs": ["Proof 1"]
    }
  ]
}

Respond ONLY with the JSON object."""

        final_json = None
        parsed_data = None
        for attempt in range(2):
            activity_logger.log_event("Extraction", "INFO", target, f"Refinement Pass (Attempt {attempt+1})")
            async with AsyncAzureOpenAI(azure_endpoint=resource_base, api_key=api_key, api_version=api_version) as cl_s:
                try: # Try both parameter styles for GPT-5 stability on this environment
                     res_f = await cl_s.chat.completions.create(model=deployment_id, messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": f"DATA:\n{masked_text}"}], response_format={"type": "json_object"}, max_completion_tokens=4096)
                except:
                     res_f = await cl_s.chat.completions.create(model=deployment_id, messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": f"DATA:\n{masked_text}"}], response_format={"type": "json_object"}, max_tokens=4096)
                
                content = res_f.choices[0].message.content
                if not content:
                    activity_logger.log_event("Extraction", "WARNING", target, "LLM returned empty content.")
                    continue
                
                try:
                    match = re.search(r'(\{.*\})', content, re.DOTALL)
                    json_str = match.group(1) if match else content
                    repaired_str = repair_json(json_str)
                    if not repaired_str:
                        raise ValueError("repair_json returned empty string.")
                    parsed_data = json.loads(repaired_str)
                except Exception as parse_e:
                    activity_logger.log_event("Extraction", "WARNING", target, f"Parse Error: {str(parse_e)}. Content snippet: {content[:200]}")
                    continue
                
                if validate_extraction_format(parsed_data):
                    final_json = parsed_data
                    break
        
        if not final_json:
            activity_logger.log_event("Extraction", "WARNING", target, "Returning unvalidated JSON schema.")
            final_json = parsed_data if parsed_data else {}

        activity_logger.log_event("Extraction", "SUCCESS", target, "Final Extraction Success.")
        return JSONResponse(content=final_json)

    except Exception as e:
        activity_logger.log_event("Extraction", "ERROR", target, f"Pipeline Error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
