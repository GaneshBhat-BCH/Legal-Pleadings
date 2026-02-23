
from langchain_openai import AzureOpenAIEmbeddings
from langchain_postgres import PGVector
from app.core.config import settings

# Initialize Embeddings
embeddings = AzureOpenAIEmbeddings(
    azure_deployment="text-embedding-3-large",
    openai_api_version="2023-05-15",
    azure_endpoint=settings.AZURE_OPENAI_EMBEDDING_ENDPOINT,
    api_key=settings.AZURE_OPENAI_EMBEDDING_API_KEY,
)

from sqlalchemy.ext.asyncio import create_async_engine

# Initialize Vector Store
# Create async engine with search_path in server_settings
engine = create_async_engine(
    settings.SQLALCHEMY_DATABASE_URI,
    connect_args={"server_settings": {"search_path": "Legal_Pleadings,public"}}
)

vector_store = PGVector(
    embeddings=embeddings,
    collection_name="legal_citations",
    connection=engine,
    use_jsonb=True,
    create_extension=False, # We handle this via setup_db.py or manual admin action
)

async def init_vector_store():
    """
    Initializes the vector store tables.
    Note: Requires 'vector' extension to be enabled in Postgres.
    """
    # PGVector in langchain-postgres handles table creation automatically 
    # if valid connection and permissions exist.
    pass
