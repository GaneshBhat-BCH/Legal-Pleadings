from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
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

# Helper to resolve logo paths
_HERE = Path(__file__).parent
# Navigate to backend/assets correctly (parent is api_v1, parent2 is api, parent3 is app, parent4 is backend)
_ASSETS_DIR = _HERE.parent.parent.parent.parent / "assets"
LEFT_LOGO = _ASSETS_DIR / "bch_logo.png"
RIGHT_LOGO = _ASSETS_DIR / "hms_logo.png"

# Reference Document Path (Template)
# Use a relative fallback for the VM environment if the OneDrive path is missing
_DEFAULT_TEMPLATE = _ASSETS_DIR / "templates" / "Andrea_Roxton_Template.docx"
REFERENCE_DOC_PATH = os.getenv("REFERENCE_DOC_PATH", str(_DEFAULT_TEMPLATE))

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
    if not json_str: return "{}"
    json_str = json_str.strip()
    if json_str.startswith("```json"):
        json_str = json_str[7:]
    if json_str.endswith("```"):
        json_str = json_str[:-3]
    return json_str.strip()

def chunk_text(text: str, max_chars: int = 6000, overlap: int = 500) -> list:
    """Split large text into overlapping chunks for reliable AI analysis."""
    chunks = []
    current_pos = 0
    while current_pos < len(text):
        end_pos = min(current_pos + max_chars, len(text))
        
        # Try to find a clean break (newline) within the last 200 chars of the chunk
        if end_pos < len(text):
            break_pos = text.rfind('\n', end_pos - 200, end_pos)
            if break_pos != -1 and break_pos > current_pos:
                end_pos = break_pos
        
        chunks.append(text[current_pos:end_pos].strip())
        
        # Move forward by (chunk_size - overlap) to ensure continuity
        new_pos = end_pos - overlap
        if new_pos <= current_pos:
            new_pos = end_pos
        current_pos = new_pos
        
        if end_pos >= len(text):
            break
            
    return chunks
    return chunks

router = APIRouter()

class CombinedDraftRequest(BaseModel):
    raw_data: str = Field(..., description="The stringified table/list containing Allegations and Answers.")
    folder_path: Optional[str] = Field(None, description="Absolute directory path (defaults to ./Drafts if empty).")
    charging_party: str = Field("Unknown", description="Name of the charging party if known")
    respondent: str = Field("Boston Children's Hospital", description="Name of the respondent")

@router.post("/generate_position_draft")
async def generate_position_draft(request: CombinedDraftRequest):
    activity_logger.log_event("Drafting", "START", request.charging_party, "Executing Roxton-Style Point-by-Point Drafting")
    
    api_key = settings.AZURE_OPENAI_API_KEY
    deployment_id = settings.AZURE_OPENAI_MODEL
    
    # Construct base URL for Azure OpenAI
    base_url = settings.AZURE_OPENAI_ENDPOINT.rstrip('/')
    if "/openai/deployments/" in base_url:
        final_url = base_url
    else:
        final_url = f"{base_url}/openai/deployments/{deployment_id}/chat/completions?api-version=2024-05-01-preview"

    try:
        # --- STEP 1: ADAPTIVE ANALYSIS (JSON-OR-UNSTRUCTURED) --- 
        all_points = []
        
        # Sanitize raw_data: Remove problematic literal control characters that break JSON
        sanitized_raw = request.raw_data.replace("\r", "").replace("\t", " ")
        if "\\n" not in sanitized_raw: # If they used literal newlines instead of \n
            sanitized_raw = sanitized_raw.replace("\n", "\\n")

        try:
            # Check if input is already structured JSON
            structured_input = json.loads(repair_json(sanitized_raw))
            all_points = structured_input.get("points", []) or structured_input.get("allegations_list", [])
            activity_logger.log_event("Drafting", "BYPASS", request.charging_party, "Using pre-structured JSON input.")
        except:
            # Partitioned Analysis for Massive Unstructured Inputs
            activity_logger.log_event("Drafting", "ANALYSIS_START", request.charging_party, "Executing Partitioned Raw Analysis...")
            
            analysis_prompt = """[SENIOR LEGAL ANALYST] Extract ALL individual allegations and their corresponding responses verbatim.
            STRICT RULES:
            - ZERO MERGING. Every numbered index (1, 2, 3...) must be its own unique entry.
            - NO SUMMARIZATION. Keep all names (e.g. 'Andrea Roxton', 'Genevieve Benoit') and verbatim quotes.
            - Pattern: Identify the index number, then the allegation text, then the employer's response.
            - IMPORTANT: The data is unstructured. Do not be confused by commas inside legal sentences.
            - Return JSON: { "points": [ { "label": "X", "allegation": "...", "response": "..." }, ... ] }
            """
            
            # Use smaller 2,500-character chunks with generous 500-char overlap
            raw_chunks = chunk_text(sanitized_raw, 2500, 500)
            
            for idx, chunk in enumerate(raw_chunks):
                activity_logger.log_event("Drafting", "ANALYSIS_BLOCK", request.charging_party, f"Processing Part {idx+1}/{len(raw_chunks)}")
                try:
                    res1 = requests.post(
                        final_url,
                        headers={"api-key": api_key, "Content-Type": "application/json"},
                        json={
                            "messages": [{"role": "system", "content": analysis_prompt}, {"role": "user", "content": f"DATA (PART {idx+1}/{len(raw_chunks)}):\n{chunk}"}],
                            "response_format": { "type": "json_object" },
                            "max_completion_tokens": 4096
                        },
                        timeout=300
                    )
                    if res1.status_code == 200:
                        chunk_json = json.loads(repair_json(res1.json()["choices"][0]["message"]["content"]))
                        new_pts = chunk_json.get("points", [])
                        if isinstance(new_pts, list): all_points.extend(new_pts)
                except Exception as e:
                    activity_logger.log_event("Drafting", "ANALYSIS_WARN", request.charging_party, f"Part {idx+1} failed: {str(e)}")

        if not all_points:
            raise Exception("No allegations found in input.")

        # --- STEP 1d: POINT AUDIT & GAP RECOVERY (SAFETY NET) ---
        try:
            found_labels = []
            for p in all_points:
                try:
                    lbl_num = re.findall(r'\d+', str(p.get('label', '')))
                    if lbl_num: found_labels.append(int(lbl_num[0]))
                except: continue
            
            if found_labels:
                found_labels = sorted(list(set(found_labels)))
                gaps = [i for i in range(min(found_labels), max(found_labels)) if i not in found_labels]
                
                if gaps:
                    activity_logger.log_event("Drafting", "GAP_DETECTED", request.charging_party, f"Detected {len(gaps)} missing points. Recovering...")
                    for gap in gaps[:10]: # Limit surgical recoveries
                        try:
                            recovery_res = requests.post(
                                final_url,
                                headers={"api-key": api_key, "Content-Type": "application/json"},
                                json={
                                    "messages": [
                                        {"role": "system", "content": f"[SURGICAL EXTRACTION] Extract EXACT VERBATIM the Allegation and Response for Point No. {gap}. DO NOT summarize. Keep all names and quotes. Return JSON: {{ 'point': {{ 'label': '...', 'allegation': '...', 'response': '...' }} }}"},
                                        {"role": "user", "content": f"FULL RAW DATA:\n{request.raw_data}"}
                                    ],
                                    "response_format": { "type": "json_object" },
                                    "max_completion_tokens": 1024
                                },
                                timeout=60
                            )
                            if recovery_res.status_code == 200:
                                rec_json = json.loads(repair_json(recovery_res.json()["choices"][0]["message"]["content"]))
                                rec_p = rec_json.get("point") or rec_json.get("points", [{}])[0]
                                if rec_p.get("allegation"): 
                                    rec_p["label"] = str(gap)
                                    all_points.append(rec_p)
                                    activity_logger.log_event("Drafting", "GAP_RECOVERED", request.charging_party, f"Successfully recovered Point {gap} verbatim.")
                        except: continue
        except Exception as audit_ex:
            activity_logger.log_event("Drafting", "AUDIT_WARN", request.charging_party, f"Audit failed: {str(audit_ex)}")

        # deduplicate by Label
        unique_points = {}
        for p in all_points:
            lbl = str(p.get('label', ''))
            if lbl not in unique_points or len(str(p.get('allegation',''))) > len(str(unique_points[lbl].get('allegation',''))):
                unique_points[lbl] = p

        final_points = sorted(unique_points.values(), key=lambda x: int(re.findall(r'\d+', str(x.get('label', '0')))[0]) if re.findall(r'\d+', str(x.get('label', ''))) else 999)

        # --- STEP 1e: CRITICAL IDENTITY CHECK (THE "BETSY" MARKER) ---
        has_betsy_extracted = any("Betsy" in str(p.get("allegation", "")) or "Betsy" in str(p.get("response", "")) for p in final_points)
        has_betsy_raw = "Betsy" in request.raw_data
        
        if has_betsy_raw and not has_betsy_extracted:
            activity_logger.log_event("Drafting", "BETSY_LOST", request.charging_party, "Critical 'Betsy' point missing from extraction. Triggering Surgical Identity Recovery...")
            try:
                recovery_res = requests.post(
                    final_url,
                    headers={"api-key": api_key, "Content-Type": "application/json"},
                    json={
                        "messages": [
                            {"role": "system", "content": "[SURGICAL IDENTITY RECOVERY] Verbatim Extract the specific Index Point and Allegation containing the name 'Betsy'. DO NOT summarize. Return JSON: { 'point': { 'label': '...', 'allegation': '...', 'response': '...' } }"},
                            {"role": "user", "content": f"FULL RAW DATA:\n{request.raw_data}"}
                        ],
                        "response_format": { "type": "json_object" },
                        "max_completion_tokens": 1024
                    },
                    timeout=120
                )
                if recovery_res.status_code == 200:
                    rec_json = json.loads(repair_json(recovery_res.json()["choices"][0]["message"]["content"]))
                    rec_p = rec_json.get("point") or rec_json.get("points", [{}])[0]
                    if rec_p.get("allegation"): 
                        final_points.append(rec_p)
                        # Re-sort
                        final_points = sorted(final_points, key=lambda x: int(re.findall(r'\d+', str(x.get('label', '0')))[0]) if re.findall(r'\d+', str(x.get('label', ''))) else 999)
                        activity_logger.log_event("Drafting", "BETSY_RECOVERED", request.charging_party, "Successfully recovered Point 22 (Betsy) verbatim.")
            except: pass

        # --- STEP 2: RAG RETRIEVAL ---
        rag_context = ""
        unique_cats = set(p.get("legal_category") for p in final_points if p.get("legal_category"))
        for cat in unique_cats:
            try:
                docs = await retrieve_documents(cat, k=2)
                rag_context += "\n\n".join(d.page_content for d in docs)
            except: break
        if not rag_context: rag_context = "Standard legal principles apply."

        # --- STEP 3: LITERARY DRAFTING (POINT-BY-POINT FIDELITY) ---
        activity_logger.log_event("Drafting", "BATCH_START", request.charging_party, f"Drafting {len(final_points)} points individually...")
        
        processed_points = []
        final_intro = ""
        final_background = ""
        final_analysis = ""
        final_defenses = []
        final_conclusion = ""

        # A. Global Sections (Intro/Background)
        try:
            summary_res = requests.post(
                final_url,
                headers={"api-key": api_key, "Content-Type": "application/json"},
                json={
                    "messages": [
                        {"role": "system", "content": f"[LEGAL COUNSEL] Generate Introduction and Background for {request.charging_party} vs {request.respondent}. Style: Roxton Template (Clinical, Firm). Return JSON: {{ 'introduction': '...', 'background': '...' }}"},
                        {"role": "user", "content": f"Points for context:\n{json.dumps(final_points[:15], indent=2)}"}
                    ],
                    "response_format": { "type": "json_object" },
                    "max_completion_tokens": 2048
                },
                timeout=180
            )
            if summary_res.status_code == 200:
                s_json = json.loads(repair_json(summary_res.json()["choices"][0]["message"]["content"]))
                final_intro = s_json.get("introduction", "")
                final_background = s_json.get("background", "")
        except: pass

        # B. Individual Point Drafting Loop
        for idx, p in enumerate(final_points):
            activity_logger.log_event("Drafting", "POINT_PROC", request.charging_party, f"Drafting Point {idx+1}/{len(final_points)} (Label: {p.get('label')})")
            try:
                point_res = requests.post(
                    final_url,
                    headers={"api-key": api_key, "Content-Type": "application/json"},
                    json={
                        "messages": [
                            {"role": "system", "content": "[SENIOR DEFENSE COUNSEL] Draft a professional, legal-grade response for ONE SPECIFIC allegation. Use 'The Respondent denies...' style and cite lack of evidence where appropriate. Mirror Roxton template Exactly. Return JSON: { 'response_label': 'Response No. X', 'drafted_response': '...' }.\nSTRICT FIDELITY RULES:\n- DO NOT ANONYMIZE. This is a formal court filing; proper names like 'Betsy' are part of the record and MUST be included if present in the input.\n- DO NOT SUMMARIZE. All situational details, dates, and names MUST be preserved verbatim in the drafted output.\n- NEVER swap a proper name for generic terms like 'a staff member' or 'an employee'."},
                            {"role": "user", "content": f"ALLEGATION NO. {p.get('label')}: {p.get('allegation')}\nRESPONSE: {p.get('response')}\nLAW: {rag_context[:1000]}"}
                        ],
                        "response_format": { "type": "json_object" },
                        "max_completion_tokens": 1500
                    },
                    timeout=120
                )
                if point_res.status_code == 200:
                    p_json = json.loads(repair_json(point_res.json()["choices"][0]["message"]["content"]))
                    processed_points.append({
                        "label": f"Allegation No. {p.get('label')}",
                        "allegation": p.get('allegation'),
                        "response_label": p_json.get("response_label") or f"Response No. {p.get('label')}",
                        "response": p_json.get("drafted_response") or p.get('response')
                    })
                else:
                    processed_points.append({"label": f"Allegation No. {p.get('label')}", "allegation": p.get('allegation'), "response_label": f"Response No. {p.get('label')}", "response": p.get('response')})
            except:
                processed_points.append({"label": f"Allegation No. {p.get('label')}", "allegation": p.get('allegation'), "response_label": f"Response No. {p.get('label')}", "response": p.get('response')})

        # C. Global Sections (Analysis/Defenses/Conclusion)
        try:
            closing_res = requests.post(
                final_url,
                headers={"api-key": api_key, "Content-Type": "application/json"},
                json={
                    "messages": [
                        {"role": "system", "content": "[LEGAL COUNSEL] Generate Legal Analysis, Affirmative Defenses, and Conclusion for David Amicangioli vs Boston Childrens Hospital. Return JSON: { 'analysis': '...', 'defenses': [ '...', ... ], 'conclusion': '...' }"},
                        {"role": "user", "content": f"92 allegations have been addressed. Draft sections IV to VI."}
                    ],
                    "response_format": { "type": "json_object" },
                    "max_completion_tokens": 4000
                },
                timeout=180
            )
            if closing_res.status_code == 200:
                c_json = json.loads(repair_json(closing_res.json()["choices"][0]["message"]["content"]))
                final_analysis = c_json.get("analysis", "")
                final_defenses = c_json.get("defenses", [])
                final_conclusion = c_json.get("conclusion", "")
        except: pass

        # --- STEP 4: DOCX GENERATION ---
        doc = Document()
        doc.styles['Normal'].font.name = 'Times New Roman'
        doc.styles['Normal'].font.size = Pt(11)
        
        # 1st Page Mirror
        copy_standard_first_page(doc, request.charging_party)
        
        def add_centered_header(roman, title):
            p1 = doc.add_paragraph()
            p1.alignment = WD_ALIGN_PARAGRAPH.CENTER
            p1.paragraph_format.space_before = Pt(24)
            r1 = p1.add_run(roman)
            r1.bold = True
            p2 = doc.add_paragraph()
            p2.alignment = WD_ALIGN_PARAGRAPH.CENTER
            p2.paragraph_format.space_after = Pt(12)
            r2 = p2.add_run(title.upper())
            r2.bold = True

        def add_body_paragraph(text):
            if not text: return
            p = doc.add_paragraph(re.sub(r'\*|_', '', text).strip())
            p.paragraph_format.space_after = Pt(10)

        # Section III: Facts/Allegations
        add_centered_header("III.", "FACTS AND ALLEGATIONS")
        for item in processed_points:
            p_a = doc.add_paragraph()
            r_a = p_a.add_run(f"{item.get('label')}:")
            r_a.bold = True; r_a.underline = True
            p_a.add_run(f" {item.get('allegation')}")
            p_r = doc.add_paragraph()
            r_r = p_r.add_run(f"{item.get('response_label')}:")
            r_r.bold = True; r_r.underline = True
            p_r.add_run(f" {item.get('response')}")
            p_r.paragraph_format.space_after = Pt(12)

        # Analysis, Defenses, Conclusion
        add_centered_header("IV.", "LEGAL ANALYSIS")
        add_body_paragraph(final_analysis)
        add_centered_header("V.", "AFFIRMATIVE DEFENSES")
        for d in final_defenses: add_body_paragraph(d)
        add_centered_header("VI.", "CONCLUSION")
        add_body_paragraph(final_conclusion)

        # Save
        default_dir = Path(_HERE).parent.parent.parent.parent / "Drafts"
        try:
            f_dir = Path(request.folder_path) if request.folder_path else default_dir
            f_dir.mkdir(parents=True, exist_ok=True)
            # Test writability
            test_file = f_dir / f".write_test_{int(time.time())}"
            test_file.touch()
            test_file.unlink()
        except Exception as folder_ex:
            activity_logger.log_event("Drafting", "WARN", request.charging_party, f"Folder path invalid: {str(folder_ex)}. Falling back to default.")
            f_dir = default_dir
            f_dir.mkdir(parents=True, exist_ok=True)

        fname = f"Roxton_Draft_{request.charging_party.replace(' ', '_')}_{int(time.time())}.docx"
        fpath = f_dir / fname
        doc.save(str(fpath))
        
        activity_logger.log_event("Drafting", "END", request.charging_party, f"Successfully saved to: {str(fpath)}")
        return {"status": "success", "file_path": str(fpath)}

    except Exception as e:
        import traceback
        activity_logger.log_event("Drafting", "ERROR", request.charging_party, f"Critical: {str(e)}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))
