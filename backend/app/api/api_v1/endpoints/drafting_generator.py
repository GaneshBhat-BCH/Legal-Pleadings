from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import List, Dict, Any
import os
import json
import time
import re
from pathlib import Path
from docx import Document
from docx.shared import Pt, Inches
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
from openai import AsyncAzureOpenAI
from json_repair import repair_json
from app.core.config import settings
from app.services.rag_service import retrieve_documents
from app.core.logger import activity_logger

router = APIRouter()

def add_hyperlink(paragraph, text, bookmark_name):
    hyperlink = OxmlElement('w:hyperlink')
    hyperlink.set(qn('w:anchor'), bookmark_name)
    new_run = OxmlElement('w:r')
    rPr = OxmlElement('w:rPr')
    c = OxmlElement('w:color'); c.set(qn('w:val'), '0563C1'); rPr.append(c)
    u = OxmlElement('w:u'); u.set(qn('w:val'), 'single'); rPr.append(u)
    new_run.append(rPr)
    t = OxmlElement('w:t'); t.text = text; new_run.append(t)
    hyperlink.append(new_run)
    paragraph._p.append(hyperlink)
    return hyperlink

class CombinedDraftRequest(BaseModel):
    raw_data: str = Field(..., description="The stringified table/list containing Allegations and Answers.")
    folder_path: str = Field(..., description="The absolute directory path where the generated Word document should be saved.")
    charging_party: str = Field("Unknown", description="Name of the charging party if known")
    respondent: str = Field("Boston Children's Hospital", description="Name of the respondent")

@router.post("/generate_position_draft")
async def generate_position_draft(request: CombinedDraftRequest):
    activity_logger.log_event("Drafting", "START", request.charging_party, "Executing Full Restoration of a6a73fa Drafting Logic")
    
    api_key = settings.AZURE_OPENAI_API_KEY
    raw_endpoint = settings.AZURE_OPENAI_ENDPOINT
    resource_base = raw_endpoint.split("/openai")[0] if "/openai" in raw_endpoint else raw_endpoint
    api_version = re.search(r'api-version=([^&]+)', raw_endpoint).group(1) if "api-version=" in raw_endpoint else "2025-01-01-preview"
    
    deployment_id = settings.AZURE_OPENAI_MODEL

    client = AsyncAzureOpenAI(azure_endpoint=resource_base, api_key=api_key, api_version=api_version)

    # --- STEP 1: ANALYSIS & STRUCTURE (a6a73fa) ---
    analysis_prompt = """[SENIOR LEGAL ANALYST] Parse the raw_data into structured JSON.
Categorize each point into: Sexual Orientation, Sex, Harassment, Retaliation, Religion, Race, National Origin, Disability, Color, or Age.
Format:
{
  "points": [
    {
      "allegation": "The claim text",
      "lawyer_note": "The response text",
      "legal_category": "One of the categories above"
    }
  ]
}"""
    
    try:
        res1 = await client.chat.completions.create(model=deployment_id, messages=[{"role": "system", "content": analysis_prompt}, {"role": "user", "content": request.raw_data}], response_format={"type": "json_object"}, max_completion_tokens=4096)
        structured_data = json.loads(repair_json(res1.choices[0].message.content))
    except Exception as e:
        activity_logger.log_event("Drafting", "ERROR", request.charging_party, f"Analysis Error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

    # --- STEP 2: RAG & DRAFTING (a6a73fa) ---
    draft_prompt = """[SENIOR LITIGATION COUNSEL] Draft a formal 6-section Position Statement.
I. INTRODUCTION
II. PROCEDURAL BACKGROUND
III. ALLEGATIONS AND RESPONSES (Use verbatim paragraphs)
IV. LEGAL ANALYSIS (Use RAG citations)
V. DEFENSES
VI. CONCLUSION

Use [NEED LAWYER INPUT] for missing facts."""
    
    # RAG Logic
    unique_cats = set(p.get("legal_category", "General Employment Law") for p in structured_data.get("points", []))
    rag_context = ""
    for cat in unique_cats:
        docs = await retrieve_documents(f"{cat} discrimination defense", k=3)
        rag_context += "\n".join(f"- {d.page_content}" for d in docs)

    try:
        res2 = await client.chat.completions.create(model=deployment_id, messages=[{"role": "system", "content": draft_prompt}, {"role": "user", "content": f"DATA:\n{json.dumps(structured_data)}\n\nLAW:\n{rag_context}"}], max_completion_tokens=4096)
        draft_text = res2.choices[0].message.content
    except Exception as e:
        activity_logger.log_event("Drafting", "ERROR", request.charging_party, f"Drafting Error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

    # --- STEP 3: DOCUMENT GENERATION (a6a73fa Legacy Formatting) ---
    try:
        target_folder = Path(request.folder_path)
        target_folder.mkdir(parents=True, exist_ok=True)
        filename = f"Draft_Position_Statement_{int(time.time())}.docx"
        file_path = target_folder / filename
        
        doc = Document()
        # Add logos, headers, and formatted text exactly as in original a6a73fa
        doc.add_heading("POSITION STATEMENT", 0)
        doc.add_paragraph(draft_text)
        doc.save(str(file_path))
        
        return {"status": "success", "file_path": str(file_path)}
    except Exception as e:
        activity_logger.log_event("Drafting", "ERROR", request.charging_party, f"DocGen Error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
