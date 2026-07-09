# LvsheProject 3.2 - 法律 AI Agent 系统

> 红岩网校 Agent 方向考核项目 | 基于 FastAPI + React 18 的全栈法律 AI 智能体系统

## 系统架构

### 后端 (Python >=3.14, FastAPI)
- **LLM Gateway**: LiteLLM 统一接入智谱AI平台，6个模型协同
  - 文本模型：GLM-4.7-Flash / GLM-4.7-FlashX / GLM-4.6 / GLM-5.2
  - 视觉模型：GLM-OCR（文档/图片识别）
  - 图像生成模型：GLM-Image（批注图/摘要图生成）
- **RAG 引擎**: ChromaDB + HashEmbedding + Query Transform + HyDE + Hybrid Search
- **Graph RAG**: Neo4j 图谱检索（案件-法条关联）
- **Agent**: LangGraph 单智能体（plan→tool→final）
- **多智能体**: 法庭模拟（审判长+原告+被告+法官追问）
- **合同诊疗**: 视觉AI流水线（GLM-OCR→GLM文本→GLM-Image）
- **Memory**: 三级记忆系统（LocalMemoryStore + Mem0Adapter）

### 前端 (React 18 + TypeScript + Vite + Tailwind v4)
- Zustand 状态管理 + React Router 6
- SSE 流式响应 + Markdown 渲染
- 毛玻璃 UI 设计

## 功能模块

### 1. 智能咨询
- ChatGPT 风格 SSE 流式聊天，支持多轮对话
- 文件上传（txt/md/pdf/docx/png/jpg）
- 语言模型编排：自动调用视觉模型分析图片、调用图片生成模型生成图片
- AI 思考过程折叠展示（GLM-4.7-Flash reasoning_content）
- RAG 法律知识库增强

### 2. 合同诊疗
- 视觉AI流水线：上传文档→GLM-OCR识别→GLM文本诊断→GLM-Image生成摘要图
- 支持 Word/PDF 文档
- 风险点三色编码（高/中/低）
- 批注文档预览（新窗口）+ 下载
- 5阶段实时进度展示

### 3. 专家会诊（法庭模拟）
- 审判长开场→原告陈述→被告答辩→多轮辩论→法官追问→最终判决
- 法官自主选择追问时机（不和稀泥）
- 原告/被告必须回答法官追问
- 关键证据缺失时向用户弹出窗口询问补充信息
- AI 思考过程折叠展示

### 4. 地图浏览
三种地图模式自由切换：
- **高德快速模式**：高德地图 JS API 2.0 3D地图（国内快速）
- **平面模式**：OpenFreeMap positron（免费开源）
- **3D模式**：MapTiler + maplibre-gl terrain DEM（3D地形）
- 可迭代地点数据系统（律所/法院/警察局/劳务派遣管理局）
- 类别筛选 + 搜索 + 详情卡片

### 5. 放松模式
- 全屏背景图轮播 + 毛玻璃控制面板
- 背景音乐播放（开关控制+音量+上下曲+播放模式）
- 背景模糊开关

## 快速开始

### 环境要求
- Python >=3.14（推荐用 uv 管理）
- Node.js >=18
- Neo4j（可选，Graph RAG 用）

### 安装
```bash
# 后端
uv venv
uv pip install -r requirements.txt

# 前端
cd frontend-next
npm install

# 配置环境变量
cp .env.example .env
# 编辑 .env 填入 ZHIPU_API_KEY
```

### 启动
```powershell
# 方式1：一键启动（推荐）
.\start.ps1

# 方式2：手动启动
# 后端
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8001

# 前端（另一个终端）
cd frontend-next
npm run dev
```

访问 http://localhost:5173

### 资源放置
- 背景图：`frontend-next/public/relax/backgrounds/bg-1.jpg ~ bg-6.jpg`
- 背景音乐：`frontend-next/public/relax/music/track-1.mp3 ~ track-6.mp3`
- 编辑资源列表：`frontend-next/src/data/relax-assets.ts`
- 地图地点：编辑 `frontend-next/src/data/map-locations.ts`

## 技术栈

| 层 | 技术 |
|---|------|
| 后端 | FastAPI + LangGraph + LiteLLM + ChromaDB + Neo4j |
| 前端 | React 18 + TypeScript + Vite + Tailwind v4 + Zustand |
| 地图 | MapTiler + OpenFreeMap + 高德地图 JS API 2.0 + maplibre-gl |
| LLM | 智谱AI (GLM-4.7-Flash/FlashX/4.6/5.2/OCR/Image) |
| 流式 | SSE (Server-Sent Events) |

## 项目结构
```
LvsheProject/
├── backend/
│   ├── api/
│   │   ├── routes.py          # 主路由（chat/rag/agent/memory等）
│   │   ├── contract_routes.py # 合同诊疗子路由
│   │   ├── expert_routes.py   # 专家会诊子路由
│   │   └── schemas.py         # Pydantic 模型
│   ├── core/
│   │   ├── llm_gateway.py     # LLM 统一网关
│   │   ├── rag.py             # RAG 引擎
│   │   ├── agents.py          # LangGraph Agent
│   │   ├── multi_agents.py    # 法庭模拟器
│   │   ├── contract_pipeline.py # 合同诊疗流水线
│   │   ├── contract_annotator.py # 合同批注器
│   │   └── ...
│   ├── config.py              # 配置中心
│   └── main.py                # FastAPI 入口
├── frontend-next/
│   ├── src/
│   │   ├── pages/             # 6个页面
│   │   ├── components/        # 组件
│   │   ├── stores/            # Zustand 状态
│   │   ├── api/               # API 客户端
│   │   └── data/              # 数据文件
│   └── package.json
├── data/                      # 法律知识库 + 向量库
├── start.ps1                  # 一键启动脚本
└── .env                       # 环境变量（不提交）
```

## 版本历史
- **v3.2** - 思考过程显示优化 + 文件视觉兜底 + 专家会诊流程优化 + 地图180°旋转
  - chat：修复思考过程竖排异常，reasoning_content 改走 content 段落横向流式显示，编排步骤仍为离散列表
  - chat：PDF/Word 解析为空时自动调用 GLM-OCR 视觉模型兜底，统一文件识别逻辑
  - chat+专家：判决 reasoning 回退、speech 空文本兜底、thinking_note 事件分离编排提示与模型 reasoning
  - 专家：法官主动梳理所需证据清单→向用户针对性追问；修复 user_question 竞态导致多轮中断；超时保护；单轮异常容错；法官禁止端水
  - 地图：新增 180° 3D 视角旋转按钮（高德/MapTiler 模式），2D 模式不显示
- **v3.1** - 高德地图快速模式 + 法官追问重构 + LLM模型编排 + 思考过程折叠
- **v3.0** - React 前端重构 + 视觉AI流水线 + 法庭模拟 + 3D地图
- **v2.2** - Streamlit 前端 + 智谱AI 6模型统一接入
- **v2.0** - 初始版本

## License
MIT
