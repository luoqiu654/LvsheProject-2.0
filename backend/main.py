from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.routes import router
from backend.config import settings


app = FastAPI(
    title="LvsheProject API",
    description="法律 AI Agent 系统：LLM Gateway + RAG + Agent + Skills + Memory + GUI Agent + Multi-Agent",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.get("/health")
async def health() -> dict:
    return {
        "ok": True,
        "app_name": settings.app_name,
        "env": settings.app_env,
    }


@app.get("/")
async def root() -> dict:
    return {
        "message": "Welcome to LvsheProject API",
        "docs": "/docs",
        "health": "/health",
    }
