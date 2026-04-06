
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
import json
from app.core.config import settings
from app.api.api_v1.endpoints import rag, extraction, generation, drafting_generator
from app.core.logger import activity_logger

app = FastAPI(title=settings.PROJECT_NAME)

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    errors = exc.errors()
    # Log the exact field and reason for the 422 error
    activity_logger.log_event("FastAPI", "VALIDATION_ERROR", "system", f"422 Detail: {errors}")
    print(f"--- 422 VALIDATION ERROR ---")
    print(json.dumps(errors, indent=2))
    return JSONResponse(status_code=422, content={"detail": errors})

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
app.include_router(drafting_generator.router, prefix=f"{settings.API_V1_STR}/drafting", tags=["Drafting"])

@app.get("/")
def read_root():
    return {"message": f"Welcome to {settings.PROJECT_NAME}"}
