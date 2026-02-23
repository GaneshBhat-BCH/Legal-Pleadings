
from fastapi import APIRouter, HTTPException
from typing import List, Dict, Any
from app.services import rag_service
from app.models.schemas import SearchResult, LegalAuditResponse

router = APIRouter()

@router.post("/ingest", response_model=Dict[str, int])
async def ingest_analysis(data: LegalAuditResponse):
    """
    Ingest legal analysis results into the vector store.
    """
    try:
        # Convert Pydantic models to dicts for the service
        # (The service expects list of dicts based on current implementation, 
        #  or we could update service to take pydantic models)
        audit_dicts = [item.model_dump() for item in data.legal_audit]  # Pydantic v2
        count = await rag_service.ingest_legal_analysis(audit_dicts)
        return {"ingested_count": count}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/search", response_model=List[SearchResult])
async def search_citations(query: str, limit: int = 5):
    """
    Semantic search for legal citations.
    """
    try:
        from app.db.vector_store import vector_store
        docs_and_scores = await vector_store.asimilarity_search_with_score(query, k=limit)
        
        results = []
        for doc, score in docs_and_scores:
            results.append(SearchResult(
                law_cited=doc.metadata.get("law_cited", "Unknown"),
                legal_background=doc.page_content,
                similarity_score=float(score),
                citation_context=doc.metadata.get("citation_context"),
                associated_category=doc.metadata.get("associated_category")
            ))
        return results
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
