
from pydantic import BaseModel, Field
from typing import List, Optional

class LegalCitation(BaseModel):
    law_cited: str = Field(..., description="Full name of the statute or case")
    citation_context: str = Field(..., description="The specific sentence where this law was used")
    associated_category: str = Field(..., description="The protected class or legal theory")
    legal_background: str = Field(..., description="Explanation of what this law requires")
    relevance_score: str = Field(..., description="High/Medium/Low relevance")

class LegalAuditResponse(BaseModel):
    legal_audit: List[LegalCitation]

class SearchResult(BaseModel):
    law_cited: str
    legal_background: str
    similarity_score: float
    citation_context: Optional[str] = None
    associated_category: Optional[str] = None
