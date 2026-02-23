
from fastapi import APIRouter, HTTPException
from typing import List, Dict, Any
from app.services.rag_service import rag_service
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
        audit_dicts = [item.dict() for item in data.legal_audit]
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
        results = await rag_service.search_legal_citations(query, limit)
        return results
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
