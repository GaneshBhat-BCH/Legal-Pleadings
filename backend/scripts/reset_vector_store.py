
import asyncio
import sys
import os
import asyncpg

# Add backend to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.config import settings

async def reset_db():
    print("Connecting to database...")
    try:
        conn = await asyncpg.connect(
            user=settings.DB_USER,
            password=settings.DB_PASSWORD,
            database=settings.DB_NAME,
            host=settings.DB_HOST,
            port=settings.DB_PORT
        )
        # Check if tables exist first to avoid error
        # Assuming schemas are correct
        print("Truncating tables in 'Legal_Pleadings'...")
        await conn.execute('TRUNCATE TABLE "Legal_Pleadings".langchain_pg_embedding RESTART IDENTITY CASCADE;')
        await conn.execute('TRUNCATE TABLE "Legal_Pleadings".langchain_pg_collection RESTART IDENTITY CASCADE;')
        print("Vector store reset complete.")
        await conn.close()
    except Exception as e:
        print(f"Error resetting DB (tables might not exist yet): {e}")

if __name__ == "__main__":
    asyncio.run(reset_db())
