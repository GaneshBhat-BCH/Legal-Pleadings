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

async def analyze_document_and_answer(text_content: str, questions_config: dict | list) -> dict:
    log_event("AI Service", "constructing prompt", "START")
    
    # Handle backward compatibility or list input
    if isinstance(questions_config, list):
        questions_list = questions_config
        global_instr = {}
        hms_policy = {}
        phs_policy = {}
    else:
        questions_list = questions_config.get("QUESTIONS", [])
        global_instr = questions_config.get("global_instructions", {})
        
        # Extract Ref Policies (handle both old and new structure just in case)
        ref_policies = questions_config.get("REFERENCE_POLICIES", questions_config)
        hms_policy = ref_policies.get("HMS_COI_Policy", {})
        phs_policy = ref_policies.get("PHS_COI_Policy", {})

    prompt = f"""
    You are a forensic document auditor. Your goal is to extract specific details from the document text provided below.
    
    DOCUMENT CONTENT:
    ~~~~~~~~~~~~~~~~~
    {text_content}
    ~~~~~~~~~~~~~~~~~
    
    YOUR TASK:
    Answer the following questions based on the document text.
    
    GLOBAL INSTRUCTIONS:
    {json.dumps(global_instr, indent=2)}

    REFERENCE POLICIES:
    HMS_COI_Policy: {json.dumps(hms_policy, indent=2)}
    PHS_COI_Policy: {json.dumps(phs_policy, indent=2)}

    QUESTIONS AND EXTRACTION PROMPTS:
    {json.dumps(questions_list, indent=2)}

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
                {"role": "system", "content": "You are a forensic auditor AI. Extract every possible detail. Do not be lazy. Never answer N/A if any relevant text exists. Follow specific prompts for each question."},
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
