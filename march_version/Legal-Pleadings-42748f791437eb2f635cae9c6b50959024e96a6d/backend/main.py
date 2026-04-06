from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import os
from pathlib import Path
from backend.database import database

# Load .env from the same directory as this file
env_path = Path(__file__).parent / ".env"
load_dotenv(dotenv_path=env_path)

app = FastAPI(title="Legal Pleadings API")

# CORS
origins = [
    "http://localhost:5173",
    "http://localhost:3000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup():
    await database.connect()

@app.on_event("shutdown")
async def shutdown():
    await database.disconnect()

@app.get("/")
def read_root():
    return {"message": "Welcome to the Legal Pleadings API"}
