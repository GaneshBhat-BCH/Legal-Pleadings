import asyncio
import os
import sys

# Ensure backend module can be imported
sys.path.append(os.getcwd())

from backend.database import database

async def clear_tables():
    print("Connecting to database...")
    await database.connect()
    try:
        print("Clearing tables in coi_mgmt schema...")
        # TRUNCATE removes all rows. CASCADE ensures dependent rows (pdf_answers, pdf_chunks) are also removed.
        await database.execute("TRUNCATE TABLE coi_mgmt.pdf_documents, coi_mgmt.user_queries CASCADE;")
        print("Tables cleared successfully.")
    except Exception as e:
        print(f"Error clearing tables: {e}")
    finally:
        await database.disconnect()

if __name__ == "__main__":
    asyncio.run(clear_tables())
