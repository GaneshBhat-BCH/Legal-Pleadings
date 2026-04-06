
from typing import TypedDict, List
from langgraph.graph import StateGraph, END
from app.services.rag_service import retrieve_documents, generate_answer
from langchain_core.documents import Document

# --- LangGraph State ---
class GraphState(TypedDict):
    question: str
    documents: List[Document]
    answer: str

# --- Nodes ---
async def retrieve_node(state: GraphState):
    """
    Node to retrieve documents.
    """
    print("--- Node: Retrieve ---")
    question = state["question"]
    try:
        documents = await retrieve_documents(question)
    except Exception as e:
        print(f"Error in retrieval: {e}")
        documents = []
    return {"documents": documents}

async def generate_node(state: GraphState):
    """
    Node to generate answer.
    """
    print("--- Node: Generate ---")
    question = state["question"]
    documents = state["documents"]
    
    if not documents:
        return {"answer": "I could not retrieve any documents (Embedding/DB issue)."}
    
    answer = await generate_answer(question, documents)
    return {"answer": answer}

# --- Graph Definition ---
workflow = StateGraph(GraphState)

# Add nodes
workflow.add_node("retrieve", retrieve_node)
workflow.add_node("generate", generate_node)

# Add edges
workflow.set_entry_point("retrieve")
workflow.add_edge("retrieve", "generate")
workflow.add_edge("generate", END)

# Compile
app = workflow.compile()
