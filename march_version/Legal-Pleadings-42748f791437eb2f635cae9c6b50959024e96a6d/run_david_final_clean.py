import requests
import json
import time

url = "http://localhost:8001/api/v1/drafting/generate_position_draft"

# Load JSON from file
with open("david_input.json", "r") as f:
    data = json.load(f)

# Ensure folder_path is valid for this machine
data["folder_path"] = "C:\\Users\\GaneshBhat\\Documents\\Legal Pleadings\\backend\\Drafts"

print(f"Starting drafted generation for {data['charging_party']}...")
start_time = time.time()

try:
    # Use a long timeout for the 92-point case
    response = requests.post(url, json=data, timeout=3600)
    print(f"Status Code: {response.status_code}")
    if response.status_code == 200:
        print(f"Response: {json.dumps(response.json(), indent=2)}")
    else:
        print(f"Error Body: {response.text}")
except Exception as e:
    print(f"Error: {str(e)}")

print(f"Total time: {time.time() - start_time:.2f}s")
