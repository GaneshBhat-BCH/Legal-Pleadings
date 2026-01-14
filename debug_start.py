import asyncio
import os
import sys
import uvicorn
from backend.database import database

# Mimic startup
async def test_startup():
    print("Attempting database connection...")
    try:
        await database.connect()
        print("Database connection SUCCESS!")
        await database.disconnect()
        print("Database disconnect SUCCESS!")
    except Exception as e:
        print(f"Database connection FAILED: {e}")
        raise e

if __name__ == "__main__":
    # 1. Test connection isolated
    try:
        asyncio.run(test_startup())
    except Exception:
        print("Startup test failed.")
        sys.exit(1)
        
    # 2. Test uvicorn start
    print("Attempting to start uvicorn on port 8001...")
    try:
        uvicorn.run("backend.main:app", host="0.0.0.0", port=8001, log_level="debug")
    except Exception as e:
        print(f"Uvicorn failed: {e}")
