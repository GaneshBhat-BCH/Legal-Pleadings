import asyncio
import os
import sys

# Ensure backend module can be imported
sys.path.append(os.getcwd())

from backend.database import database
from backend.services.ai import get_embeddings

async def check_connections():
    print("=== VM Connectivity Check ===")
    
    # 1. Database Check
    print("\n[1/3] Checking Database...")
    try:
        await database.connect()
        print("SUCCESS: Database connected.")
        
        # Check if tables exist
        query = "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'coi_mgmt'"
        count = await database.fetch_val(query)
        print(f"SUCCESS: Found {count} tables in schema 'coi_mgmt'.")
        
        if count == 0:
            print("WARNING: Schema exists but no tables found. Did you run init_db.py?")
            
        await database.disconnect()
    except Exception as e:
        print(f"ERROR: Database connection failed: {e}")
        # Don't exit, try AI check anyway
        
    # 2. AI Service Check
    print("\n[2/3] Checking OpenAI Service...")
    
    # Debug: Check environment variables
    from backend.services.ai import AOAI_ENDPOINT, api_key, GPT_DEPLOYMENT
    masked_key = f"{api_key[:4]}...{api_key[-4:]}" if api_key else "None"
    print(f"DEBUG: Endpoint: '{AOAI_ENDPOINT}'")
    print(f"DEBUG: API Key: {masked_key}")
    print(f"DEBUG: Model: {GPT_DEPLOYMENT}")
    
    if not AOAI_ENDPOINT or not api_key:
        print("CRITICAL ERROR: Endpoint or API Key is missing. Check .env file location.")
        from pathlib import Path
        import backend.services.ai
        expected_env = Path(backend.services.ai.__file__).parent.parent / ".env"
        print(f"DEBUG: Expected .env path: {expected_env}")
        print(f"DEBUG: File exists? {expected_env.exists()}")
    else:
        try:
            test_text = "VM Connectivity Test"
            print(f"Sending test embedding request for '{test_text}'...")
            emb = await get_embeddings(test_text)
            if emb and len(emb) == 1536:
                print("SUCCESS: OpenAI (Embeddings) is reachable.")
            else:
                print(f"FAILURE: Embeddings returned invalid format: {type(emb)}")
        except Exception as e:
            print(f"ERROR: OpenAI connection failed: {e}")
            
            # 3. Raw Network Check
            print("\n[3/3] Checking Raw Network Connectivity...")
            import urllib.request
            import urllib.error
            try:
                # Test the base URL (without specific API paths) just to see if reachable
                test_url = AOAI_ENDPOINT.split("/openai")[0] 
                print(f"Attempting to reach: {test_url} ...")
                with urllib.request.urlopen(test_url, timeout=5) as response:
                    print(f"SUCCESS: Raw HTTP request to endpoint returned status {response.status}")
            except urllib.error.URLError as e:
                print(f"FAILURE: Raw network check failed. Reason: {e.reason}")
            except Exception as e:
                print(f"FAILURE: Raw network check failed. Error: {e}")

            print("\nTroubleshooting: If [3/3] failed, your VM firewall is blocking the connection. You may need to set HTTP_PROXY/HTTPS_PROXY environment variables.")

if __name__ == "__main__":
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(check_connections())
