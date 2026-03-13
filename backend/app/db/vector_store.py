
from langchain_openai import AzureOpenAIEmbeddings
from langchain_postgres import PGVector
from app.core.config import settings
import urllib.parse

# Initialize Embeddings
embeddings = AzureOpenAIEmbeddings(
    azure_deployment="text-embedding-3-large",
    openai_api_version="2023-05-15",
    azure_endpoint=settings.AZURE_OPENAI_EMBEDDING_ENDPOINT,
    api_key=settings.AZURE_OPENAI_EMBEDDING_API_KEY,
    request_timeout=1200, # Standardized 20-minute timeout
)

from sqlalchemy.ext.asyncio import create_async_engine

# Build connection URI with search_path forced to Legal_Pleadings
# This ensures PGVector CREATE TABLE statements land in the correct schema
encoded_password = urllib.parse.quote_plus(settings.DB_PASSWORD)
_base_uri = (
    f"postgresql+asyncpg://{settings.DB_USER}:{encoded_password}"
    f"@{settings.DB_HOST}:{settings.DB_PORT}/{settings.DB_NAME}"
)

engine = create_async_engine(
    _base_uri,
    connect_args={
        "server_settings": {
            "search_path": "Legal_Pleadings,public"
        }
    }
)

vector_store = PGVector(
    embeddings=embeddings,
    collection_name="legal_citations",
    connection=engine,
    use_jsonb=True,
    create_extension=False,
)

async def init_vector_store():
    """
    Initializes the vector store tables inside Legal_Pleadings schema.
    Requires: 'vector' extension enabled and Legal_Pleadings schema created first.
    """
    pass
