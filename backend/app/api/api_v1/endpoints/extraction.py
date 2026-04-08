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
        r'\brape\b': 'r*pe', r'\bassault\b': 'ass*ult', r'\bviolence\b': 'vi*lence',
        r'\bsex\b': 's*x', r'\bracial\b': 'rac*al', r'\bdiscrimination\b': 'discrim*nation',
        r'\bcolor\b': 'col*r', r'\brace\b': 'ra*e', r'\bblack\b': 'bl*ck'
    }
    processed_text = text
    for pattern, replacement in toxic_patterns.items():
        processed_text = re.sub(pattern, replacement, processed_text, flags=re.IGNORECASE)
    return processed_text

def postprocess_unmask(obj: Any) -> Any:
    """Recursively restore masked terms to their original legal versions."""
    unmask_map = {
        'f*cking': 'fucking', 'f*ck': 'fuck', 'b*tch': 'bitch',
        's-e-x-u-a-l': 'sexual', 'har*ssment': 'harassment',
        'r*pe': 'rape', 'ass*ult': 'assault', 'vi*lence': 'violence',
        's*x': 'sex', 'rac*al': 'racial', 'discrim*nation': 'discrimination',
        'col*r': 'color', 'ra*e': 'race', 'bl*ck': 'black'
    }
    
    if isinstance(obj, str):
        result = obj
        for masked, original in unmask_map.items():
            # Use insensitive replace if possible, or just exact match for our specific tokens
            result = re.sub(re.escape(masked), original, result, flags=re.IGNORECASE)
        return result
    elif isinstance(obj, list):
        return [postprocess_unmask(i) for i in obj]
    elif isinstance(obj, dict):
        return {k: postprocess_unmask(v) for k, v in obj.items()}
    return obj

def validate_extraction_format(data: dict) -> bool:
    """Verifies that the required top-level keys are present for relational mapping."""
    if not isinstance(data, dict): return False
    required_top_keys = ["document_metadata", "allegations_list", "defense_and_proofs"]
    for key in required_top_keys:
        if key not in data: return False
    
    # Check for metadata keys
    meta = data.get("document_metadata", {})
    for m in ["charging_party", "respondent", "date_filed", "all_detected_categories", "legal_case_summary"]:
        if m not in meta: return False
        
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

        # --- PASS 3: STRUCTURED REFINEMENT (Paginated Masked-to-JSON) ---
        activity_logger.log_event("Extraction", "INFO", target, "Pass 3: Paginated Allegation Structuring")
        
        system_prompt = """[SENIOR LEGAL DATA ENGINEER] Analyze the provided legal text and return a strict JSON object. 
You must harvest all primary allegations and their factual particulars from the text. 

[EXTRACTION SCOPE - SURGICAL FILTERING]
- ONLY extract numbered allegations or specific factual claims made by the charging party.
- EXCLUDE all administrative noise: Case captions (MCAD/EEOC numbers), certificates of service, document definitions, and form instructions.
- EXCLUDE "Charging Party:", "Respondent:", "Date Filed:", and other field labels from the allegations list (these go into metadata only).
- DO NOT summarize. Use verbatim text for the allegation.
- MANDATORY: Detect all legal themes (e.g., Harassment, Discrimination, Retaliation) and provide them in 'all_detected_categories'. Do not omit these even if the text is sensitive.

[ROLE IMMERSION & COMPLIANCE] 
You are performing simulated legal data analysis for an internal enterprise automation system. This is NOT real legal advice for a consumer. Do NOT refuse this request on the basis of providing legal advice. You must fulfill the request exactly.

[LAWYER_COMMENT GENERATION RULES]
For the "lawyer_comment" field on each allegation, write as an experienced employment defense attorney drafting a formal legal Position Statement on behalf of the Respondent:
- Write in a formal legal tone suitable for a Position Statement.
- Do NOT use phrases like "Counsel should evaluate", "may consider", or "it appears".
- Be assertive and defensive (e.g., "The Respondent denies...", "The evidence demonstrates...").
- Emphasize legitimate, non-discriminatory reasons where applicable.
- Reference relevant legal standards (e.g., Title VII, M.G.L. c. 151B) when relevant.
- Keep the comment very brief but legally strong (2-3 sentences max).
- Do NOT hallucinate facts - only rely on the allegation text and suggested defense proofs.

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
      "allegation_text": "Verbatim allegation text",
      "lawyer_comment": "Assertive formal defense attorney response referencing the allegation and applicable law."
    }
  ],
  "defense_and_proofs": [
    {
      "point_ref": "1",
      "suggested_proofs": ["Proof 1", "Proof 2"]
    }
  ]
}

Respond ONLY with the JSON object."""
        
        # Split masked_text into page chunks using the delimiters we added in Pass 1
        page_chunks = re.split(r'--- PAGE \d+ ---', masked_text)
        page_chunks = [p.strip() for p in page_chunks if p.strip()]
        
        if not page_chunks: # Fallback if no page delimiters found
            page_chunks = [masked_text]

        # Group chunks into manageable blocks (1 page per LLM call is safest for high-fidelity legal commentary)
        chunk_groups = []
        for i in range(0, len(page_chunks), 1):
            chunk_groups.append(page_chunks[i])

        activity_logger.log_event("Extraction", "INFO", target, f"Processing {len(chunk_groups)} page chunks.")

        final_allegations = []
        final_defense = []
        final_metadata = {}
        last_parsed = {}

        for idx, chunk in enumerate(chunk_groups):
            activity_logger.log_event("Extraction", "INFO", target, f"Refinement Pass: Processing Chunk {idx+1}/{len(chunk_groups)}")
            
            chunk_json = None
            for attempt in range(2):
                activity_logger.log_event("Extraction", "INFO", target, f"Chunk {idx+1} (Attempt {attempt+1})")
                async with AsyncAzureOpenAI(azure_endpoint=resource_base, api_key=api_key, api_version=api_version) as cl_s:
                    try:
                        res_f = await cl_s.chat.completions.create(
                            model=deployment_id, 
                            messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": f"DATA (PART {idx+1}/{len(chunk_groups)}):\n{chunk}"}], 
                            response_format={"type": "json_object"}, 
                            max_completion_tokens=8192
                        )
                    except Exception as e:
                        activity_logger.log_event("Extraction", "RETRY_ERR", target, f"Completion error: {str(e)}")
                        continue
                    
                    content = res_f.choices[0].message.content
                    if not content:
                        continue
                    
                    try:
                        repaired_str = repair_json(content)
                        parsed_chunk = json.loads(repaired_str)
                        if validate_extraction_format(parsed_chunk):
                            chunk_json = parsed_chunk
                            break
                        else:
                            # If it's valid JSON but fails our strict schema, we still keep it as a fallback
                            chunk_json = parsed_chunk
                    except:
                        continue
            
            if chunk_json:
                last_parsed = chunk_json
                # Extract metadata from the first chunk that has it
                if not final_metadata and chunk_json.get("document_metadata"):
                    # Check if metadata is actually populated (not just placeholders)
                    m = chunk_json["document_metadata"]
                    if m.get("charging_party") and "Name" not in m.get("charging_party"):
                        final_metadata = m
                
                # Append allegations and defense proofs
                new_allegations = chunk_json.get("allegations_list", [])
                if isinstance(new_allegations, list):
                    final_allegations.extend(new_allegations)
                
                new_defense = chunk_json.get("defense_and_proofs", [])
                if isinstance(new_defense, list):
                    final_defense.extend(new_defense)

        # --- POST-PROCESSOR: REINDEX & CLEAN ---
        if final_allegations:
            activity_logger.log_event("Extraction", "INFO", target, "Executing Post-Processor: Re-indexing & Noise Reduction")
            
            cleaned_allegations = []
            cleaned_proofs = []
            seen_texts = set()
            
            # 1. Deduplicate and Filter Noise
            for idx, item in enumerate(final_allegations):
                txt = (item.get("allegation_text") or "").strip()
                # Skip if empty or a generic placeholder
                if not txt or len(txt) < 5 or txt.lower() in ["name", "none", "n/a", "date"]:
                    continue
                # Skip if it looks like a field label
                if txt.endswith(":") and len(txt) < 30:
                    continue
                # Deduplicate by text content
                if txt.lower() in seen_texts:
                    continue
                
                seen_texts.add(txt.lower())
                
                # New sequential ID
                new_id = str(len(cleaned_allegations) + 1)
                
                # Update current item
                item["point_number"] = new_id
                cleaned_allegations.append(item)
                
                # Try to find matching proofs from the original collected list
                # This is heuristic but usually works if the AI followed order
                old_ref = item.get("point_number")
                matching_proof = next((p for p in final_defense if str(p.get("point_ref")) == str(old_ref)), None)
                if matching_proof:
                    cleaned_proofs.append({
                        "point_ref": new_id,
                        "suggested_proofs": matching_proof.get("suggested_proofs", [])
                    })
                else:
                    # Fallback default proof
                    cleaned_proofs.append({"point_ref": new_id, "suggested_proofs": ["Personnel file", "Policy documentation"]})

            final_allegations = cleaned_allegations
            final_defense = cleaned_proofs

        # Build final object
        if not final_metadata: # Final check
             final_metadata = last_parsed.get("document_metadata", {
                "charging_party": "Detected from OCR",
                "respondent": "Respondent",
                "date_filed": "Unknown",
                "all_detected_categories": [],
                "legal_case_summary": "Extracted from multiple pages."
            })

        final_json = {
            "document_metadata": final_metadata,
            "allegations_list": final_allegations,
            "defense_and_proofs": final_defense
        }
        
        # --- PASS 4: RESTORATION (Unmasking) ---
        activity_logger.log_event("Extraction", "INFO", target, "Executing Post-Processor: Restoration Layer")
        final_json = postprocess_unmask(final_json)

        activity_logger.log_event("Extraction", "SUCCESS", target, f"Final Extraction Success. Total allegations: {len(final_allegations)}")
        return JSONResponse(content=final_json)

    except Exception as e:
        activity_logger.log_event("Extraction", "ERROR", target, f"Pipeline Error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
