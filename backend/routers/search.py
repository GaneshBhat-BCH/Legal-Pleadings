from fastapi import APIRouter, HTTPException, Depends
from backend.database import get_db
from backend.services.ai import get_embeddings
from backend.utils.logger import log_event
from pydantic import BaseModel
import json

router = APIRouter()

class SearchRequest(BaseModel):
    questions_answers: list[dict]

@router.post("/search")
async def search_documents(request: SearchRequest, db = Depends(get_db)):
    log_event("Search Module", "Search request received", "START")
    try:
        # 1. Prepare Query
        # Combine Q&A into text for Embedding AND Keyword search
        query_text = ""
        for item in request.questions_answers:
             # Flexible key access
             q = item.get("question_text") or item.get("question") or item.get("text") or ""
             a = item.get("answer_text") or item.get("answer") or ""
             query_text += f" {q} {a} " # Space separated for keywords
             
        if not query_text.strip():
            log_event("Search Module", "Empty search query", "WARNING")
            raise HTTPException(status_code=400, detail="Empty search query")

        # ... (logic remains) ...
        
        # Helper: Process a list of DB rows into Verified Forensic Candidates
        async def get_verified_candidates(db_rows):
            processed_candidates = []
            for row in db_rows:
                pdf_id = row["pdf_id"]
                query_answers = "SELECT question_id, question_text, answer_text FROM coi_mgmt.pdf_answers WHERE pdf_id = :pdf_id"
                stored_answers = await db.fetch_all(query_answers, values={"pdf_id": pdf_id})
                
                stored_map = { str(rec["question_id"]): rec["answer_text"] for rec in stored_answers }
                stored_map_text = { rec["question_text"].lower().strip(): rec["answer_text"] for rec in stored_answers }
                
                matches = []
                non_matches = []
                
                for item in request.questions_answers:
                    q_text = item.get("question_text") or item.get("question") or item.get("text") or "Unknown Question"
                    q_id = str(item.get("question_id", ""))
                    
                    # Try matching by ID first, then by text
                    found_answer = stored_map.get(q_id) or stored_map_text.get(q_text.lower().strip())
                    
                    if found_answer and found_answer != "N/A":
                        user_ref = item.get("answer_text") or item.get("answer") or ""
                        
                        # STRICT MATCHING LOGIC
                        # Normalize strings: lowercase and strip whitespace
                        norm_user = user_ref.strip().lower()
                        norm_pdf = found_answer.strip().lower()
                        
                        if norm_user == norm_pdf:
                            is_match = True
                            status_msg = "Match"
                            matches.append({"question": q_text, "pdf_answer": found_answer, "user_answer_ref": user_ref})
                        else:
                            is_match = False
                            status_msg = "Mismatch"
                            non_matches.append({"question": q_text, "pdf_answer": found_answer, "user_answer_ref": user_ref, "status": status_msg})
                    else:
                        non_matches.append({"question": q_text, "status": "Not Found in this PDF"})

                processed_candidates.append({
                    "pdf_id": pdf_id,
                    "pdf_name": row["file_name"],
                    "match_score_raw": len(matches) / len(request.questions_answers) if request.questions_answers else 0,
                    "relevance_details": {"vector": float(row["max_sim"]), "keyword_rank": float(row["max_rank"])},
                    "matched_qa": matches,
                    "unmatched_qa": non_matches,
                    "valid_match_count": len(matches)
                })
            
            verified = [c for c in processed_candidates if c["valid_match_count"] > 0]
            # If nothing verified, but we have high vector score, maybe keep them?
            # For now, let's just return what we have.
            verified.sort(key=lambda x: (x["valid_match_count"], x["match_score_raw"]), reverse=True)
            return verified

        # 2. STEP 1: PURE KEYWORD SEARCH (No Model Cost)
        log_event("Search Module", "Attempting Keyword-First search...", "PROGRESS")
        keyword_search_query = """
        SELECT pdf.file_name, pdf.pdf_id, 0 as max_sim, MAX(ts_rank(c.search_vector, plainto_tsquery('english', :query_text))) as max_rank
        FROM coi_mgmt.pdf_chunks c
        JOIN coi_mgmt.pdf_documents pdf ON c.pdf_id = pdf.pdf_id
        WHERE c.search_vector @@ plainto_tsquery('english', :query_text)
        GROUP BY pdf.file_name, pdf.pdf_id
        ORDER BY max_rank DESC LIMIT 10
        """
        results_kw = await db.fetch_all(keyword_search_query, values={"query_text": query_text})
        candidates = await get_verified_candidates(results_kw)
        search_method = "SQL Keyword (Free)"

        # 3. STEP 2: FALLBACK TO VECTOR SEARCH
        # Fallback if verified keyword matches represent FEWER THAN 3 unique PDFs
        if len(candidates) < 3:
            log_event("Search Module", f"Keyword search found only {len(candidates)} verified PDFs. Augmenting with Vectorization...", "PROGRESS")
            search_method = "Hybrid (Keyword + Vector Fallback)"
            query_embedding = await get_embeddings(query_text)
            embedding_str = str(query_embedding)
            
            search_query_vec = """
            WITH matches AS (
                SELECT pdf.file_name, pdf.pdf_id, 1 - (c.chunk_embedding <=> :embedding) as vector_sim,
                       ts_rank(c.search_vector, plainto_tsquery('english', :query_text)) as text_rank
                FROM coi_mgmt.pdf_chunks c
                JOIN coi_mgmt.pdf_documents pdf ON c.pdf_id = pdf.pdf_id
                WHERE 1 - (c.chunk_embedding <=> :embedding) > 0.5
            )
            SELECT pdf_id, file_name, MAX(vector_sim) as max_sim, MAX(text_rank) as max_rank
            FROM matches 
            GROUP BY pdf_id, file_name 
            ORDER BY max_sim DESC, max_rank DESC LIMIT 10
            """
            results_vec = await db.fetch_all(search_query_vec, values={"embedding": embedding_str, "query_text": query_text})
            
            # Identify which PDFs we already found via keyword to avoid redundant verification
            existing_pdf_ids = {str(c["pdf_id"]) for c in candidates} # Note: I'll add pdf_id to candidates below
            
            # Filter results_vec to only new PDFs
            new_results_vec = [r for r in results_vec if str(r["pdf_id"]) not in existing_pdf_ids]
            
            if new_results_vec:
                log_event("Search Module", f"Vector search found {len(new_results_vec)} NEW raw candidates.", "PROGRESS")
                vector_candidates = await get_verified_candidates(new_results_vec)
                candidates.extend(vector_candidates)
            
            log_event("Search Module", f"Verification complete. Final combined count: {len(candidates)} unique PDFs.", "SUCCESS")
        else:
            log_event("Search Module", f"Keyword search found {len(candidates)} verified PDFs. Skipping Vectorization.", "SUCCESS")
        
        final_results = candidates[:3]
        formatted_results = []
        for c in final_results:
             formatted_results.append({
                "pdf_name": c["pdf_name"],
                "match_score": f"{c['match_score_raw'] * 100:.1f}%",
                "search_method": search_method,
                "relevance_details": c["relevance_details"],
                "matched_qa": c["matched_qa"],
                "unmatched_qa": c["unmatched_qa"]
             })
            
        return {
            "search_method_used": search_method,
            "results": formatted_results
        }

    except Exception as e:
        print(f"Search Error: {e}")
        log_event("Search Module", f"Search Failed: {str(e)}", "ERROR")
        raise HTTPException(status_code=500, detail=str(e))
