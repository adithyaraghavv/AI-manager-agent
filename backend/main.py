"""
PM Document Assistant - FastAPI Backend
Main application entry point
"""

import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routers import templates, upload, chat, documents

app = FastAPI(
    title="PM Document Assistant API",
    description="AI-powered chatbot for Project Managers to manage document templates",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173", "http://127.0.0.1:5500"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup_event():
    from services.storage_service import TEMPLATES_DIR, CLIENTS_DIR
    os.makedirs(TEMPLATES_DIR, exist_ok=True)
    os.makedirs(CLIENTS_DIR, exist_ok=True)


app.include_router(templates.router, prefix="/api/templates", tags=["Templates"])
app.include_router(upload.router,    prefix="/api/upload",    tags=["Upload"])
app.include_router(chat.router,      prefix="/api/chat",      tags=["Chat"])
app.include_router(documents.router, prefix="/api/documents", tags=["Documents"])


@app.get("/health")
def health_check():
    return {"status": "ok", "service": "PM Document Assistant v2"}
