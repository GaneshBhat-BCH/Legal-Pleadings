
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.api.api_v1.endpoints import rag, extraction, generation

app = FastAPI(title=settings.PROJECT_NAME)

# CORS structure
origins = [
    "http://localhost",
    "http://localhost:8080",
    "http://localhost:5173", # Vite default
    "http://localhost:3000", # React default
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include Routers
app.include_router(rag.router, prefix=f"{settings.API_V1_STR}/rag", tags=["RAG"])
app.include_router(extraction.router, prefix=f"{settings.API_V1_STR}/extraction", tags=["Extraction"])
app.include_router(generation.router, prefix=f"{settings.API_V1_STR}/generation", tags=["Generation"])

@app.get("/")
def read_root():
    return {"message": f"Welcome to {settings.PROJECT_NAME}"}
