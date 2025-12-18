import asyncio
import os
from database import database
from pathlib import Path

async def init_db():
    print("Connecting to database...")
    await database.connect()
    
    schema_path = Path(__file__).parent / "schema.sql"
    print(f"Reading schema from {schema_path}...")
    
    with open(schema_path, "r") as f:
        schema_sql = f.read()
    
    print("Executing schema...")
    # Split by semicolon and filter out empty strings
    # Simple split is usually fine for basic schemas without complex triggers/functions
    commands = [cmd.strip() for cmd in schema_sql.split(";") if cmd.strip()]
    
    try:
        for cmd in commands:
            print(f"Executing: {cmd[:50]}...")
            await database.execute(cmd)
        print("Database initialized successfully!")
    except Exception as e:
        print(f"Error during initialization: {e}")
    finally:
        await database.disconnect()

if __name__ == "__main__":
    asyncio.run(init_db())
