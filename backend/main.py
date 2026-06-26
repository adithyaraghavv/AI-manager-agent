"""
PM Document Assistant - FastAPI Backend
Main application entry point
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import os
import mimetypes

from routers import templates, upload, chat, documents

# ─────────────────────────────────────────────
# App Initialization
# ─────────────────────────────────────────────
app = FastAPI(
    title="PM Document Assistant API",
    description="AI-powered chatbot for Project Managers to manage document templates",
    version="1.0.0",
)

# ─────────────────────────────────────────────
# CORS Middleware (allow React dev server)
# ─────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─────────────────────────────────────────────
# Ensure base directories exist at startup
# ─────────────────────────────────────────────
@app.on_event("startup")
async def startup_event():
    os.makedirs("../Templates", exist_ok=True)
    os.makedirs("../Clients", exist_ok=True)
    

# ─────────────────────────────────────────────
# Register Routers
# ─────────────────────────────────────────────
app.include_router(templates.router, prefix="/api/templates", tags=["Templates"])
app.include_router(upload.router,    prefix="/api/upload",    tags=["Upload"])
app.include_router(chat.router,      prefix="/api/chat",      tags=["Chat"])
app.include_router(documents.router, prefix="/api/documents", tags=["Documents"])

@app.get("/health")
def health_check():
    return {"status": "ok", "service": "PM Document Assistant"}
