# ===== Stage 1: Build Frontend =====
FROM node:22-alpine AS frontend-builder
WORKDIR /build

# 先复制依赖文件，利用 Docker 层缓存
COPY frontend-next/package.json frontend-next/package-lock.json ./
RUN npm ci

# 复制源码并构建
COPY frontend-next/ ./
RUN npm run build


# ===== Stage 2: Python Backend =====
FROM python:3.14-slim AS backend

# 安装系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# 安装 uv（Python 包管理器）
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# 先复制依赖文件，利用 Docker 层缓存
COPY pyproject.toml uv.lock ./

# 创建虚拟环境并安装依赖
RUN uv venv && uv sync --no-dev --frozen

# 复制项目代码
COPY backend/ ./backend/
COPY data/raw/ ./data/raw/
COPY skills/ ./skills/

# 复制前端构建产物
COPY --from=frontend-builder /build/dist ./frontend-next/dist

# 创建数据目录
RUN mkdir -p data/vector_store data/memory data/uploads output/contract_review

# 环境变量
ENV PYTHONPATH=/app
ENV APP_ENV=production
ENV VIRTUAL_ENV=/app/.venv
ENV PATH="/app/.venv/bin:$PATH"

# 暴露端口
EXPOSE 8000

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# 启动命令
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
