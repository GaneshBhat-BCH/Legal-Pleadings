
import asyncio
import asyncpg
import sys
import os

# Add the parent directory (backend) to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.config import settings

async def setup_database():
    print(f"Connecting to database: {settings.DB_HOST}...")
    try:
        # Connect to the default database to create extension
        conn = await asyncpg.connect(
            user=settings.DB_USER,
            password=settings.DB_PASSWORD,
            database=settings.DB_NAME,
            host=settings.DB_HOST,
            port=settings.DB_PORT
        )
        
        print("Creating 'vector' extension if not exists...")
        await conn.execute("CREATE EXTENSION IF NOT EXISTS vector;")
        print("Extension 'vector' created/verified.")
        
        await conn.close()
        
    except Exception as e:
        print(f"Error setting up database: {e}")
        print("Note: You might need superuser privileges to create extensions on RDS.")

if __name__ == "__main__":
    asyncio.run(setup_database())
