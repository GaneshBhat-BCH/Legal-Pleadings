
import asyncio
import sys
import os

# Add backend to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.workflow import app

async def run_interactive():
    print("=== Legal Pleadings RAG Workflow ===")
    print("Type 'exit' or 'quit' to stop.\n")
    
    while True:
        question = input("\nEnter your legal question: ")
        if question.lower() in ["exit", "quit"]:
            break
            
        print(f"\n--- Starting Workflow for: '{question}' ---\n")
        
        inputs = {"question": question}
        
        try:
            # Stream the output from the graph
            # This yields a dictionary of the state update from each node
            async for output in app.astream(inputs):
                for node_name, state_update in output.items():
                    print(f"\n>> Finished Step: [{node_name}]")
                    
                    if node_name == "retrieve":
                        # logic to show retrieved docs if available in state
                        # Note: state_update contains the keys modified by the node
                        if "context" in state_update:
                            docs = state_update["context"]
                            print(f"   Action: Retrieved {len(docs)} documents.")
                            for i, doc in enumerate(docs):
                                source = doc.metadata.get('law_cited', 'Unknown')
                                snippet = doc.page_content.replace('\n', ' ')[:100]
                                print(f"   - Doc {i+1} ({source}): {snippet}...")
                                
                    elif node_name == "generate":
                        answer = state_update.get("answer", "No answer generated.")
                        print(f"   Action: Generated response.")
                        print(f"\nFINAL ANSWER:\n{answer}\n")
                        print("-" * 50)
                        
        except Exception as e:
            print(f"Error during execution: {e}")

if __name__ == "__main__":
    asyncio.run(run_interactive())
