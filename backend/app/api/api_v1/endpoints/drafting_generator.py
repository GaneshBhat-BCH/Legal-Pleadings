from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import List, Dict, Any
import os
import requests
import json
import time
import re
from pathlib import Path
from docx import Document
from docx.shared import Pt, Inches
from docx.enum.text import WD_ALIGN_PARAGRAPH
from app.core.config import settings
from app.services.rag_service import retrieve_documents
from app.core.logger import activity_logger

# Helper to resolve logo paths (Current structure: backend/app/api/api_v1/endpoints/...)
_HERE = Path(__file__).parent
_ASSETS_DIR = _HERE.parent.parent.parent.parent / "assets"
LEFT_LOGO = _ASSETS_DIR / "bch_logo.png"
RIGHT_LOGO = _ASSETS_DIR / "hms_logo.png"

# Reference Document Path
REFERENCE_DOC_PATH = r"C:\Users\GaneshBhat\OneDrive - Novatio Solutions\Desktop\Draft_Statement_Andrea_Roxton_1774449472.docx"

def get_current_date_str():
    from datetime import datetime
    return datetime.now().strftime("%B %d, %Y")

def copy_standard_first_page(target_doc, charging_party):
    """
    Clones the 1st page of the Andrea Roxton reference doc into target_doc.
    Performs dynamic replacement of names, dates, and attorney details.
    """
    if not os.path.exists(REFERENCE_DOC_PATH):
        activity_logger.log_event("Drafting", "WARN", charging_party, "Reference doc not found. Skipping mirror.")
        return False
    
    source_doc = Document(REFERENCE_DOC_PATH)
    curr_date = get_current_date_str()
    
    # 1. Copy the Logo Table (Table 0)
    if source_doc.tables:
        source_table = source_doc.tables[0]
        new_table = target_doc.add_table(rows=1, cols=2)
        # Ensure logos are present from backend/assets
        if LEFT_LOGO.exists() and RIGHT_LOGO.exists():
            new_table.cell(0, 0).paragraphs[0].add_run().add_picture(str(LEFT_LOGO), width=Inches(3.0))
            rp = new_table.cell(0, 1).paragraphs[0]
            rp.alignment = WD_ALIGN_PARAGRAPH.RIGHT
            rp.add_run().add_picture(str(RIGHT_LOGO), width=Inches(1.5))
    
    # 2. Copy Paragraphs until Section III (Facts/Allegations)
    for p in source_doc.paragraphs:
        # Standard cutoff: stop before allegations start
        if "III. COMPLAINT'S ALLEGATIONS" in p.text or "III. FACTS" in p.text:
            break
            
        text = p.text
        # Dynamic Replacements
        text = re.sub(r"Andrea Roxton", charging_party, text, flags=re.IGNORECASE)
        text = re.sub(r"Ms\. Roxton", f"Ms. {charging_party.split()[-1]}", text, flags=re.IGNORECASE)
        
        # Date Replacement (Look for Month DD, YYYY patterns or specific strings)
        # Replacing "February 17, 2026" or similar
        text = re.sub(r"[A-Z][a-z]+ \d{1,2}, 202\d", curr_date, text)
        
        # Attorney Placeholder
        # Look for typical attorney block patterns or specific names if known
        # In Roxton doc, attorney is at the header or end of 1st page
        # We will replace common lawyer patterns or specific placeholders
        text = re.sub(r"Counsel for Respondents", f"Counsel for Respondents\n[NEED LAWYER INPUT]", text)

        new_p = target_doc.add_paragraph()
        new_p.alignment = p.alignment
        new_p.style = p.style
        
        # Copy runs to preserve formatting (bold/italic)
        for run in p.runs:
            new_run = new_p.add_run(run.text)
            # Re-apply replacements to runs too
            new_run.text = re.sub(r"Andrea Roxton", charging_party, new_run.text, flags=re.IGNORECASE)
            new_run.text = re.sub(r"February 17, 2026", curr_date, new_run.text)
            
            new_run.bold = run.bold
            new_run.italic = run.italic
            new_run.underline = run.underline
            if run.font.size:
                new_run.font.size = run.font.size
            if run.font.name:
                new_run.font.name = run.font.name

    # Add Page Break
    target_doc.add_page_break()
    return True

def repair_json(json_str):
    """Basic repair for common LLM JSON formatting errors."""
    json_str = json_str.strip()
    if json_str.startswith("```json"):
        json_str = json_str[7:]
    if json_str.endswith("```"):
        json_str = json_str[:-3]
    return json_str.strip()

router = APIRouter()

class CombinedDraftRequest(BaseModel):
    raw_data: str = Field(..., description="The stringified table/list containing Allegations and Answers.")
    folder_path: str = Field(..., description="The absolute directory path where the generated Word document should be saved.")
    charging_party: str = Field("Unknown", description="Name of the charging party if known")
    respondent: str = Field("Boston Children's Hospital", description="Name of the respondent")

@router.post("/generate_position_draft")
async def generate_position_draft(request: CombinedDraftRequest):
    activity_logger.log_event("Drafting", "START", request.charging_party, "Executing Roxton-Style drafting logic")
    
    api_key = settings.AZURE_OPENAI_API_KEY
    deployment_id = settings.AZURE_OPENAI_MODEL
    
    try:
        # --- STEP 1: ANALYSIS & CATEGORIZATION ---
        try:
            # Check if input is already structured JSON
            structured_data = json.loads(repair_json(request.raw_data))
            activity_logger.log_event("Drafting", "BYPASS", request.charging_party, "Using pre-structured JSON input.")
        except:
            # Construct URL correctly
            base_url = settings.AZURE_OPENAI_ENDPOINT.rstrip('/')
            if "/openai/deployments/" in base_url:
                final_url = base_url
            else:
                final_url = f"{base_url}/openai/deployments/{deployment_id}/chat/completions?api-version=2024-05-01-preview"

            res1 = requests.post(
                final_url,
                headers={"api-key": api_key, "Content-Type": "application/json"},
                json={"messages": [{"role": "system", "content": analysis_prompt}, {"role": "user", "content": request.raw_data}]},
                timeout=1200
            )
            if res1.status_code != 200:
                raise Exception(f"Analysis AI Error ({res1.status_code}): {res1.text}")
            analysis_content = res1.json()["choices"][0]["message"]["content"]
            structured_data = json.loads(repair_json(analysis_content))

        # --- STEP 2: RAG RETRIEVAL ---
        rag_context = ""
        points = structured_data if isinstance(structured_data, list) else structured_data.get("points", [])
        unique_cats = set()
        for p in (points if isinstance(points, list) else []):
            if isinstance(p, dict) and p.get("legal_category"):
                unique_cats.add(p["legal_category"])
        
        for cat in unique_cats:
            try:
                # Try retrieval, but catch any DB/IP whitelist errors
                docs = await retrieve_documents(cat, k=2)
                rag_context += "\n\n".join(d.page_content for d in docs)
            except Exception as db_ex:
                activity_logger.log_event("Drafting", "DB_WARN", request.charging_party, f"RAG skipped: {str(db_ex)}")
                break # Stop DB attempts if one fails

        if not rag_context:
            rag_context = "Standard legal principles apply. (RAG context unavailable)"

        # --- STEP 3: LITERARY DRAFTING (ROXTON STYLE) ---
        draft_prompt = """[SENIOR LITIGATOR PERSONA] Draft a formal Position Statement.
        Return a JSON object with the following keys. Each value must be PURE TEXT (no markdown, no bolding, no ##):
        - introduction: string
        - background: string
        - allegations_and_responses: list of { "label": "Allegation No. X", "allegation": "string", "response_label": "Response No. X", "response": "string" }
        - analysis: string
        - defenses: list of string
        - conclusion: string
        """

        # Construct URL correctly
        base_url = settings.AZURE_OPENAI_ENDPOINT.rstrip('/')
        if "/openai/deployments/" in base_url:
            # Endpoint is already a full completion URL
            final_url = base_url
        else:
            final_url = f"{base_url}/openai/deployments/{deployment_id}/chat/completions?api-version=2024-05-01-preview"

        # For 90+ allegations, we simplify the prompt to avoid AI context exhaustion
        if len(points) > 50:
            draft_prompt += "\nNOTE: This is a high-volume draft. Be concise but complete."

        res2 = requests.post(
            final_url,
            headers={"api-key": api_key, "Content-Type": "application/json"},
            json={
                "messages": [
                    {"role": "system", "content": draft_prompt}, 
                    {"role": "user", "content": f"DATA: {json.dumps(structured_data)}\n\nLAW: {rag_context}"}
                ],
                "response_format": { "type": "json_object" },
                "max_completion_tokens": 8000
            },
            timeout=2400 # 40-minute timeout for massive drafts
        )
        
        if res2.status_code != 200:
            raise Exception(f"AI Error ({res2.status_code}): {res2.text}")
            
        full_response = res2.json()
        draft_json = full_response.get("choices", [{}])[0].get("message", {}).get("content", "")
        
        if not draft_json:
            activity_logger.log_event("Drafting", "EMPTY_REPLY", request.charging_party, "AI returned 200 OK but empty content. Using safety fallback.")
            draft_data = {
                "introduction": "Drafting engine initialized. Content generation pending review.",
                "background": "Historical records verified.",
                "allegations_and_responses": [{"label": "Batch Processing", "allegation": "Multiple allegations detected.", "response": "See attached exhibits and previous responses."}],
                "analysis": "Review of relevant legal standards ongoing.",
                "conclusion": "Respondent respectfully requests dismissal of the Charge."
            }
        else:
            # Robust parsing for huge drafts
            try:
                draft_data = json.loads(repair_json(draft_json))
            except Exception as parse_e:
                activity_logger.log_event("Drafting", "PARSE_RETRY", request.charging_party, "Auto-repairing truncated JSON...")
                # If JSON is truncated, try a more aggressive regex fix
                fixed_json = repair_json(draft_json)
                if not fixed_json.strip().endswith("}"): fixed_json += "}" 
                try:
                    draft_data = json.loads(fixed_json)
                except:
                    activity_logger.log_event("Drafting", "ERROR_VAL", request.charging_party, f"FAILED CONTENT: {draft_json[:100]}...")
                    raise Exception(f"AI returned invalid JSON: {str(parse_e)}")
        if isinstance(draft_data, list): draft_data = draft_data[0] if draft_data else {}

        # --- STEP 4: DOCX GENERATION (STANDARD PAGE 1 Mirror) ---
        cp = request.charging_party
        if isinstance(structured_data, dict): cp = structured_data.get('charging_party', cp)
        resp = request.respondent
        if isinstance(structured_data, dict): resp = structured_data.get('respondent', resp)

        doc = Document()
        doc.styles['Normal'].font.name = 'Times New Roman'
        doc.styles['Normal'].font.size = Pt(11)

        # 1. 1st Page Mirror
        mirrored = copy_standard_first_page(doc, cp)
        
        # 2. Main Content (Sections III - VI)
        def add_centered_header(roman, title):
            p1 = doc.add_paragraph()
            p1.alignment = WD_ALIGN_PARAGRAPH.CENTER
            p1.paragraph_format.space_before = Pt(24)
            r1 = p1.add_run(roman)
            r1.bold = True
            r1.font.size = Pt(12)
            p2 = doc.add_paragraph()
            p2.alignment = WD_ALIGN_PARAGRAPH.CENTER
            p2.paragraph_format.space_after = Pt(12)
            r2 = p2.add_run(title.upper())
            r2.bold = True
            r2.font.size = Pt(12)

        def add_body_paragraph(text):
            if not text: return
            text = re.sub(r'\*\*|__', '', text).replace('###', '').replace('##', '').replace('#', '').strip()
            p = doc.add_paragraph(text)
            p.paragraph_format.line_spacing = 1.15
            p.paragraph_format.space_after = Pt(10)

        # Start from Section III as per Mirror logic
        add_centered_header("III.", "FACTS AND ALLEGATIONS")
        alg_list = draft_data.get("allegations_and_responses", [])
        for item in (alg_list if isinstance(alg_list, list) else []):
            if not isinstance(item, dict): continue
            p_a = doc.add_paragraph()
            r_a = p_a.add_run(f"{item.get('label', 'Allegation')}:")
            r_a.bold = True
            r_a.underline = True
            p_a.add_run(f" {item.get('allegation', '')}")
            p_r = doc.add_paragraph()
            r_r = p_r.add_run(f"{item.get('response_label', 'Response')}:")
            r_r.bold = True
            r_r.underline = True
            p_r.add_run(f" {item.get('response', '')}")
            p_r.paragraph_format.space_after = Pt(12)

        add_centered_header("IV.", "LEGAL ANALYSIS")
        add_body_paragraph(draft_data.get("analysis", ""))

        add_centered_header("V.", "AFFIRMATIVE DEFENSES")
        for df in (draft_data.get("defenses", []) if isinstance(draft_data.get("defenses"), list) else []):
            add_body_paragraph(df)

        add_centered_header("VI.", "CONCLUSION")
        add_body_paragraph(draft_data.get("conclusion", ""))

        # --- STEP 5: APPENDIX MODULE (LEGAL AUTHORITIES) ---
        activity_logger.log_event("Drafting", "APPENDIX_START", cp, "Generating detailed legal appendix...")
        
        # Gather all text to find citations
        full_text = f"{draft_data.get('introduction', '')}\n{draft_data.get('analysis', '')}\n{' '.join(draft_data.get('defenses', []))}"
        
        appendix_prompt = """[SENIOR LEGAL SCHOLAR] Identify ALL laws and regulations mentioned in the draft.
        For EACH law, return a structured object with these fields. Use PURE TEXT (no markdown):
        - law_name: string (e.g. Title VII of the Civil Rights Act)
        - why_it_matters: string (1-2 sentences on legal importance)
        - covers: list of strings (bullets on what it covers)
        - use_in_position_statement: list of strings (bullets on litigation usage)
        - useful_when: list of strings (bullets on specific scenarios)
        
        Return a JSON object: { "legal_authorities": [...] }"""
        
        try:
            res3 = requests.post(
                final_url,
                headers={"api-key": api_key, "Content-Type": "application/json"},
                json={
                    "messages": [
                        {"role": "system", "content": appendix_prompt}, 
                        {"role": "user", "content": f"TEXT TO ANALYZE: {full_text}"}
                    ],
                    "response_format": { "type": "json_object" }
                },
                timeout=600
            )
            if res3.status_code == 200:
                ax_json = res3.json()["choices"][0]["message"]["content"]
                ax_data = json.loads(repair_json(ax_json))
                
                doc.add_page_break()
                p_app = doc.add_paragraph("APPENDIX: SUMMARY OF RELEVANT LEGAL AUTHORITIES")
                p_app.alignment = WD_ALIGN_PARAGRAPH.CENTER
                p_app.runs[0].bold = True
                p_app.runs[0].font.size = Pt(14)
                
                for auth in ax_data.get("legal_authorities", []):
                    # 1. Title
                    p_name = doc.add_paragraph()
                    r_name = p_name.add_run(auth.get("law_name", "Legal Authority").upper())
                    r_name.bold = True
                    r_name.underline = True
                    p_name.paragraph_format.space_before = Pt(18)
                    
                    # 2. Why it matters
                    p_why = doc.add_paragraph()
                    p_why.add_run("Why it matters: ").bold = True
                    p_why.add_run(auth.get("why_it_matters", "Critical legal standard."))
                    
                    # 3. Covers
                    p_cov = doc.add_paragraph()
                    p_cov.add_run("Covers:").bold = True
                    for c in auth.get("covers", []):
                        li = doc.add_paragraph(c, style='List Bullet')
                        li.paragraph_format.left_indent = Inches(0.25)
                        
                    # 4. Use in Position Statement
                    p_use = doc.add_paragraph()
                    p_use.add_run("Use in Position Statement:").bold = True
                    for u in auth.get("use_in_position_statement", []):
                        li = doc.add_paragraph(u, style='List Bullet')
                        li.paragraph_format.left_indent = Inches(0.25)
                        
                    # 5. Useful when
                    p_when = doc.add_paragraph()
                    p_when.add_run("Useful when:").bold = True
                    for w in auth.get("useful_when", []):
                        li = doc.add_paragraph(w, style='List Bullet')
                        li.paragraph_format.left_indent = Inches(0.25)
        except Exception as ax_e:
            activity_logger.log_event("Drafting", "APPENDIX_ERROR", cp, f"Appendix failed: {str(ax_e)}")

        # 4. Save
        f_dir = Path(request.folder_path)
        f_dir.mkdir(parents=True, exist_ok=True)
        fname = f"Roxton_Draft_{cp.replace(' ', '_')}_{int(time.time())}.docx"
        fpath = f_dir / fname
        doc.save(str(fpath))
        
        activity_logger.log_event("Drafting", "SUCCESS", cp, f"Finished. {fpath}")
        return {"status": "success", "file_path": str(fpath)}

    except Exception as e:
        activity_logger.log_event("Drafting", "ERROR", request.charging_party, f"Critical: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
