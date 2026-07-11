# LvsheProject - 法律 AI Agent 系统

> 基于 FastAPI + React 18 的全栈法律 AI 智能体系统 | 多智能体法庭模拟 + RAG + 多供应商 LLM 网关

## 项目亮点

- **多供应商 LLM 统一网关**：通过 `LLM_PROVIDER` 环境变量一键切换智谱AI / 百炼(通义千问) / 任意 OpenAI 兼容接口，业务代码零改动
- **多智能体法庭模拟**：参考 CrewAI / CAMEL 设计理念，LangGraph 编排「1 主 Agent + 3 子 Agent」真实法庭全流程（开庭→证据梳理→用户追问→多轮辩论→判决→打回检查），子 Agent 自主调用工具检索法律条文
- **端水判决自动打回**：法官判决无明确胜负时自动打回重判，关键证据缺失时向用户追问，拒绝和稀泥
- **Agent Memory 记忆系统**：对话前后自动检索和提取用户记忆，侧边栏展示历史记忆条目
- **Agent Skills 技能系统**：自动匹配并注入技能（合同风险审查 / 法律检索 / 法律咨询）
- **GUI Agent 浏览器自动化**：用户消息含 URL 时自动浏览网页，提取内容并智能总结
- **RAG 法律依据检索**：ChromaDB + HyDE + Hybrid Search，每个子 Agent 均集成 RAG 检索
- **三模地图 + 360° 旋转 + 俯视调节**：高德 / OpenFreeMap / MapTiler 三引擎自由切换
- **视觉 AI 流水线**：OCR → 文本诊断 → 图像生成端到端合同诊疗
- **Framer Motion + tsparticles 动效**：粒子背景、3D 悬停、全屏开场动画

## 系统架构

### 后端 (Python >=3.14, FastAPI)
- **LLM Gateway**: LiteLLM 统一接入多供应商，支持文本 / 视觉 / 图像生成三类模型
  - 智谱AI：GLM-4.7-Flash / GLM-4.6 / GLM-5.2 / GLM-OCR / GLM-Image
  - 百炼：qwen-turbo / qwen-plus / qwen-max / qwen-vl-max
  - 通用：任何 OpenAI 兼容接口（OpenAI / DeepSeek / Moonshot 等）
- **RAG 引擎**: ChromaDB + HashEmbedding + Query Transform + HyDE + Hybrid Search
- **Graph RAG**: Neo4j 图谱检索（案件-法条关联，可选）
- **Agent**: LangGraph 自主 Agent（plan→tool→final 模式）
- **多智能体**: 1 主 Agent + 3 子 Agent（法官 / 原告 / 被告），LangGraph 状态图驱动
- **合同诊疗**: 视觉AI流水线（OCR→文本诊断→图像生成）
- **Memory**: 本地 JSON 存储 + Mem0 适配器

### 前端 (React 18 + TypeScript + Vite + Tailwind v4)
- Zustand 状态管理 + React Router 6
- SSE 流式响应 + Markdown 渲染
- 毛玻璃 UI 设计 + Framer Motion 动画 + tsparticles 粒子背景

## 功能模块

### 1. 智能咨询
- SSE 流式聊天，支持多轮对话和文件上传
- AI 思考过程折叠展示（reasoning_content 与 content 分离）
- RAG 法律知识库增强
- Agent Memory：对话前后自动检索和提取用户记忆
- Agent Skills：自动匹配并注入技能
- GUI Agent：消息含 URL 时自动浏览网页并总结

### 2. 合同诊疗
- 视觉AI流水线：上传文档→OCR识别→文本诊断→图像生成
- 支持 Word/PDF/PNG 文档
- 风险点三色编码（高/中/低）
- 批注文档预览 + 下载

### 3. 专家会诊（法庭模拟）
- 审判长开场→原告陈述→被告答辩→多轮辩论→法官追问→最终判决
- 法官自主选择追问时机，原被告回答"不清楚"时向用户追问
- 判决打回机制：端水/无理由判决自动打回重判
- 子 Agent 自主调用 law_search 工具检索法律条文
- AI 思考过程折叠展示

### 4. 地图浏览
- 高德 / OpenFreeMap / MapTiler 三引擎自由切换
- 360° 旋转拨盘 + 0-60° 俯视角度调节
- 类别筛选 + 搜索 + 详情卡片
- 模式切换时保持中心坐标和缩放级别

### 5. 放松模式
- 全屏背景图轮播 + 毛玻璃控制面板
- 背景音乐播放控制

## 快速开始

### 环境要求
- Python >=3.14（推荐用 [uv](https://github.com/astral-sh/uv) 管理）
- Node.js >=18
- Neo4j（可选，Graph RAG 用）

### 本地开发

```bash
# 后端
uv venv
uv pip install -e .

# 前端
cd frontend-next
npm install

# 配置环境变量
cp .env.example .env
# 编辑 .env 填入 LLM API Key
```

```powershell
# 一键启动（推荐）
.\start.ps1

# 或手动启动
# 后端
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8001

# 前端（另一个终端）
cd frontend-next
npm run dev
```

访问 http://localhost:5173

### LLM 供应商切换

项目支持多供应商无缝切换，只需修改 `.env` 中的 `LLM_PROVIDER` 和对应 API Key：

| 供应商 | LLM_PROVIDER | 环境变量 | 模板文件 |
|--------|-------------|---------|---------|
| 智谱AI | `zhipu` | `ZHIPU_API_KEY` | `.env.example.zhipu` |
| 百炼/通义千问 | `dashscope` | `DASHSCOPE_API_KEY` | `.env.example.dashscope` |
| 通用OpenAI兼容 | `openai` | `OPENAI_COMPAT_API_KEY` | `.env.example.openai` |

```bash
# 示例：切换到百炼
cp .env.example.dashscope .env
# 编辑 .env 填入 DASHSCOPE_API_KEY
```

切换供应商后无需修改任何业务代码，LLM Gateway 自动路由到对应供应商的 API。

### 角色专用模型配置（可选）

法庭模拟中的不同角色可指定不同模型（留空则使用默认模型）：

```bash
# .env 中配置
MODEL_SPEECH=glm-4.7-flash     # 陈述/回答（需要思考过程展示）
MODEL_DECISION=glm-4.6         # 法官追问决策（需要稳定 JSON）
MODEL_VERDICT=glm-5.2          # 最终判决（需要强推理）
```

## 容器化部署

### 镜像构建

```bash
# 构建镜像（多阶段构建：前端编译 + 后端打包）
docker build -t lvshe-project .

# 查看镜像大小
docker images lvshe-project
```

**构建参数说明**：
- 镜像基于 `python:3.14-slim`，包含完整后端运行环境
- Stage 1 使用 `node:22-alpine` 编译前端（Vite build → dist/）
- Stage 2 使用 uv 安装 Python 依赖，复制前端构建产物
- 最终镜像包含前后端，单容器部署

### 容器运行

**方式一：docker run**

```bash
# 准备环境变量
cp .env.example .env
# 编辑 .env 填入 LLM API Key

# 运行容器
docker run -d \
  --name lvshe-app \
  -p 8000:8000 \
  --env-file .env \
  -v lvshe-vector-store:/app/data/vector_store \
  -v lvshe-memory:/app/data/memory \
  -v lvshe-uploads:/app/data/uploads \
  -v lvshe-output:/app/output \
  --restart unless-stopped \
  lvshe-project
```

**方式二：docker-compose（推荐）**

```bash
# 准备环境变量
cp .env.example .env
# 编辑 .env 填入 LLM API Key

# 启动服务
docker compose up -d

# 查看日志
docker compose logs -f lvshe

# 停止服务
docker compose down
```

**附带 Neo4j（Graph RAG）启动**：

```bash
docker compose --profile graph-rag up -d
```

### 环境变量配置

容器通过 `--env-file .env` 或 `docker-compose.yml` 中的 `env_file` 注入环境变量。必须配置的变量：

| 变量 | 说明 | 示例 |
|------|------|------|
| `LLM_PROVIDER` | LLM 供应商 | `zhipu` / `dashscope` / `openai` |
| `ZHIPU_API_KEY` | 智谱AI 密钥（选择 zhipu 时） | `xxx.xxx` |
| `DASHSCOPE_API_KEY` | 百炼密钥（选择 dashscope 时） | `sk-xxx` |
| `OPENAI_COMPAT_API_KEY` | OpenAI兼容密钥（选择 openai 时） | `sk-xxx` |

其他可选配置（Neo4j、MinIO、图像 RAG 等）参见 `.env.example`。

### 注意事项及常见问题

**1. 镜像构建时间较长**
- 首次构建需下载 Python 依赖（含 PyTorch、ChromaDB 等），约 10-15 分钟
- Docker 层缓存机制使后续构建更快（仅重新构建变更层）

**2. 容器内无法连接 LLM API**
- 检查 `.env` 中 `LLM_PROVIDER` 与 API Key 是否匹配
- 智谱AI：确认 `ZHIPU_API_KEY` 有效
- 百炼：确认 `DASHSCOPE_API_KEY` 有效且已开通对应模型
- 使用 `docker compose logs lvshe` 查看错误日志

**3. 数据持久化**
- 向量库、记忆、上传文件、合同审查输出通过 Docker Volume 持久化
- 删除容器不会丢失数据，需显式删除 Volume：`docker volume rm lvshe-vector-store`

**4. Graph RAG（Neo4j）连接**
- 默认不启动 Neo4j，使用 `--profile graph-rag` 启动
- `.env` 中设置 `GRAPH_RAG_ENABLED=true` 和 `NEO4J_URI=bolt://neo4j:7687`

**5. 端口冲突**
- 默认占用 8000 端口，可通过 `docker compose.yml` 中的 `ports` 修改
- Neo4j 占用 7474（Browser）和 7687（Bolt）

**6. GPU 支持（可选）**
- 如需 GPU 加速 PyTorch 推理，在 `docker-compose.yml` 中添加：
  ```yaml
  deploy:
    resources:
      reservations:
        devices:
          - driver: nvidia
            count: all
            capabilities: [gpu]
  ```

## 技术栈

| 层 | 技术 |
|---|------|
| 后端 | FastAPI + LangGraph + LiteLLM + ChromaDB + Neo4j |
| 前端 | React 18 + TypeScript + Vite + Tailwind v4 + Zustand + Framer Motion + tsparticles |
| 地图 | MapTiler + OpenFreeMap + 高德地图 JS API 2.0 + maplibre-gl |
| LLM | 智谱AI / 百炼(通义千问) / 任意 OpenAI 兼容接口 |
| 容器 | Docker + docker-compose |
| 流式 | SSE (Server-Sent Events) |

## 项目结构

```
LvsheProject/
├── backend/
│   ├── api/
│   │   ├── routes.py              # 主路由（chat/rag/agent/memory等）
│   │   ├── contract_routes.py     # 合同诊疗路由
│   │   ├── expert_routes.py       # 专家会诊路由
│   │   └── schemas.py             # Pydantic 模型
│   ├── core/
│   │   ├── llm_gateway.py         # 多供应商 LLM 统一网关
│   │   ├── rag.py                 # RAG 引擎
│   │   ├── agents.py              # LangGraph 自主 Agent
│   │   ├── court_agents.py        # 法庭子 Agent（法官/原告/被告）
│   │   ├── court_orchestrator.py  # 法庭主编排器（LangGraph）
│   │   ├── multi_agents.py        # 法庭模拟器（兼容保留）
│   │   ├── contract_pipeline.py   # 合同诊疗流水线
│   │   ├── memory.py              # 记忆系统
│   │   ├── skills.py              # 技能系统
│   │   ├── gui_agent.py           # GUI Agent
│   │   └── ...
│   ├── config.py                  # 配置中心（多供应商支持）
│   └── main.py                    # FastAPI 入口
├── frontend-next/
│   ├── src/
│   │   ├── pages/                 # 7个页面
│   │   ├── components/            # 组件
│   │   ├── stores/                # Zustand 状态
│   │   ├── api/                   # API 客户端
│   │   └── data/                  # 数据文件
│   └── package.json
├── data/                          # 法律知识库 + 向量库
├── skills/                        # Agent Skills 定义
├── Dockerfile                     # 多阶段容器构建
├── docker-compose.yml             # 容器编排
├── .env.example                   # 环境变量模板（默认智谱AI）
├── .env.example.zhipu             # 智谱AI 配置模板
├── .env.example.dashscope         # 百炼/通义千问 配置模板
├── .env.example.openai            # 通用 OpenAI 兼容 配置模板
├── start.ps1                      # 一键启动脚本
└── pyproject.toml                 # Python 项目配置
```

## 版本历史
- **v3.5** - 多供应商 LLM 适配 + 容器化部署 + 版本控制优化
  - LLM Gateway 重构：支持智谱AI / 百炼 / 通用 OpenAI 兼容接口一键切换
  - `LLM_PROVIDER` 环境变量路由，业务代码零改动
  - 角色专用模型可配置（MODEL_SPEECH / MODEL_DECISION / MODEL_VERDICT）
  - 多套 .env 模板文件（zhipu / dashscope / openai）
  - Dockerfile 多阶段构建 + docker-compose 编排
  - README 重写，专注项目功能与技术亮点
- **v3.4** - Agent Skills / Memory / GUI Agent / Autonomous Agent 全面集成
  - 四大功能深度融入现有页面，不新增独立页面
  - 专家会诊思考面板修复、法官端水判决打回、首页动效、地图 pitch 调节
- **v3.3** - 专家会诊多 agent 重构 + 地图 360° 旋转 + 首页动效 + chat 加固
- **v3.2** - 思考过程显示优化 + 文件视觉兜底 + 专家会诊流程优化
- **v3.1** - 高德地图快速模式 + 法官追问重构 + LLM模型编排
- **v3.0** - React 前端重构 + 视觉AI流水线 + 法庭模拟 + 3D地图
- **v2.0** - 初始版本

## License
MIT
