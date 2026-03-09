import asyncio
import sys
import os

sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "backend"))
from app.core.config import settings
import asyncpg

async def check():
    conn = await asyncpg.connect(
        user=settings.DB_USER,
        password=settings.DB_PASSWORD,
        database=settings.DB_NAME,
        host=settings.DB_HOST,
        port=settings.DB_PORT
    )
    db_name = await conn.fetchval("SELECT current_database();")
    print("DATABASE : " + db_name)
    print("HOST     : " + settings.DB_HOST)
    print("-" * 50)

    # Search ALL schemas for any langchain tables
    rows = await conn.fetch("""
        SELECT table_schema, table_name
        FROM information_schema.tables
        WHERE table_name LIKE 'langchain%'
        ORDER BY table_schema, table_name;
    """)
    if rows:
        print("Found " + str(len(rows)) + " langchain table(s) across all schemas:")
        for r in rows:
            # get row count for each
            count = await conn.fetchval(
                'SELECT COUNT(*) FROM "' + r["table_schema"] + '"."' + r["table_name"] + '";'
            )
            print("  [" + r["table_schema"] + "] " + r["table_name"] + " -> " + str(count) + " rows")
    else:
        print("WARNING: No LangChain tables found in this database at all!")
    await conn.close()

asyncio.run(check())
