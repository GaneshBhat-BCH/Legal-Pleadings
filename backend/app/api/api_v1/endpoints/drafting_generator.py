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
from app.core.config import settings
from app.services.rag_service import retrieve_documents
from app.core.logger import activity_logger

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

[OUTPUT FORMAT: JSON]
Return exactly this structure:
{
  "charging_party": "string",
  "respondent": "string",
  "analysis_summary": "Overall summary of the case",
  "points": [
    {
      "allegation": "The specific claim from the PDF text",
      "lawyer_comment": "The response or factual rebuttal found in the lawyer's notes"
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
        res = requests.post(chat_url, headers=headers, json=analysis_payload, timeout=60)
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

    # --- STEP 2: RAG RETRIEVAL ---
    # Use the structured analysis as a basis for legal research.
    search_query = structured_data.get("analysis_summary", "")
    for p in structured_data.get("points", []):
         search_query += f" {p['allegation']} {p['lawyer_comment']}"
         
    try:
        rag_docs = await retrieve_documents(search_query, k=8)
        rag_context = "\n\n".join([f"Source citation: {d.page_content}" for d in rag_docs])
    except Exception as e:
        print(f"RAG Error: {e}")
        rag_context = "No direct legal citations found in vector store."

    # --- STEP 3: DRAFTING ---
    draft_prompt = """You are a Senior Legal Counsel. You will draft a formal, high-quality "Position Statement" for a legal case based on the provided facts and legal citations.

[OUTPUT FORMAT: JSON]
You MUST return your entire response as a structured JSON object exactly as follows:
{
  "introduction": "The text for I. INTRODUCTION. Include a summary of parties and high-level defense.",
  "background": "The text for II. BACKGROUND. Narrative history based on the lawyer notes.",
  "allegations": "The text for III. COMPLAINT'S ALLEGATIONS. Address each point specifically.",
  "analysis": "The text for IV. ANALYSIS. Legal argument gracefully interweaving the [RELEVANT LEGAL CITATIONS]."
}

[INSTRUCTIONS]
- Draft professionally, persuasively, clinically, and sterilely. 
- Avoid markdown tags in the text fields. Only return the raw text.
- Address the allegations in the 'allegations' section.
- Interweave citations in the 'analysis' section."""

    draft_user_input = f"""
[CASE DETAILS]
Charging Party: {structured_data.get('charging_party', request.charging_party)}
Respondent: {structured_data.get('respondent', request.respondent)}
Summary: {structured_data.get('analysis_summary')}

[ALLEGATIONS AND RESPONSES]
"""
    for i, p in enumerate(structured_data.get("points", []), 1):
        draft_user_input += f"\nPoint {i}:\nAllegation: {p['allegation']}\nRespondent's Facts: {p['lawyer_comment']}\n"

    draft_user_input += f"\n[RELEVANT LEGAL CITATIONS]\n{rag_context}"

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
        res = requests.post(chat_url, headers=headers, json=draft_payload, timeout=120)
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
        except Exception as parse_err:
            print(f"Draft JSON Parse warning: {parse_err}")
            # Fallback
            draft_data = {
                "introduction": "Parsing Error. Raw content below:\n" + draft_content,
                "background": "",
                "allegations": "",
                "analysis": ""
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
        # Assuming logos are placed correctly in the backend or we can reference their absolute paths
        left_logo_path = r"C:\Users\GaneshBhat\.gemini\antigravity\brain\992d3bc6-b9e8-4424-92af-148ae96d92eb\media__1773144732317.png"
        right_logo_path = r"C:\Users\GaneshBhat\.gemini\antigravity\brain\992d3bc6-b9e8-4424-92af-148ae96d92eb\media__1773144732266.png"
        
        if Path(left_logo_path).exists() and Path(right_logo_path).exists():
            logo_table = doc.add_table(rows=1, cols=2)
            logo_table.allow_autofit = True
            
            # Left cell (Image 1 - Now BCH)
            left_cell = logo_table.cell(0, 0)
            left_pr = left_cell.paragraphs[0]
            left_pr.alignment = WD_ALIGN_PARAGRAPH.LEFT
            left_r = left_pr.add_run()
            left_r.add_picture(left_logo_path, width=Inches(3.0))
            
            # Right cell (Image 2 - Now HMS)
            right_cell = logo_table.cell(0, 1)
            right_pr = right_cell.paragraphs[0]
            right_pr.alignment = WD_ALIGN_PARAGRAPH.RIGHT
            right_r = right_pr.add_run()
            right_r.add_picture(right_logo_path, width=Inches(1.5))

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
            ("I.\nINTRODUCTION", draft_data.get("introduction", "")),
            ("II.\nBACKGROUND", draft_data.get("background", "")),
            ("III.\nCOMPLAINT'S ALLEGATIONS", draft_data.get("allegations", "")),
            ("IV.\nANALYSIS", draft_data.get("analysis", ""))
        ]
        
        for head, content in sections:
            h = doc.add_paragraph(head)
            h.alignment = WD_ALIGN_PARAGRAPH.CENTER
            for run in h.runs:
                run.bold = True
            for paragraph in content.split("\n\n"):
                if paragraph.strip():
                    doc.add_paragraph(paragraph.strip())

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
            "citations_used": len(rag_docs) if 'rag_docs' in locals() else 0
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create Word file: {str(e)}")
