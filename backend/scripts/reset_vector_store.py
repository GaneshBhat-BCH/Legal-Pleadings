
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

        # Step 1: DROP the tables completely (CASCADE handles the foreign key)
        print("Dropping tables in 'Legal_Pleadings' schema...")
        await conn.execute('DROP TABLE IF EXISTS "Legal_Pleadings".langchain_pg_embedding CASCADE;')
        await conn.execute('DROP TABLE IF EXISTS "Legal_Pleadings".langchain_pg_collection CASCADE;')
        print("Tables dropped successfully.")
        await conn.close()

        # Step 2: Recreate tables by importing and triggering PGVector initialization
        print("Recreating tables via PGVector...")
        from app.db.vector_store import vector_store
        async with vector_store._async_engine.begin() as conn:
            await vector_store.acreate_tables_if_not_exists()
        print("Tables recreated successfully!")
        print("Vector store is clean and ready to use.")

    except Exception as e:
        print(f"Error resetting DB: {e}")

if __name__ == "__main__":
    asyncio.run(reset_db())
