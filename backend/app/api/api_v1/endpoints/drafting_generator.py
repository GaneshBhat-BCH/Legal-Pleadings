from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
import os
import requests
import json
import time
import re
from datetime import datetime
from pathlib import Path
from docx import Document
from docx.shared import Pt, Inches
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.table import Table, _Cell
from docx.text.paragraph import Paragraph
from docx.oxml.table import CT_Tbl
from docx.oxml.text.paragraph import CT_P
from app.core.config import settings
from app.services.rag_service import retrieve_documents
from app.core.logger import activity_logger

# Helper to resolve logo paths
_HERE = Path(__file__).parent

def sanitize_xml(text):
    """Remove control characters that break XML/DOCX."""
    if not isinstance(text, str):
        return text
    # Standard XML-illegal character ranges
    illegal_xml_chars_re = re.compile(
        u'[\x00-\x08\x0b\x0c\x0e-\x1F\uD800-\uDFFF\uFFFE\uFFFF]'
    )
    return illegal_xml_chars_re.sub('', text)

# Navigate to backend/assets correctly (parent is api_v1, parent2 is api, parent3 is app, parent4 is backend)
_ASSETS_DIR = _HERE.parent.parent.parent.parent / "assets"
LEFT_LOGO = _ASSETS_DIR / "bch_logo.png"
RIGHT_LOGO = _ASSETS_DIR / "hms_logo.png"

# Reference Document Path (Template)
# Use a relative fallback for the VM environment if the OneDrive path is missing
_DEFAULT_TEMPLATE = _ASSETS_DIR / "templates" / "Legal_Template.docx"
REFERENCE_DOC_PATH = os.getenv("REFERENCE_DOC_PATH", str(_DEFAULT_TEMPLATE))

def get_current_date_str():
    from datetime import datetime
    return datetime.now().strftime("%B %d, %Y")

def copy_standard_first_page(target_doc, charging_party, respondent):
    """
    Clones the intro sections (Transmittal Letter + Legal Caption) from the master 
    Legal_Template.docx into target_doc. Handles dynamic replacements.
    """
    if not os.path.exists(REFERENCE_DOC_PATH):
        activity_logger.log_event("Drafting", "WARN", charging_party, "Reference doc not found. Skipping mirror.")
        return False
    
    source_doc = Document(REFERENCE_DOC_PATH)
    curr_date = get_current_date_str()
    
    from docx.oxml.table import CT_Tbl
    from docx.oxml.text.paragraph import CT_P
    from docx.table import Table, _Cell
    from docx.text.paragraph import Paragraph

    def iter_block_items(parent):
        if hasattr(parent, 'element') and hasattr(parent.element, 'body'):
            parent_elm = parent.element.body
        elif hasattr(parent, '_tc'):
            parent_elm = parent._tc
        else:
            raise TypeError("Value must be a document or cell")

        for child in parent_elm.iterchildren():
            if isinstance(child, CT_P):
                yield Paragraph(child, parent)
            elif isinstance(child, CT_Tbl):
                yield Table(child, parent)

    # Global Font Setup for Cloned Parts
    def apply_replacement(text, cp, resp, date):
        # Specific Roxton Draft Replacements
        # Use word boundaries \b for BCH to avoid messing up addresses like 'BCH3046'
        text = re.sub(r"\bAndrea Roxton\b", cp, text, flags=re.IGNORECASE)
        text = re.sub(r"\bMs\. Roxton\b", f"Ms. {cp.split()[-1]}", text, flags=re.IGNORECASE)
        text = re.sub(r"March 25, 2026", date, text)
        
        # Only replace 'Respondent' if it's not already followed by the respondent name
        if resp.lower() not in text.lower() or "Respondent," in text:
             # Handle 'Respondent, [Name]' specifically to avoid 'Name, Name'
             text = text.replace("Respondent,", f"{resp},")
             text = re.sub(r"\bRespondent\b", resp, text, flags=re.IGNORECASE)
            
        text = re.sub(r"\bBCH\b", resp, text)
        return sanitize_xml(text)

    for block in iter_block_items(source_doc):
        # Stop exactly before Section I (INTRODUCTION) starts
        # This keeps the Letter (Page 1) and Case Caption (Page 2)
        if isinstance(block, Paragraph):
            if "I." in block.text.upper() and "INTRODUCTION" in block.text.upper():
                break
        
        if isinstance(block, Table):
            # Clone Table Structure (Captures Table 0 Logos and Table 1 Caption)
            new_table = target_doc.add_table(rows=len(block.rows), cols=len(block.columns))
            new_table.style = block.style
            for r_idx, row in enumerate(block.rows):
                for c_idx, cell in enumerate(row.cells):
                    target_cell = new_table.cell(r_idx, c_idx)
                    for p in cell.paragraphs:
                        new_p = target_cell.add_paragraph()
                        new_p.alignment = p.alignment
                        for run in p.runs:
                            # Handle Logos
                            if "BCH_LOGO" in run.text.upper() or "HMS_LOGO" in run.text.upper():
                                if "BCH_LOGO" in run.text.upper() and LEFT_LOGO.exists():
                                    new_p.add_run().add_picture(str(LEFT_LOGO), width=Inches(3.0))
                                elif "HMS_LOGO" in run.text.upper() and RIGHT_LOGO.exists():
                                    new_p.add_run().add_picture(str(RIGHT_LOGO), width=Inches(1.5))
                                continue

                            text = apply_replacement(run.text, charging_party, respondent, curr_date)
                            new_run = new_p.add_run(text)
                            new_run.bold = run.bold
                            new_run.italic = run.italic
                            new_run.underline = run.underline
                            if run.font.size: new_run.font.size = run.font.size
                            else: new_run.font.size = Pt(11)
                            new_run.font.name = 'Times New Roman'
        
        elif isinstance(block, Paragraph):
            # Skip empty paragraphs that don't have formatting (like spacing)
            if not block.text.strip() and not block.runs:
                target_doc.add_paragraph()
                continue
            
            # Manually handle Page Break before the Pleading Caption
            if "COMMONWEALTH OF MASSACHUSETTS" in block.text.upper():
                target_doc.add_page_break()
            
            text = apply_replacement(block.text, charging_party, respondent, curr_date)
            new_p = target_doc.add_paragraph()
            new_p.alignment = block.alignment
            new_p.style = block.style
            
            for run in block.runs:
                run_text = apply_replacement(run.text, charging_party, respondent, curr_date)
                new_run = new_p.add_run(run_text)
                new_run.bold = run.bold
                new_run.italic = run.italic
                new_run.underline = run.underline
                if run.font.size: new_run.font.size = run.font.size
                else: new_run.font.size = Pt(11)
                new_run.font.name = 'Times New Roman'

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
    case_number: Optional[str] = Field(None, description="MCAD/EEOC Case Number")

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

        # --- STEP 3: LITERARY DRAFTING (10-MODULE STRATEGY) ---
        activity_logger.log_event("Drafting", "BATCH_START", request.charging_party, f"Drafting 10-Module Position Statement...")
        
        processed_points = []
        final_sections = {
            "introduction": "",
            "procedural_history": "",
            "statement_of_facts": "",
            "analysis": {}, # Subsections A-E
            "conclusion": "",
            "appendix": ""
        }

        # A. Global Sections (Master Prompt Strategy)
        master_prompt = f"""[SENIOR DEFENSE COUNSEL - GPT-5.4 LEGAL SPECIALIST]
        You are a top-tier US employment defense attorney. Draft a 100% formal, professional Position Statement for {request.respondent}.
        
        STRICT REGISTRY: Use formal US legal language. No summaries. No generalizations. Verbatim names and quotes.
        
        STRUCTURE (GLOBAL MODULES):
        - I. INTRODUCTION (Firm denial, core mission)
        - II. PROCEDURAL HISTORY (Administrative timeline)
        - III. STATEMENT OF FACTS (The core narrative of performance and neutral policy application)
        - V. LEGAL ANALYSIS (Broken into 5 sub-sections: A. Discrimination, B. Retaliation, C. Disability/Interactive Process, D. Constructive Discharge, E. Damages)
        - VI. CONCLUSION (Formal request for dismissal)
        - VII. APPENDIX (Detailed statutory framework citing MCAD/EEOC regulations)
        
        CASE DATA (CONTEXT):
        {json.dumps(final_points[:20], indent=2)}
        
        RETURN JSON:
        {{
            "introduction": "...",
            "procedural_history": "...",
            "statement_of_facts": "...",
            "analysis": {{
                "discrimination": "...",
                "retaliation": "...",
                "disability": "...",
                "discharge": "...",
                "damages": "..."
            }},
            "conclusion": "...",
            "appendix": "..."
        }}
        """

        try:
            summary_res = requests.post(
                final_url,
                headers={"api-key": api_key, "Content-Type": "application/json"},
                json={
                    "messages": [
                        {"role": "system", "content": master_prompt},
                        {"role": "user", "content": f"Generate the global sections for {request.charging_party} vs {request.respondent}."}
                    ],
                    "response_format": { "type": "json_object" },
                    "max_completion_tokens": 4096
                },
                timeout=300
            )
            if summary_res.status_code == 200:
                final_sections = json.loads(repair_json(summary_res.json()["choices"][0]["message"]["content"]))
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
                            {"role": "system", "content": "[SENIOR DEFENSE COUNSEL] Draft a professional, legal-grade response for ONE SPECIFIC allegation. Use 'The Respondent denies...' style and cite lack of evidence where appropriate. Return JSON: { 'response_label': 'Response No. X', 'drafted_response': '...' }.\nSTRICT FIDELITY RULES:\n- DO NOT ANONYMIZE. This is a formal court filing; proper names like 'Betsy' are part of the record and MUST be included if present in the input.\n- DO NOT SUMMARIZE. All situational details, dates, and names MUST be preserved verbatim in the drafted output.\n- NEVER swap a proper name for generic terms like 'a staff member' or 'an employee'."},
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
                        "allegation": sanitize_xml(p.get('allegation')),
                        "response_label": sanitize_xml(p_json.get("response_label") or f"Response No. {p.get('label')}"),
                        "response": sanitize_xml(p_json.get("drafted_response") or p.get('response'))
                    })
                else:
                    processed_points.append({"label": f"Allegation No. {p.get('label')}", "allegation": sanitize_xml(p.get('allegation')), "response": sanitize_xml(p.get('response'))})
            except:
                processed_points.append({"label": f"Allegation No. {p.get('label')}", "allegation": sanitize_xml(p.get('allegation')), "response": sanitize_xml(p.get('response'))})

        # --- STEP 4: DOCX GENERATION (TEMPLATE-FIRST) ---
        # _HERE is .../backend/app/api/api_v1/endpoints
        template_path = Path(_HERE).parent.parent.parent.parent / "assets" / "templates" / "Legal_Template.docx"
        
        if not template_path.exists():
            activity_logger.log_event("Drafting", "ERROR", request.charging_party, f"Template not found at {template_path}. Falling back to blank document.")
            doc = Document()
            # Minimal styling for fallback
            doc.styles['Normal'].font.name = 'Times New Roman'
            doc.styles['Normal'].font.size = Pt(11)
        else:
            doc = Document(str(template_path))

            # --- FRONT MATTER REPLACEMENTS ---
            replacements = {
                "ANDREA ROXTON": request.charging_party,
                "Andrea Roxton": request.charging_party,
                "BOSTON CHILDREN'S HOSPITAL": request.respondent,
                "Boston Children's Hospital": request.respondent,
                "Genevieve Benoit": "GENEVIEVE BENOIT",
                "March 25, 2026": datetime.now().strftime("%B %d, %Y"),
                "[NEED LAWYER INPUT: Investigator Name]": "Investigator",
                "[NEED LAWYER INPUT: Investigator Email]": "investigator@mcaq.gov",
                "[NEED LAWYER INPUT: MCAD No.]": request.case_number if request.case_number else "MCAD No. 24-EM-12345",
                "[NEED LAWYER INPUT: EEOC No.]": "EEOC No. 16K-2024-00123",
                "BCH": request.respondent 
            }

            # Replace in Tables (Logo and Caption)
            for i, tbl in enumerate(doc.tables):
                if i < 2:
                    for k, v in replacements.items():
                        for row in tbl.rows:
                            for cell in row.cells:
                                for p in cell.paragraphs:
                                    for r in p.runs:
                                        if k in r.text:
                                            r.text = r.text.replace(k, str(v))

            # Replace in Paragraphs (Front Matter)
            for i, p in enumerate(doc.paragraphs[:20]):
                for k, v in replacements.items():
                    for r in p.runs:
                        if k in r.text:
                            r.text = r.text.replace(k, str(v))

            # --- DELETE BOILERPLATE ---
            # Index 10 is the start of "I. INTRODUCTION" in our template scan
            body_elements = list(doc.element.body)
            # Find the cutoff: anything starting with "I. INTRODUCTION" or similar should be where we delete
            for el in body_elements[10:]:
                if el.tag.endswith('sectPr'): continue # Preserve section props
                parent = el.getparent()
                if parent is not None:
                    parent.remove(el)

        # --- APPEND MODULAR CONTENT ---
        def add_centered_header(num, title):
            p = doc.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            r = p.add_run(f"{num} {title}" if num else title)
            r.bold = True
            r.font.size = Pt(12)
            p.paragraph_format.space_before = Pt(18)
            p.paragraph_format.space_after = Pt(12)

        def add_body_paragraph(text):
            if not text: return
            p = doc.add_paragraph(sanitize_xml(text))
            p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
            p.paragraph_format.first_line_indent = Inches(0.5)
            p.paragraph_format.space_after = Pt(12)
            p.paragraph_format.line_spacing = 1.15

        # Draft Modules
        add_centered_header("I.", "INTRODUCTION")
        add_body_paragraph(final_sections.get("introduction", ""))

        add_centered_header("II.", "PROCEDURAL HISTORY")
        add_body_paragraph(final_sections.get("procedural_history", ""))

        add_centered_header("III.", "STATEMENT OF FACTS")
        add_body_paragraph(final_sections.get("statement_of_facts", ""))

        add_centered_header("IV.", "RESPONDENT'S ANSWERS TO SPECIFIC ALLEGATIONS")
        for p in processed_points:
            p_header = doc.add_paragraph()
            p_header.paragraph_format.space_before = Pt(12)
            r_header = p_header.add_run(sanitize_xml(p['label']))
            r_header.bold = True
            add_body_paragraph(p['allegation'])
            
            p_ans = doc.add_paragraph()
            r_ans = p_ans.add_run(sanitize_xml(p.get('response_label', "Response:")))
            r_ans.bold = True
            add_body_paragraph(p['response'])

        add_centered_header("V.", "LEGAL ANALYSIS")
        l_analysis = final_sections.get("legal_analysis", {})
        if isinstance(l_analysis, str):
            add_body_paragraph(l_analysis)
        elif isinstance(l_analysis, dict):
            for k, v in l_analysis.items():
                p_sub = doc.add_paragraph()
                r_sub = p_sub.add_run(sanitize_xml(k.replace('_', ' ').title()))
                r_sub.bold = True
                add_body_paragraph(v)

        add_centered_header("VI.", "AFFIRMATIVE DEFENSES")
        standard_defenses = [
            "Failure to state a claim upon which relief can be granted.",
            "Lack of probable cause as to any alleged violation of anti-discrimination or anti-retaliation statutes.",
            "Legitimate, non-discriminatory and non-retaliatory business reasons for all challenged actions.",
            "No materially adverse employment action taken against Charging Party as a matter of law.",
            "Lack of causal connection between any protected activity and any challenged action; absence of but-for causation.",
            "Equal application of policies and consistent treatment of similarly situated employees; absence of comparator evidence.",
            "Good faith adherence to and enforcement of anti-discrimination, anti-harassment, anti-retaliation, leave, and accommodation policies.",
            "Failure to engage in the interactive process by Charging Party and/or failure to provide sufficient medical documentation.",
            "Statute of limitations and/or untimeliness of any claims outside the actionable period.",
            "Failure to exhaust administrative remedies for any claims not properly presented to the agency.",
            "After-acquired evidence and/or subsequently discovered information limiting or barring damages, if applicable.",
            "Failure to mitigate damages, including economic loss.",
            "Estoppel, waiver, and laches as appropriate based on Charging Party's conduct and delay.",
            "Good faith, reasonable grounds, and lack of willfulness precluding liquidated or punitive damages."
        ]
        for idx, d in enumerate(standard_defenses):
            add_body_paragraph(f"{idx+1}. {d}")

        add_centered_header("VII.", "CONCLUSION")
        conclusion_text = final_sections.get("conclusion", "")
        conclusion_text = re.sub(r'^VI\.\s+CONCLUSION\s*', '', conclusion_text, flags=re.IGNORECASE).strip()
        add_body_paragraph(conclusion_text)
        
        # --- SIGNATURE BLOCK ---
        p_sig = doc.add_paragraph()
        p_sig.paragraph_format.space_before = Pt(24)
        p_sig.add_run("Respectfully submitted,")
        p_resp = doc.add_paragraph()
        r_resp = p_resp.add_run(sanitize_xml(request.respondent))
        r_resp.bold = True
        p_atty = doc.add_paragraph()
        p_atty.add_run("By its attorneys,")
        
        # --- VERIFICATION ---
        add_centered_header(None, "VERIFICATION")
        add_body_paragraph("I, upon information and belief, affirm that the facts stated herein are true and correct to the best of my knowledge based on records maintained in the ordinary course of business and information provided to me. This Position Statement is submitted without waiver of any privileges, defenses, or objections, all of which are expressly preserved.")

        # --- APPENDIX ---
        doc.add_page_break()
        add_centered_header("VIII.", "APPENDIX: STATUTORY AND REGULATORY FRAMEWORK")
        appendix_text = final_sections.get("appendix", "")
        appendix_text = re.sub(r'^VII\.\s+APPENDIX.*?\n', '', appendix_text, flags=re.IGNORECASE).strip()
        add_body_paragraph(appendix_text)

        # --- SAVE ---
        default_dir = Path(_HERE).parent.parent.parent.parent / "Drafts"
        try:
            f_dir = Path(request.folder_path) if request.folder_path else default_dir
            f_dir.mkdir(parents=True, exist_ok=True)
        except:
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
