from fastapi import APIRouter, HTTPException, Depends
from backend.database import get_db
from backend.services.ai import analyze_document_and_answer, get_embeddings
from backend.questions import QUESTIONS
from backend.utils.chunking import chunk_text
from backend.utils.logger import log_event
from pydantic import BaseModel
import uuid

router = APIRouter()

class UploadRequest(BaseModel):
    file_name: str
    pdf_text: str
    user_text: str = ""

@router.post("/upload")
async def upload_file(
    request: UploadRequest,
    db = Depends(get_db)
):
    log_event("Upload Module", "Upload request received", "START")
    try:
        # 1. Insert into DB (pdf_documents)
        # Using "text-input" as placeholder for file_path since we don't save to disk
        query_doc = """
        INSERT INTO coi_mgmt.pdf_documents (file_name, file_path)
        VALUES (:file_name, :file_path)
        RETURNING pdf_id
        """
        
        pdf_id = await db.fetch_val(query_doc, values={"file_name": request.file_name, "file_path": "text-input"})
        log_event("Upload Module", f"Document record created (ID: {pdf_id})", "PROGRESS")
             
        # Combine PDF Text + User Input
        full_context = f"User Input:\n{request.user_text}\n\nDocument Content:\n{request.pdf_text}"
        
        # 2. Get Answers (AI)
        ai_result = await analyze_document_and_answer(full_context, QUESTIONS)
        answers_data = ai_result.get("answers", [])
        token_usage = ai_result.get("usage", {})
        
        # 3. Preparation for Processing
        answers_result = []
        texts_to_embed = []
        
        for q_def in QUESTIONS:
            ans_text = "N/A"
            for item in answers_data:
                if item.get("question_id") == q_def["id"] or item.get("question_text") == q_def["text"]:
                    ans_text = item.get("answer_text", "N/A")
                    break
            
            answers_result.append({
                "question_id": q_def["id"],
                "question_text": q_def["text"],
                "answer_text": ans_text
            })
            texts_to_embed.append(ans_text)

        # 4. Batch Embeddings for Answers
        all_embeddings = await get_embeddings(texts_to_embed)
        
        # 5. Store Answers in Relational DB
        query_ans = """
        INSERT INTO coi_mgmt.pdf_answers (pdf_id, question_id, question_text, answer_text, answer_embedding)
        VALUES (:pdf_id, :question_id, :question_text, :answer_text, :answer_embedding)
        """
        ans_values = []
        for i, item in enumerate(answers_result):
            ans_values.append({
                "pdf_id": pdf_id,
                "question_id": item["question_id"],
                "question_text": item["question_text"],
                "answer_text": item["answer_text"],
                "answer_embedding": str(all_embeddings[i])
            })
        
        if ans_values:
            await db.execute_many(query_ans, values=ans_values)
            
        log_event("Upload Module", "AI Analysis & Answer Storage complete", "PROGRESS")
        
        # 6. RAG Vectorization (Structured Answers Only)
        chunks_to_index = []
        if request.user_text.strip():
             chunks_to_index.append(f"General Context / Instructions: {request.user_text}")
             
        for item in answers_result:
            if item["answer_text"] != "N/A":
                chunks_to_index.append(f"Question: {item['question_text']}\nAnswer: {item['answer_text']}")

        # 7. Batch Embeddings for Chunks
        if chunks_to_index:
            chunk_vectors = await get_embeddings(chunks_to_index)
            
            query_chunk = """
            INSERT INTO coi_mgmt.pdf_chunks (pdf_id, chunk_text, chunk_embedding, search_vector)
            VALUES (:pdf_id, :chunk_text, :chunk_embedding, to_tsvector('english', :chunk_text))
            """
            chunk_values = []
            for i, chunk in enumerate(chunks_to_index):
                chunk_values.append({
                    "pdf_id": pdf_id,
                    "chunk_text": chunk,
                    "chunk_embedding": str(chunk_vectors[i])
                })
            
            await db.execute_many(query_chunk, values=chunk_values)
            
        log_event("Upload Module", f"Processing Complete. {len(chunks_to_index)} structured chunks indexed.", "SUCCESS")
        
        return {
            "status": "success", 
            "pdf_id": str(pdf_id), 
            "extracted_text_preview": request.pdf_text[:200], 
            "answers": answers_result,
            "chunks_created": len(chunks_to_index),
            "token_usage": token_usage
        }
        
    except Exception as e:
        print(f"Error: {e}")
        log_event("Upload Module", f"Error: {str(e)}", "ERROR")
        raise HTTPException(status_code=500, detail=str(e))
