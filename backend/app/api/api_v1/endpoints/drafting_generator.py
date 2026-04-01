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

# --- UTILS ---
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

_HERE = Path(__file__).parent
_ASSETS_DIR = _HERE.parent.parent.parent.parent / "assets"
LEFT_LOGO = _ASSETS_DIR / "bch_logo.png"
RIGHT_LOGO = _ASSETS_DIR / "hms_logo.png"

class CombinedDraftRequest(BaseModel):
    raw_data: str = Field(..., description="The stringified table/list containing Allegations and Answers.")
    folder_path: str = Field(..., description="The absolute directory path where the generated Word document should be saved.")
    charging_party: str = Field("Unknown", description="Name of the charging party if known")
    respondent: str = Field("Boston Children's Hospital", description="Name of the respondent")

@router.post("/generate_position_draft")
async def generate_position_draft(request: CombinedDraftRequest):
    activity_logger.log_event("Drafting", "START", request.charging_party, "Processing SDK-Powered Legal Draft (GPT-5/o1)")
    
    api_key = settings.AZURE_OPENAI_API_KEY
    raw_endpoint = settings.AZURE_OPENAI_ENDPOINT
    
    # Resolve SDK Base (Same as Matching Engine)
    aoai_base = raw_endpoint.split("/openai")[0] if "/openai" in raw_endpoint else raw_endpoint
    api_version = re.search(r'api-version=([^&]+)', raw_endpoint).group(1) if "api-version=" in raw_endpoint else "2025-01-01-preview"
    deployment_id = raw_endpoint.split("/deployments/")[1].split("/")[0] if "/deployments/" in raw_endpoint else "gpt-5"

    client = AsyncAzureOpenAI(azure_endpoint=aoai_base, api_key=api_key, api_version=api_version)

    # --- STEP 1: ANALYSIS ---
    analysis_prompt = """[SENIOR LEGAL ANALYST] Parse the following verified allegations and facts into clean JSON. Categorize each point into one of the 10 standard legal categories (Sexual Orientation, Sex, Harassment, Retaliation, Religion, Race, National Origin, Disability, Color, Age)."""
    
    try:
        # Use max_completion_tokens for GPT-5/o1
        try:
             res1 = await client.chat.completions.create(
                model=deployment_id,
                messages=[{"role": "system", "content": analysis_prompt}, {"role": "user", "content": f"DATA:\n{request.raw_data}"}],
                response_format={"type": "json_object"},
                max_completion_tokens=4096
             )
        except:
             res1 = await client.chat.completions.create(
                model=deployment_id,
                messages=[{"role": "system", "content": analysis_prompt}, {"role": "user", "content": f"DATA:\n{request.raw_data}"}],
                response_format={"type": "json_object"},
                max_tokens=4096
             )
        
        structured_data = json.loads(repair_json(res1.choices[0].message.content))
    except Exception as e:
        activity_logger.log_event("Drafting", "ERROR", request.charging_party, f"Analysis Error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

    # --- STEP 2: RAG ---
    unique_categories = set(p.get("legal_category", "General Employment Law") for p in structured_data.get("points", []))
    rag_blocks = []
    total_citations = 0
    for cat in unique_categories:
        try:
            docs = await retrieve_documents(f"{cat} discrimination defense", k=3)
            if docs:
                rag_blocks.append(f"[CATEGORY: {cat}]\n" + "\n".join(f"- {d.page_content}" for d in docs))
                total_citations += len(docs)
        except: pass
    rag_context = "\n\n".join(rag_blocks)

    # --- STEP 3: DRAFTING ---
    draft_prompt = """[SENIOR LITIGATION COUNSEL] Draft a formal 6-section Position Statement (I. Intro, II. Background, III. Allegations/Responses, IV. Analysis, V. Defenses, VI. Conclusion). Use Section III preamble exactly. Use [NEED LAWYER INPUT] protection."""
    
    try:
        # Use max_completion_tokens for the main drafting synthesis
        try:
            res2 = await client.chat.completions.create(
                model=deployment_id,
                messages=[{"role": "system", "content": draft_prompt}, {"role": "user", "content": f"ANALYSIS:\n{json.dumps(structured_data)}\n\nLAW:\n{rag_context}"}],
                response_format={"type": "json_object"},
                max_completion_tokens=4096
            )
        except:
            res2 = await client.chat.completions.create(
                model=deployment_id,
                messages=[{"role": "system", "content": draft_prompt}, {"role": "user", "content": f"ANALYSIS:\n{json.dumps(structured_data)}\n\nLAW:\n{rag_context}"}],
                response_format={"type": "json_object"},
                max_tokens=4096
            )
            
        draft_data = json.loads(repair_json(res2.choices[0].message.content))
    except Exception as e:
        activity_logger.log_event("Drafting", "ERROR", request.charging_party, f"Drafting Error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

    # --- STEP 4: DOCX (Simplified for stability) ---
    try:
        cp = structured_data.get('charging_party', request.charging_party)
        resp = structured_data.get('respondent', request.respondent)
        doc = Document()
        
        # Cover and Caption (Logic from previous stable version)
        doc.add_paragraph(f"POSITION STATEMENT\n{cp} v. {resp}\nGenerated: {time.strftime('%Y-%m-%d')}")
        doc.add_page_break()

        for roman, title, key in [("I.", "INTRODUCTION", "introduction"), ("II.", "BACKGROUND", "background"), ("III.", "ALLEGATIONS", "allegations"), ("IV.", "ANALYSIS", "analysis"), ("V.", "DEFENSES", "defenses"), ("VI.", "CONCLUSION", "conclusion")]:
            content = draft_data.get(key, "")
            if content:
                h = doc.add_paragraph(); h.alignment = WD_ALIGN_PARAGRAPH.CENTER
                r = h.add_run(f"{roman}\n{title}"); r.bold = True; r.font.size = Pt(12)
                doc.add_paragraph(content)

        file_path = Path(request.folder_path) / f"Draft_{cp.replace(' ', '_')}_{int(time.time())}.docx"
        doc.save(str(file_path))
        activity_logger.log_event("Drafting", "SUCCESS", cp, f"Draft saved: {file_path}")
        return {"status": "success", "file_path": str(file_path.absolute()), "citations": total_citations}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Word Error: {str(e)}")
