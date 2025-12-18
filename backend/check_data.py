import asyncio
from database import database

async def check():
    await database.connect()
    
    chunks_count = await database.fetch_val("SELECT COUNT(*) FROM coi_mgmt.pdf_chunks")
    answers_count = await database.fetch_val("SELECT COUNT(*) FROM coi_mgmt.pdf_answers")
    print(f"Total Chunks: {chunks_count}")
    print(f"Total Answers: {answers_count}")
    
    if chunks_count > 0:
        sample_chunks = await database.fetch_all("SELECT pdf_id, chunk_text FROM coi_mgmt.pdf_chunks LIMIT 2")
        print("\n--- Sample Chunks ---")
        for c in sample_chunks:
            print(f"PDF ID: {c['pdf_id']}\nText: {c['chunk_text'][:200]}...\n")
            
    if answers_count > 0:
        sample_answers = await database.fetch_all("SELECT pdf_id, question_text, answer_text FROM coi_mgmt.pdf_answers LIMIT 5")
        print("\n--- Sample Answers ---")
        for a in sample_answers:
            print(f"PDF ID: {a['pdf_id']}\nQ: {a['question_text']}\nA: {a['answer_text']}\n")
            
    await database.disconnect()

if __name__ == "__main__":
    asyncio.run(check())
