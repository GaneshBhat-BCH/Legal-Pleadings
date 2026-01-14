import asyncio
import os
import sys

# Ensure backend module can be imported
sys.path.append(os.getcwd())

from backend.database import database

async def reset_db():
    print("Connecting to database...")
    await database.connect()
    try:
        print("Dropping schema coi_mgmt cascade...")
        await database.execute("DROP SCHEMA IF EXISTS coi_mgmt CASCADE;")
        print("Schema dropped successfully.")
    except Exception as e:
        print(f"Error dropping schema: {e}")
    finally:
        await database.disconnect()

if __name__ == "__main__":
    asyncio.run(reset_db())
