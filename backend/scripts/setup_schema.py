
import asyncio
import asyncpg
import sys
import os

# Add the parent directory (backend) to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.config import settings

async def setup_schema():
    schema_name = "Legal_Pleadings"
    print(f"Connecting to database to create schema '{schema_name}'...")
    try:
        conn = await asyncpg.connect(
            user=settings.DB_USER,
            password=settings.DB_PASSWORD,
            database=settings.DB_NAME,
            host=settings.DB_HOST,
            port=settings.DB_PORT
        )
        
        print(f"Creating schema {schema_name} if not exists...")
        await conn.execute(f"CREATE SCHEMA IF NOT EXISTS \"{schema_name}\";")
        
        # We also need the vector extension. It is usually installed in public, 
        # but the new schema needs to be in search path.
        # We can also verify vector extension here.
        await conn.execute("CREATE EXTENSION IF NOT EXISTS vector;")
        
        print(f"Schema '{schema_name}' created/verified.")
        await conn.close()
        
    except Exception as e:
        print(f"Error creating schema: {e}")

if __name__ == "__main__":
    asyncio.run(setup_schema())
