from openai import AsyncAzureOpenAI
import os
import json
from dotenv import load_dotenv
from pathlib import Path
from backend.utils.logger import log_event

# Load .env
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

# Configuration
api_key = os.getenv("AZURE_OPENAI_API_KEY")
# Handle potential full URL in env var
raw_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT", "")
if "/openai" in raw_endpoint:
    AOAI_ENDPOINT = raw_endpoint.split("/openai")[0]
else:
    AOAI_ENDPOINT = raw_endpoint

GPT_DEPLOYMENT = "gpt-5"
EMBEDDING_DEPLOYMENT = "text-embedding-3-large"
API_VERSION = "2025-01-01-preview"

client = AsyncAzureOpenAI(
    azure_endpoint=AOAI_ENDPOINT,
    api_key=api_key,
    api_version=API_VERSION
)

async def get_embeddings(input_data: str | list[str]):
    """
    Fetches embeddings for a single string or a list of strings.
    Uses OpenAI batch API for performance when a list is provided.
    """
    if not input_data:
        return []

    # Ensure input is a list for the API call
    is_single = isinstance(input_data, str)
    api_input = [input_data] if is_single else input_data

    response = await client.embeddings.create(
        input=api_input,
        model=EMBEDDING_DEPLOYMENT,
        dimensions=1536
    )
    
    if is_single:
        return response.data[0].embedding
    else:
        return [item.embedding for item in response.data]

async def analyze_document_and_answer(text_content: str, questions: list[dict]) -> dict:
    log_event("AI Service", "constructing prompt", "START")
    
    prompt = f"""
    You are a forensic document auditor. Your goal is to extract specific details from the document text provided below.
    
    DOCUMENT CONTENT:
    ~~~~~~~~~~~~~~~~~
    {text_content}
    ~~~~~~~~~~~~~~~~~
    
    YOUR TASK:
    Answer the following questions based on the document text.
    
    RULES:
    1.  **AGGRESSIVE EXTRACTION**: Maps names, roles, numerical values (equity, compensation), and relationships even if they are mentioned indirectly or in a standard "legalese" format.
    2.  **INFERENCE IS REQUIRED**: If the document allows for a reasonable deduction (e.g. "Founder" implies "Equity holder"), state it. 
    3.  **NO "N/A"**: Do NOT return "N/A" simply because the exact wording isn't found. Return the closest related information found. Only return "N/A" if the document is completely silent on the topic.
    4.  **EXTREME BREVITY**: Answers must be specific and concise. 
        *   **GOOD**: "25% equity", "$24,000/year", "Co-founder"
        *   **BAD**: "The researcher holds a 25% equity stake which will dilute over time..."
        *   Start with the direct answer. Avoid full sentences unless necessary for context.
    5.  **FORMAT**: Return a JSON object with a key "answers" containing a list of objects.
    
    QUESTIONS TO ANSWER (Use these IDs):
    {json.dumps(questions, indent=2)}

    OUTPUT FORMAT (JSON):
    {{
        "answers": [
            {{ "question_id": <int>, "question_text": "<str>", "answer_text": "<extracted detail or inference>" }},
            ...
        ]
    }}
    """
    
    log_event("AI Service", "Analysis request sending to GPT-5", "PENDING")
    
    try:
        response = await client.chat.completions.create(
            model=GPT_DEPLOYMENT,
            messages=[
                {"role": "system", "content": "You are a forensic auditor AI. Extract every possible detail. Do not be lazy. Never answer N/A if any relevant text exists."},
                {"role": "user", "content": prompt}
            ],
            response_format={"type": "json_object"}
        )
        
        content = response.choices[0].message.content
        usage = response.usage
        
        usage_data = {
            "prompt_tokens": usage.prompt_tokens,
            "completion_tokens": usage.completion_tokens,
            "total_tokens": usage.total_tokens
        }
        
        log_event("AI Service", f"Response received from GPT-5. Usage: {usage.total_tokens}", "SUCCESS")
             
        data = json.loads(content)
        return {
            "answers": data.get("answers", []),
            "usage": usage_data
        }
    except Exception as e:
        log_event("AI Service", f"Analysis failed: {str(e)}", "ERROR")
        print(f"AI ERROR: {e}")
        return {"answers": [], "usage": {}}
