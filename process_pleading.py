import os
import requests
import json
import glob
import time
import asyncio
import sys
from dotenv import load_dotenv
from pathlib import Path

# Add backend to path for RAG service imports
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "backend"))
from app.services.rag_service import ingest_legal_analysis

# Load environment variables
env_path = Path(__file__).parent / ".env"
load_dotenv(dotenv_path=env_path)

# Configuration
# Configuration
# Configuration
API_KEY = os.getenv("AZURE_OPENAI_API_KEY")
BASE_URL = "https://ai-automationanywhere-prd-eus2-01.openai.azure.com/openai"

# Construct URLs
FILES_ENDPOINT = f"{BASE_URL}/files?api-version=2024-05-01-preview"
RESPONSES_ENDPOINT = f"{BASE_URL}/v1/responses" # Exact URL provided by user

def get_all_pdfs():
    """Finds all PDF files in the data directory."""
    files = glob.glob("data/*.pdf")
    if not files:
        print("Error: No PDF files found in 'data/' directory.")
        return []
    print(f"Found {len(files)} PDF(s):")
    for f in files:
        print(f" - {f}")
    return files

def upload_file(file_path):
    """Uploads a file to Azure OpenAI."""
    print(f"Uploading {file_path} to Azure OpenAI...")
    headers = {
        "api-key": API_KEY
    }
    
    try:
        with open(file_path, "rb") as f:
            files = {"file": (os.path.basename(file_path), f, "application/pdf")}
            data = {"purpose": "assistants"}
            
            response = requests.post(FILES_ENDPOINT, headers=headers, files=files, data=data)
            
        if response.status_code == 200:
            file_id = response.json()["id"]
            print(f"File uploaded successfully. ID: {file_id}")
            return file_id
        else:
            print(f"Upload failed: {response.status_code} - {response.text}")
            return None
    except Exception as e:
        print(f"An error occurred during upload: {e}")
        return None

def analyze_pleading(file_id):
    """Sends the analysis request to Azure OpenAI."""
    print("Sending analysis request...")
    
    system_prompt = """[SYSTEM ROLE]
You are a Legal Research Librarian and AI Automation Specialist. Your task is to audit an existing Position Statement to identify and explain all legal authorities cited within the text.

[EXTRACTION OBJECTIVES]

Identify Citations: Locate every mention of a law (e.g., Title VII), act (e.g., ADA), regulation, or court case.

Contextual Analysis: Determine exactly which "Charge Category" (e.g., Race, Age, Retaliation) the law is being used to defend.

Background Enrichment: Provide a concise summary of the law's purpose and the "burden of proof" it requires in an employment context.

[OUTPUT FORMAT: JSON]
Return the results in the following structure to ensure it can be used for your AI Brahma automation projects:

JSON
{
  "legal_audit": [
    {
      "law_cited": "Full name of the statute or case",
      "citation_context": "The specific sentence from the Position Statement where this law was used",
      "associated_category": "The protected class or legal theory this law governs",
      "legal_background": "A 2-3 sentence explanation of what this law requires the employer to prove",
      "relevance_score": "High/Medium/Low based on how central it is to the defense"
    }
  ]
}
[PROCESSING RULES]

Strict Verbatim: The law_cited must match the text in the document exactly.

No Skipping: Even if a law is mentioned multiple times, extract it once but note its multiple applications.

Hybrid Knowledge: Use your internal legal database to provide the legal_background if it isn't fully explained in the Position Statement.

Category-Specific Background Examples
When your agent provides the legal_background, it should follow these established legal standards:

Title VII (Race/Sex/Religion): Prohibits discrimination in any aspect of employment. Background: Focuses on "Disparate Treatment" where the agent looks for proof that the employee was treated differently than others.

ADA (Disability): Background: Focuses on the "Interactive Process" and "Reasonable Accommodation." The agent must note if the company attempted to find a solution for the employee's limitations.

ADEA (Age): Background: Focuses on the "But-For" causation standard, meaning the action wouldn't have happened if not for the employee's age."""

    payload = {
        "model": "gpt-5",
        "tools": [
            {
                "type": "code_interpreter",
                 "container": {
                    "type": "auto"
                  }
            }
        ],
        "input": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": system_prompt
                    },
                    {
                        "type": "input_file",
                        "file_id": file_id
                    }
                ]
            }
        ]
    }
    
    headers = {
        "api-key": API_KEY,
        "Content-Type": "application/json"
    }
    
    try:
        response = requests.post(RESPONSES_ENDPOINT, headers=headers, json=payload)
        
        if response.status_code == 200:
            print("Analysis complete.")
            return response.json()
        else:
            print(f"Analysis failed: {response.status_code} - {response.text}")
            return None
            
    except Exception as e:
        print(f"An error occurred during analysis: {e}")
        return None
    



async def main():
    print("Starting Legal Pleading Analysis...")
    
    # 1. Find PDFs
    pdf_files = get_all_pdfs()
    if not pdf_files:
        return

    for pdf_path in pdf_files:
        print(f"\n--- Processing: {pdf_path} ---")
        
        # 2. Upload File
        file_id = upload_file(pdf_path)
        if not file_id:
            continue

        # 3. Analyze
        result = analyze_pleading(file_id)
        if not result:
            continue

        # 4. Process Output
        try:
            # Save raw result to file for inspection
            base_name = os.path.basename(pdf_path)
            json_filename = f"analysis_result_{base_name}.json"
            with open(json_filename, "w", encoding="utf-8") as f:
                json.dump(result, f, indent=2)
            print(f"Analysis result saved to '{json_filename}'")

            # Attempt to extract the content
            content = None
            if "choices" in result and len(result["choices"]) > 0:
                content = result["choices"][0]["message"]["content"]
            elif "output" in result: # Some Azure endpoints use 'output'
                 content = result["output"]
            else:
                content = json.dumps(result, indent=2)

            print("\n--- Analysis Output ---\n")
            print(content)
            
            # --- REAL-TIME RAG INGESTION LOGIC ---
            print("\n--- Starting RAG Vector Ingestion ---")
            legal_audit = []
            
            try:
                start_idx = content.find("{")
                end_idx = content.rfind("}")
                if start_idx != -1 and end_idx != -1:
                    json_str = content[start_idx:end_idx+1]
                    try:
                        from json_repair import repair_json
                        parsed = json.loads(repair_json(json_str))
                    except ImportError:
                        parsed = json.loads(json_str)
                        
                    if "legal_audit" in parsed:
                        legal_audit = parsed["legal_audit"]
            except Exception as e:
                print(f"Failed to parse inner JSON: {e}")
                
            if legal_audit:
                print(f"Found {len(legal_audit)} citations. Ingesting into Vector DB...")
                count = await ingest_legal_analysis(legal_audit)
                print(f"[{base_name}] SUCCESS: Saved {count} vectors to the RAG database!")
            else:
                print("WARNING: No valid 'legal_audit' JSON found. Skipping RAG ingestion.")
            print(f"--- [{base_name}] Pipeline complete. Moving to next file. ---")
            
        except Exception as e:
            print(f"Error processing result for {pdf_path}: {e}")
        
        # Optional: wait a bit between files
        time.sleep(2)

if __name__ == "__main__":
    asyncio.run(main())
