import requests
import json
import os

def call_drafting():
    url = "http://localhost:8000/api/v1/drafting/generate_position_draft"
    
    # Input provided by the user
    input_data = {
        "document_metadata": {
            "charging_party": "Dela Vieira",
            "respondent": "The Children's Hospital Corporation, Katherine Pecci",
            "date_filed": "August 23, 2024",
            "all_detected_categories": ["Notice of Complaint", "Administrative Procedure"],
            "legal_case_summary": "This document is an MCAD service notice advising the Respondent that a discrimination complaint has been filed by Dela Vieira against The Children's Hospital Corporation and Katherine Pecci. It sets deadlines for preservation of evidence, filing a position statement, and attendance at an investigative conference, but it does not yet state the substantive allegations of discrimination."
        },
        "allegations_list": [
            # ... (86 items)
        ]
    }
    
    # Note: I will read the full list from the local file to ensure accuracy
    source_path = r"c:\Users\GaneshBhat\Documents\Legal Pleadings\paginated_test_output_v3.json"
    with open(source_path, "r", encoding="utf-8") as f:
        full_data = json.load(f)
    
    # Construct the payload for the CombinedDraftRequest
    # Using only 10 allegations to ensure successful AI generation for Appendix testing
    payload = {
        "raw_data": json.dumps(full_data["allegations_list"][:10]),
        "folder_path": r"c:\Users\GaneshBhat\Documents\Legal Pleadings\Drafts",
        "charging_party": full_data["document_metadata"].get("charging_party", "Dela Vieira"),
        "respondent": full_data["document_metadata"].get("respondent", "The Children's Hospital Corporation")
    }
    
    print(f"Sending request to {url}...")
    print(f"Charging Party: {payload['charging_party']}")
    print(f"Number of allegations: {len(full_data['allegations_list'])}")
    
    try:
        # Long timeout for drafting
        response = requests.post(url, json=payload, timeout=1800)
        
        if response.status_code == 200:
            print("Successfully generated draft!")
            print(json.dumps(response.json(), indent=2))
        else:
            print(f"Failed with status code: {response.status_code}")
            print(f"Error: {response.text}")
    except Exception as e:
        print(f"Exception occurred: {str(e)}")

if __name__ == "__main__":
    call_drafting()
