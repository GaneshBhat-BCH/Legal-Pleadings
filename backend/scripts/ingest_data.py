
import asyncio
import json
import os
import glob
import sys

# Add the parent directory (backend) to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.rag_service import ingest_legal_analysis

async def ingest_data():
    # Find all analysis result JSON files
    json_files = glob.glob("analysis_result_*.json")
    
    if not json_files:
        print("No analysis result JSON files found.")
        return

    total_ingested = 0
    
    for json_file in json_files:
        print(f"Processing {json_file}...")
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Extract content. The structure from process_pleading.py output might vary 
            # depending on how it was saved (raw OpenAI response vs processed dict).
            # Based on the user's file content, the JSON *is* the raw OpenAI response.
            # We need to parse the 'content' string which contains the actual JSON.
            
            legal_audit = []
            
            # Check if it's the structure we saw in the view_file (OpenAI response wrapper)
            if "choices" in data and len(data["choices"]) > 0:
                content_str = data["choices"][0]["message"]["content"]
                # Clean up potential markdown code blocks
                if content_str.startswith("```json"):
                    content_str = content_str[7:]
                if content_str.endswith("```"):
                    content_str = content_str[:-3]
                
                parsed_content = json.loads(content_str)
                if "legal_audit" in parsed_content:
                    legal_audit = parsed_content["legal_audit"]

            # Check for Azure /v1/responses 'output' structure
            elif "output" in data and isinstance(data["output"], list):
                for item in data["output"]:
                    if item.get("type") == "message" and "content" in item:
                        for content_item in item["content"]:
                            if content_item.get("type") == "output_text":
                                content_str = content_item.get("text", "")
                                
                                # Robust JSON extraction: Find first { and last }
                                try:
                                    start_index = content_str.find("{")
                                    end_index = content_str.rfind("}")
                                    
                                    if start_index != -1 and end_index != -1:
                                        json_str = content_str[start_index : end_index + 1]
                                        print(f"DEBUG: Extracting JSON from index {start_index} to {end_index} (len={len(json_str)})")
                                        
                                        # Use json_repair
                                        from json_repair import repair_json
                                        parsed_content = json.loads(repair_json(json_str))
                                    else:
                                        print("DEBUG: No JSON object found in content.")
                                        parsed_content = {}
                                    
                                    if "legal_audit" in parsed_content:
                                        legal_audit = parsed_content["legal_audit"]
                                    else:
                                        print("DEBUG: Parsed JSON but 'legal_audit' key missing.")
                                except json.JSONDecodeError as e:
                                    print(f"Failed to parse inner JSON in {json_file}: {e}")
                                    print(f"DEBUG: Content causing error: {content_str[:200]}")
            
            # Check if it's the direct output structure
            
            # Check if it's the direct output structure (if we modified the script to save clear JSON)
            elif "legal_audit" in data:
                legal_audit = data["legal_audit"]
                
            if legal_audit:
                print(f"Found {len(legal_audit)} citations to ingest.")
                count = await ingest_legal_analysis(legal_audit)
                print(f"Successfully ingested {count} documents.")
                total_ingested += count
            else:
                print("No 'legal_audit' found in the JSON.")

        except Exception as e:
            print(f"Error ingesting {json_file}: {e}")

    print(f"\nTotal documents ingested: {total_ingested}")

if __name__ == "__main__":
    asyncio.run(ingest_data())
