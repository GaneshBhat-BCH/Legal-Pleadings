from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import List, Dict, Any
import os
import requests
import json
import time
from pathlib import Path
from docx import Document
from docx.shared import Pt, Inches
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
from app.core.config import settings
from app.services.rag_service import retrieve_documents
from app.core.logger import activity_logger

# Resolve logo paths relative to this file so they work on any machine
_HERE = Path(__file__).parent
_ASSETS_DIR = _HERE.parent.parent.parent.parent / "assets"
LEFT_LOGO = _ASSETS_DIR / "bch_logo.png"
RIGHT_LOGO = _ASSETS_DIR / "hms_logo.png"

router = APIRouter()

class CombinedDraftRequest(BaseModel):
    raw_data: str = Field(..., description="The combined text containing both the PDF data and the lawyer's unstructured notes.")
    folder_path: str = Field(..., description="The absolute directory path where the generated Word document should be saved.")
    charging_party: str = Field("Unknown", description="Name of the charging party if known")
    respondent: str = Field("Boston Children's Hospital", description="Name of the respondent")

@router.post("/generate_position_draft")
async def generate_position_draft(request: CombinedDraftRequest):
    activity_logger.log_event("Drafting", "START", request.charging_party, "Processing combined text for legal draft")
    
    api_key = settings.AZURE_OPENAI_API_KEY
    endpoint = settings.AZURE_OPENAI_ENDPOINT
    deployment_name = "gpt-5" # Or gpt-4o as per user preference
    
    # --- STEP 1: ANALYSIS & STRUCTURE ---
    # We use the LLM to separate the combined text into structured allegations and relevant responses/facts.
    analysis_prompt = """[SYSTEM ROLE]
You are a Senior Legal Analyst. Your task is to analyze a combined text block containing both "Extracted PDF content" and "Lawyer Notes/Feedback."
You must separate these into a structured list of allegations and the respondent's rebuttal/facts for each.

[MANDATORY: LEGAL CATEGORIZATION]
For every allegation point, you must identify its primary Legal Category. You MUST choose from this exact list:
- Sexual Orientation
- Sex
- Sexual Harassment
- Retaliation
- Religion
- Race
- National Origin
- Disability ADA Failure to Accommodate
- Color
- Age

[OUTPUT FORMAT: JSON]
Return exactly this structure:
{
  "charging_party": "string",
  "respondent": "string",
  "analysis_summary": "Overall summary of the case",
  "points": [
    {
      "allegation": "The specific claim from the PDF text",
      "lawyer_comment": "The response or factual rebuttal found in the lawyer's notes",
      "legal_category": "One of the categories above"
    }
  ]
}
"""
    
    # Call Azure OpenAI Chat Completions using exact endpoint
    if "chat/completions" in settings.AZURE_OPENAI_ENDPOINT:
        chat_url = settings.AZURE_OPENAI_ENDPOINT
    else:
        # Standard base URL logic
        chat_url = f"{settings.AZURE_OPENAI_ENDPOINT.rstrip('/')}/openai/deployments/{deployment_name}/chat/completions?api-version=2024-05-01-preview"
    
    headers = {
        "api-key": api_key,
        "Content-Type": "application/json"
    }
    
    analysis_payload = {
        "messages": [
            {"role": "system", "content": analysis_prompt},
            {"role": "user", "content": f"Analyze this integrated text:\n{request.raw_data}"}
        ]
    }
    
    try:
        # Increased timeout to 1200s (20 minutes) to handle complex combined legal text
        res = requests.post(chat_url, headers=headers, json=analysis_payload, timeout=1200)
        if res.status_code != 200:
            raise Exception(f"Analysis failed: {res.text}")
        
        analysis_content = res.json()["choices"][0]["message"]["content"]
        
        # Robust JSON extraction
        try:
            from json_repair import repair_json
            start_idx = analysis_content.find("{")
            end_idx = analysis_content.rfind("}")
            if start_idx != -1 and end_idx != -1:
                json_str = analysis_content[start_idx:end_idx+1]
                structured_data = json.loads(repair_json(json_str))
            else:
                structured_data = json.loads(repair_json(analysis_content))
        except Exception as parse_err:
             print(f"JSON Parse warning: {parse_err}")
             # Fallback if AI didn't return perfect JSON
             structured_data = {"analysis_summary": analysis_content, "points": []}

    except Exception as e:
        activity_logger.log_event("Drafting", "ERROR", request.charging_party, f"Extraction failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to analyze text: {str(e)}")

    # --- STEP 2: TARGETED RAG RETRIEVAL (PHASE 4.2) ---
    # We perform separate RAG searches for each unique legal category found in the case.
    rag_context_blocks = []
    unique_categories = set()
    for p in structured_data.get("points", []):
        cat = p.get("legal_category", "General Employment Law")
        unique_categories.add(cat)
    
    if not unique_categories:
        unique_categories.add("General Employment Law")

    total_citations = 0
    for category in unique_categories:
        # Build a search query specifically for this category
        cat_points = [p for p in structured_data.get("points", []) if p.get("legal_category") == category]
        cat_search_query = f"{category} discrimination retaliation laws "
        for p in cat_points[:3]: # Use first 3 points of this category for the query
            cat_search_query += f" {p['allegation']}"
        
        try:
            # Retrieve 4 targeted docs per category
            cat_docs = await retrieve_documents(cat_search_query, k=4)
            if cat_docs:
                citations_text = "\n".join([f"- {d.page_content}" for d in cat_docs])
                rag_context_blocks.append(f"[LEGAL CATEGORY: {category.upper()}]\n{citations_text}")
                total_citations += len(cat_docs)
        except Exception as e:
            print(f"Targeted RAG Error for {category}: {e}")

    rag_context = "\n\n".join(rag_context_blocks) if rag_context_blocks else "No direct legal citations found in vector store."

    # --- STEP 3: DRAFTING ---
    # --- STEP 3: DRAFTING (REFINED SENIOR LITIGATOR STYLE) ---
    draft_prompt = """[SYSTEM ROLE: SENIOR LITIGATION COUNSEL]
You are a Senior Litigation Counsel at a top-tier law firm. You will draft a formal, high-quality "Position Statement" that is persuasive, clinical, and sterile.

[LINGUISTIC STYLE: PROFESSIONAL LEGAL REGISTER]
- Use formal legal transitions: "Notwithstanding the foregoing," "Accordingly," "Furthermore," "Respectfully submits," "Pursuant to."
- Maintain a clinical and objective tone, especially when describing sensitive or disputed facts.
- Avoid colloquialisms, contractions, and emotional language.
- Phrasing should be assertive but professional (e.g., "Respondent unequivocally denies these factual assertions").

[STRICT LEGAL MAPPING & HYBRID STRATEGY]
- YOU MUST APPLY THE CORRECT LAW TO THE CORRECT ISSUE.
- SUPPLEMENTARY LAW: If you identify relevant Federal or State laws (e.g., specific Massachusetts G.L. chapters) that are NOT in the [RELEVANT LEGAL CITATIONS] provided but are essential to a robust defense, you MUST incorporate them using your internal training.
- Clearly differentiate between RAG-provided authorities and supplemented authorities.

[OUTPUT FORMAT: JSON]
You MUST return your entire response as a structured JSON object exactly as follows:
{
  "introduction": "I. INTRODUCTION. Parties and high-level defense.",
  "background": "II. BACKGROUND. Factual history from lawyer notes.",
  "allegations": "III. COMPLAINT'S ALLEGATIONS. Point-for-point response with 12pt vertical spacing logic.",
  "analysis": "IV. ANALYSIS. Legal argument interweaving RAG and supplemental internal knowledge citations.",
  "legal_appendix": [
    {
      "citation": "Proper Bluebook Citation",
      "full_text": "Complete statutory or case text for reference"
    }
  ]
}

[INSTRUCTIONS]
- Draft professionally and persuasively.
- Do not use markdown tags in the text fields.
- Ensure the 'analysis' section uses proper Bluebook style.
- The 'legal_appendix' must contain the full reference text for EVERY law cited in the Analysis."""

    draft_user_input = f"""
[CASE DETAILS]
Charging Party: {structured_data.get('charging_party', request.charging_party)}
Respondent: {structured_data.get('respondent', request.respondent)}
Summary: {structured_data.get('analysis_summary')}

[ALLEGATIONS AND RESPONSES]
"""
    for i, p in enumerate(structured_data.get("points", []), 1):
        draft_user_input += f"\nPoint {i} [Category: {p.get('legal_category')}]:\nAllegation: {p['allegation']}\nRespondent's Facts: {p['lawyer_comment']}\n"

    draft_user_input += f"\n[RELEVANT LEGAL CITATIONS BY CATEGORY]\n{rag_context}"

    # Drafting Payload
    if "chat/completions" in settings.AZURE_OPENAI_ENDPOINT:
        chat_url = settings.AZURE_OPENAI_ENDPOINT
    else:
        chat_url = f"{settings.AZURE_OPENAI_ENDPOINT.rstrip('/')}/openai/deployments/{deployment_name}/chat/completions?api-version=2024-05-01-preview"

    draft_payload = {
        "messages": [
            {"role": "system", "content": draft_prompt},
            {"role": "user", "content": draft_user_input}
        ]
    }

    try:
        # Increased timeout to 1200s (20 minutes) for the full drafting synthesis
        res = requests.post(chat_url, headers=headers, json=draft_payload, timeout=1200)
        if res.status_code != 200:
            raise Exception(f"Drafting failed: {res.text}")
        
        draft_content = res.json()["choices"][0]["message"]["content"]
        
        # Robust JSON extraction for the drafted sections
        try:
            from json_repair import repair_json
            start_idx = draft_content.find("{")
            end_idx = draft_content.rfind("}")
            if start_idx != -1 and end_idx != -1:
                json_str = draft_content[start_idx:end_idx+1]
                draft_data = json.loads(repair_json(json_str))
            else:
                draft_data = json.loads(repair_json(draft_content))
            
            # Ensure legal_appendix exists
            if "legal_appendix" not in draft_data:
                draft_data["legal_appendix"] = []
                
        except Exception as parse_err:
            print(f"Draft JSON Parse warning: {parse_err}")
            draft_data = {
                "introduction": "Parsing Error. Raw content below:\n" + draft_content,
                "background": "", "allegations": "", "analysis": "", "legal_appendix": []
            }

    except Exception as e:
        activity_logger.log_event("Drafting", "ERROR", request.charging_party, f"Draft generation failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to generate draft: {str(e)}")

    # --- STEP 4: DOCX GENERATION ---
    try:
        cp = structured_data.get('charging_party', request.charging_party)
        resp = structured_data.get('respondent', request.respondent)

        doc = Document()
        
        # Page 1: Logos (Borderless Table)
        if LEFT_LOGO.exists() and RIGHT_LOGO.exists():
            logo_table = doc.add_table(rows=1, cols=2)
            logo_table.allow_autofit = True
            
            # Left cell (BCH logo)
            left_cell = logo_table.cell(0, 0)
            left_pr = left_cell.paragraphs[0]
            left_pr.alignment = WD_ALIGN_PARAGRAPH.LEFT
            left_r = left_pr.add_run()
            left_r.add_picture(str(LEFT_LOGO), width=Inches(3.0))
            
            # Right cell (HMS logo)
            right_cell = logo_table.cell(0, 1)
            right_pr = right_cell.paragraphs[0]
            right_pr.alignment = WD_ALIGN_PARAGRAPH.RIGHT
            right_r = right_pr.add_run()
            right_r.add_picture(str(RIGHT_LOGO), width=Inches(1.5))

        # Page 1: Cover Letter
        doc.add_paragraph("Office of General Counsel\n300 Longwood Avenue, BCH3046\nBoston, Massachusetts 02115\n617-355-6800")
        doc.add_paragraph(f"{time.strftime('%B %d, %Y')}\n\nVIA EMAIL\n")
        doc.add_paragraph("[NEED LAWYER INPUT: Investigator Name]\n[NEED LAWYER INPUT: Investigator Email]\n[NEED LAWYER INPUT: Admin Assistant Name]\nMassachusetts Commission Against Discrimination\n1 Ashburton Place\nBoston, MA 02108\nbospositionstmts@mass.gov\n")
        
        re_para = doc.add_paragraph(f"Re:\t{cp} v. {resp}\n\t[NEED LAWYER INPUT: MCAD No.]\n\t[NEED LAWYER INPUT: EEOC No.]\n")
        
        doc.add_paragraph("Dear Investigator and Administrative Assistant:\n\nI hope this letter finds you well. In connection with the above-entitled matter, enclosed please find the following pleading:\n\n•\tPosition Statement of Respondent, Boston Children's Hospital.\n\nPlease feel free to contact me should you have any questions regarding the enclosed. Thank you.\n\nSincerely,\n\n\n\n[NEED LAWYER INPUT: Attorney Name]\n[NEED LAWYER INPUT: Attorney Title]\n\ncc: [NEED LAWYER INPUT: Charging Party Name/Counsel]")

        doc.add_page_break()

        # Page 2: Formal Caption
        caption = doc.add_paragraph()
        caption.alignment = WD_ALIGN_PARAGRAPH.CENTER
        caption.add_run("COMMONWEALTH OF MASSACHUSETTS").bold = True
        
        table = doc.add_table(rows=1, cols=3)
        row_cells = table.rows[0].cells
        row_cells[0].text = f"\n{cp.upper()},\n\nComplainant\n\n\tv.\n\n{resp.upper()},\n\nRespondent"
        row_cells[1].text = ")\n)\n)\n)\n)\n)\n)\n)\n)\n)"
        row_cells[2].text = "\n\n\n[NEED LAWYER INPUT: MCAD No.]\n[NEED LAWYER INPUT: EEOC No.]"
        
        title = doc.add_paragraph("\nPOSITION STATEMENT OF RESPONDENT\nBOSTON CHILDREN'S HOSPITAL\n")
        title.alignment = WD_ALIGN_PARAGRAPH.CENTER
        title.runs[0].bold = True

        # Render AI Sections
        sections = [
            ("I.", "INTRODUCTION", draft_data.get("introduction", "")),
            ("II.", "BACKGROUND", draft_data.get("background", "")),
            ("III.", "COMPLAINT'S ALLEGATIONS", draft_data.get("allegations", "")),
            ("IV.", "ANALYSIS", draft_data.get("analysis", ""))
        ]
        
        for roman, title, content in sections:
            h = doc.add_paragraph()
            h.alignment = WD_ALIGN_PARAGRAPH.CENTER
            h_format = h.paragraph_format
            h_format.space_before = Pt(18)
            h_format.space_after = Pt(12)
            
            r1 = h.add_run(roman)
            r1.bold = True
            r1.font.size = Pt(12)
            h.add_run("\n")
            r2 = h.add_run(title)
            r2.bold = True
            r2.font.size = Pt(12)
            
            if content:
                for block in content.split("\n\n"):
                    block = block.strip()
                    if not block:
                        continue
                    p = doc.add_paragraph()
                    p_format = p.paragraph_format
                    p_format.space_after = Pt(12) # Premium vertical spacing
                    p_format.line_spacing = 1.15
                    
                    lines = block.split("\n")
                    for i, line in enumerate(lines):
                        p.add_run(line)
                        if i < len(lines) - 1:
                            p.add_run().add_break()

        # Page 3+: Legal Appendix
        appendix_data = draft_data.get("legal_appendix", [])
        if appendix_data:
            doc.add_page_break()
            app_h = doc.add_paragraph()
            app_h.alignment = WD_ALIGN_PARAGRAPH.CENTER
            app_run = app_h.add_run("LEGAL APPENDIX: TABLE OF AUTHORITIES")
            app_run.bold = True
            app_run.font.size = Pt(14)
            
            for item in appendix_data:
                cit = item.get("citation", "Unknown Citation")
                text = item.get("full_text", "No text provided.")
                
                # Citation Header
                cit_p = doc.add_paragraph()
                cit_run = cit_p.add_run(cit)
                cit_run.bold = True
                cit_run.italic = True
                cit_p.paragraph_format.space_before = Pt(12)
                
                # Statutory Text
                text_p = doc.add_paragraph(text)
                text_p.paragraph_format.left_indent = Inches(0.5)
                text_p.paragraph_format.space_after = Pt(6)
                text_p.style = doc.styles['Normal']
                for run in text_p.runs:
                    run.font.size = Pt(10) # Smaller font for appendix text

        target_folder = Path(request.folder_path)
        if not target_folder.exists():
            target_folder.mkdir(parents=True, exist_ok=True)
            
        file_name = f"Draft_Statement_{cp.replace(' ', '_')}_{int(time.time())}.docx"
        file_path = target_folder / file_name
        
        doc.save(str(file_path))
        activity_logger.log_event("Drafting", "SUCCESS", cp, f"Generated draft saved to {file_path}")
        
        return {
            "status": "success",
            "charging_party": cp,
            "respondent": resp,
            "file_path": str(file_path.absolute()),
            "citations_used": total_citations if 'total_citations' in locals() else 0
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create Word file: {str(e)}")
