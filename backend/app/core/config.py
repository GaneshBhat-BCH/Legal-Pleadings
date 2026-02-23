
from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache
from pathlib import Path

# Calculate root .env path (4 levels up from backend/app/core/config.py)
ROOT_ENV_FILE = str(Path(__file__).resolve().parent.parent.parent.parent / ".env")

class Settings(BaseSettings):
    API_V1_STR: str = "/api/v1"
    PROJECT_NAME: str = "Legal Pleadings API"
    
    # Azure OpenAI
    AZURE_OPENAI_API_KEY: str
    AZURE_OPENAI_ENDPOINT: str
    AZURE_OPENAI_EMBEDDING_ENDPOINT: str
    AZURE_OPENAI_EMBEDDING_API_KEY: str # Added for separate embedding resource
    OPENAI_API_VERSION: str = "2025-01-01-preview"
    
    # Database
    DB_USER: str
    DB_PASSWORD: str
    DB_HOST: str
    DB_NAME: str
    DB_PORT: str = "5432"

    @property
    def SQLALCHEMY_DATABASE_URI(self) -> str:
        # Handle special characters in password
        import urllib.parse
        encoded_password = urllib.parse.quote_plus(self.DB_PASSWORD)
        return f"postgresql+asyncpg://{self.DB_USER}:{encoded_password}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"

    @property
    def PSYCOPG_DATABASE_URI(self) -> str:
         # For synchronous operations if needed (e.g. initial connection checks or synchronous langchain)
        import urllib.parse
        encoded_password = urllib.parse.quote_plus(self.DB_PASSWORD)
        return f"postgresql+psycopg://{self.DB_USER}:{encoded_password}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"

    model_config = SettingsConfigDict(
        env_file=ROOT_ENV_FILE,
        case_sensitive=True,
        extra="ignore"
    )

@lru_cache()
def get_settings():
    # Pass _env_file explicitly to guarantee it loads from the absolute path
    return Settings(_env_file=ROOT_ENV_FILE)

settings = get_settings()
