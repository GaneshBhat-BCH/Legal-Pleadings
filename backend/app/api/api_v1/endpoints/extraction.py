from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
import os
import requests
import json
import time
import base64
import fitz  # PyMuPDF
import re
from app.core.config import settings
from app.core.logger import activity_logger

router = APIRouter()

class ExtractionRequest(BaseModel):
    file_path: str = Field(..., description="Absolute local path to the PDF file")

def preprocess_text(text: str) -> str:
    """
    Locally masks high-severity triggers for Azure.
    """
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
    activity_logger.log_event("Extraction", "START", file_path, "Starting Multi-Model Unified Extraction")
    
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail=f"File not found: {file_path}")
    
    # 1. Local Text Detection
    try:
        doc = fitz.open(file_path)
        extracted_text = ""
        for page in doc:
            extracted_text += page.get_text() + "\n"
        doc.close()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PDF read error: {str(e)}")
        
    system_prompt = """[SYSTEM ROLE: SENIOR LEGAL DATA ENGINEER]
Extract all allegations and provide a preliminary paralegal review (lawyer_note/category) in a single pass.
Return ONLY raw minified JSON. No preamble.
{
  "document_metadata": {"charging_party":"str","respondent":"str"},
  "allegations_list": [
    {"point_number": 1, "allegation_text":"str", "lawyer_note":"str", "legal_category":["str"]}
  ]
}"""

    # Model Selection
    is_scan = len(extracted_text.strip()) < 100
    # Use gpt-5 for text, gpt-4o-vision for scans
    deployment_to_use = "gpt-4o-vision" if is_scan else "gpt-5"
    
    if is_scan:
        activity_logger.log_event("Extraction", "INFO", file_path, f"Scan detected. Routing to {deployment_to_use}")
        try:
            doc = fitz.open(file_path)
            content_list = [{"type": "text", "text": preprocess_text(system_prompt)}]
            for i in range(min(len(doc), 3)):
                page = doc.load_page(i)
                pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
                b64_img = base64.b64encode(pix.tobytes("png")).decode("utf-8")
                content_list.append({"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64_img}"}})
            doc.close()
            messages = [{"role": "user", "content": content_list}]
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Vision prep error: {str(e)}")
    else:
        messages = [
            {"role": "system", "content": preprocess_text(system_prompt)},
            {"role": "user", "content": f"PROCESS DOCUMENT:\n{preprocess_text(extracted_text)}"}
        ]

    # Endpoint
    base_url = settings.AZURE_OPENAI_ENDPOINT.rstrip('/')
    # Standard Azure OpenAI Chat Completion URL
    chat_url = f"{base_url}/openai/deployments/{deployment_to_use}/chat/completions?api-version=2024-05-01-preview"
    headers = {"api-key": settings.AZURE_OPENAI_API_KEY, "Content-Type": "application/json"}

    # Dynamic Token Parameter (max_tokens vs max_completion_tokens)
    # Most gpt-4 models use 'max_tokens', gpt-5/o1 use 'max_completion_tokens'.
    params_to_try = ["max_completion_tokens", "max_tokens"]
    last_err = ""

    for param_name in params_to_try:
        try:
            payload = {"messages": messages, param_name: 4096}
            response = requests.post(chat_url, headers=headers, json=payload, timeout=1200)
            
            if response.status_code == 200:
                raw_content = response.json()["choices"][0]["message"]["content"]
                json_match = re.search(r'(\{.*\})', raw_content.replace('\\n', '').replace('\\r', ''), re.DOTALL)
                final_json_str = json_match.group(1) if json_match else raw_content
                import json
                from json_repair import repair_json
                activity_logger.log_event("Extraction", "SUCCESS", file_path, f"Done with {deployment_to_use} ({param_name})")
                return JSONResponse(content=json.loads(repair_json(final_json_str)))
            elif response.status_code == 400 and "unsupported_parameter" in response.text:
                continue # Try next parameter
            else:
                last_err = f"API Error {response.status_code}: {response.text}"
        except Exception as e:
            last_err = str(e)

    raise HTTPException(status_code=500, detail=f"Extraction failed for {deployment_to_use}. Error: {last_err}")
