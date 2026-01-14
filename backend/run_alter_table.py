
import asyncio
import sys
import os

# Add the parent directory to sys.path so we can import backend.database
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.database import database

async def run_migrations():
    print("Connecting to database...")
    await database.connect()
    
    try:
        print("Running ALTER TABLE commands...")
        
        # Add input_body column
        query1 = "ALTER TABLE coi_mgmt.pdf_documents ADD COLUMN IF NOT EXISTS input_body TEXT;"
        await database.execute(query1)
        print(" - Added input_body column.")

        # Add result_body column
        query2 = "ALTER TABLE coi_mgmt.pdf_documents ADD COLUMN IF NOT EXISTS result_body TEXT;"
        await database.execute(query2)
        print(" - Added result_body column.")
        
        print("Schema update successful.")
        
    except Exception as e:
        print(f"Error updating schema: {e}")
    finally:
        await database.disconnect()
        print("Disconnected.")

if __name__ == "__main__":
    asyncio.run(run_migrations())
