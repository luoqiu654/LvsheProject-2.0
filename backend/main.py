from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.api.routes import router
from backend.api.contract_routes import router as contract_router
from backend.api.expert_routes import router as expert_router
from backend.config import PROJECT_ROOT, settings


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
app.include_router(contract_router)
app.include_router(expert_router)


@app.get("/health")
async def health() -> dict:
    return {
        "ok": True,
        "app_name": settings.app_name,
        "env": settings.app_env,
    }


# ===== 生产环境：前端静态文件服务（Docker 部署时自动启用） =====
_FRONTEND_DIST = PROJECT_ROOT / "frontend-next" / "dist"


@app.get("/")
async def root():
    """根路径：生产环境返回前端页面，开发环境返回 API 信息。"""
    index = _FRONTEND_DIST / "index.html"
    if index.exists():
        return FileResponse(str(index))
    return {
        "message": "Welcome to LvsheProject API",
        "docs": "/docs",
        "health": "/health",
    }


if _FRONTEND_DIST.exists():
    # 挂载 Vite 构建产物中的静态资源
    _assets_dir = _FRONTEND_DIST / "assets"
    if _assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=str(_assets_dir)), name="frontend-assets")

    # SPA 路由兜底：非 API 路径返回 index.html（支持 React Router 客户端路由）
    @app.get("/{full_path:path}")
    async def spa_fallback(full_path: str):
        # 尝试返回实际文件（如 favicon.svg, icons.svg 等）
        file_path = _FRONTEND_DIST / full_path
        if file_path.is_file():
            return FileResponse(str(file_path))
        # SPA 路由：返回 index.html
        index = _FRONTEND_DIST / "index.html"
        if index.exists():
            return FileResponse(str(index))
        return {"error": "Frontend not built"}
