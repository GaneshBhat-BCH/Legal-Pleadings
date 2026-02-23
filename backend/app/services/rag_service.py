
from typing import List
from langchain_core.documents import Document
from app.db.vector_store import vector_store

# --- LangChain Logic ---
# This service uses LangChain components directly to perform tasks.

async def retrieve_documents(query: str, k: int = 4) -> List[Document]:
    """
    Retrieves relevant documents from the vector store using LangChain.
    """
    print(f"Service: Retrieving top {k} documents for query: '{query}'")
    
    # vector_store is a LangChain PGVector object
    docs = await vector_store.asimilarity_search(query, k=k)
    return docs

async def generate_answer(query: str, context: List[Document]) -> str:
    """
    Generates an answer using a Chat Model (LangChain).
    """
    from langchain_openai import AzureChatOpenAI
    from app.core.config import settings

    llm = AzureChatOpenAI(
        azure_deployment="gpt-5", # Ensure this matches your deployment
        openai_api_version="2025-01-01-preview",
        azure_endpoint=settings.AZURE_OPENAI_ENDPOINT,
        api_key=settings.AZURE_OPENAI_API_KEY,
        temperature=0.7,
    )

    # Simple prompt
    from langchain_core.prompts import ChatPromptTemplate
    
    prompt = ChatPromptTemplate.from_template("""
    Answer the question based ONLY on the following context.
    If the answer is not in the context, say "I don't know based on the provided documents."
    
    Context:
    {context}
    
    Question: 
    {question}
    """)
    
    chain = prompt | llm
    
    # Format context
    context_str = "\n\n".join([d.page_content for d in context])
    
    response = await chain.ainvoke({"context": context_str, "question": query})
    return response.content

async def ingest_legal_analysis(legal_audit: List[dict]) -> int:
    """
    Ingests legal audit list into the vector store.
    """
    documents = []
    for item in legal_audit:
        # Create content string
        content = f"Law: {item.get('law_cited', '')}\n" \
                  f"Background: {item.get('legal_background', '')}\n" \
                  f"Context: {item.get('citation_context', '')}"
        
        # Create metadata
        metadata = {
            "law_cited": item.get("law_cited"),
            "associated_category": item.get("associated_category"),
            "relevance_score": item.get("relevance_score"),
            "citation_context": item.get("citation_context")
        }
        
        documents.append(Document(page_content=content, metadata=metadata))
    
    if documents:
        print(f"Service: Adding {len(documents)} documents to vector store...")
        # Add documents to vector store
        await vector_store.aadd_documents(documents)
        return len(documents)
    return 0
