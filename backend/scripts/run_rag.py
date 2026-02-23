
import asyncio
import sys
import os

# Add backend to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.workflow import app

async def run_rag(query: str = "What is the legal background for Chapter 151B?"):
    print(f"=== Starting RAG Pipeline for query: '{query}' ===\n")
    
    inputs = {"question": query}
    
    try:
        # Stream the output from the graph
        async for output in app.astream(inputs):
            for node_name, state_update in output.items():
                if node_name == "retrieve":
                    print("[Stage 1/2]: Retrieval Complete")
                    if "context" in state_update:
                        print(f"           Found {len(state_update['context'])} relevant documents.")
                                
                elif node_name == "generate":
                    print("[Stage 2/2]: Generation Complete")
                    answer = state_update.get("answer", "No answer generated.")
                    print("-" * 50)
                    print(f"ANSWER:\n{answer}")
                    print("-" * 50)
                        
    except Exception as e:
        print(f"\n[Error]: Workflow execution failed: {e}")

if __name__ == "__main__":
    # Allow query from command line
    default_query = "What is the legal background for Chapter 151B?"
    target_query = sys.argv[1] if len(sys.argv) > 1 else default_query
    
    asyncio.run(run_rag(target_query))
    print("\n=== Pipeline Execution Finished ===")
