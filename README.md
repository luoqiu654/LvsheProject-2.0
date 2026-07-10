# LvsheProject 3.4 - 法律 AI Agent 系统

> 红岩网校 Agent 方向考核项目 | 基于 FastAPI + React 18 的全栈法律 AI 智能体系统

## 项目亮点

- **四大考核功能全面集成**：Agent Skills / Agent Memory / GUI Agent / Autonomous Agent 四个考核核心功能深度融入现有页面，不新增独立页面
- **自主多智能体架构**：参考 Agno / CAMEL / CrewAI / elizaOS 等主流多智能体框架理念，以 LangGraph 编排「1 主 agent + 3 子 agent」真实法庭全流程（开庭→证据梳理→用户追问→多轮辩论→判决→打回检查），子 agent 自主调用 law_search 工具检索法律条文
- **真实法庭模拟**：法官主动梳理关键证据清单 → 向用户针对性追问（证据是否真实存在、时间线是否清晰）→ 多轮辩论 → 端水/无理由判决自动打回重判，拒绝和稀泥
- **Agent Memory 记忆系统**：智能咨询对话前后自动检索和提取用户记忆，侧边栏"我的记忆"面板展示历史记忆条目，支持删除
- **Agent Skills 技能系统**：智能咨询自动匹配并注入技能（合同风险审查/法律检索/法律咨询），侧边栏"技能市场"面板展示所有可用技能
- **GUI Agent 浏览器自动化**：用户消息含 URL 时自动浏览网页，提取内容并智能总结注入对话，浏览结果以卡片展示
- **RAG 法律依据检索**：每个子 agent 均集成 RAG 检索，从项目蒸馏的法律文件中查找判决依据，让 AI 判决"言之有据"
- **三模地图 + 360° 旋转 + 俯视调节**：高德 / OpenFreeMap / MapTiler 三引擎自由切换，圆形拨盘控件支持 0-360° 任意角度拖动旋转 + 0-60° 俯视角度(pitch)垂直滑块调节
- **视觉 AI 流水线**：GLM-OCR → GLM 文本 → GLM-Image 端到端合同诊疗，PNG 图片视觉分析修复（字节头 MIME 检测 + 重试机制）
- **Framer Motion + tsparticles 首页动效**：70 个粒子 + 连线效果背景，功能卡片 3D 悬停效果，首次进入全屏开场动画

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
- **Agent Memory 集成**：对话前后自动检索和提取用户记忆，侧边栏"我的记忆"面板展示记忆条目，支持删除
- **Agent Skills 集成**：自动匹配并注入技能（合同风险审查/法律检索/法律咨询），侧边栏"技能市场"面板展示所有可用技能
- **GUI Agent 集成**：用户消息含 URL 时自动浏览网页，提取内容并智能总结注入对话，浏览结果以卡片展示

### 2. 合同诊疗
- 视觉AI流水线：上传文档→GLM-OCR识别→GLM文本诊断→GLM-Image生成摘要图
- 支持 Word/PDF 文档
- 风险点三色编码（高/中/低）
- 批注文档预览（新窗口）+ 下载
- 5阶段实时进度展示

### 3. 专家会诊（法庭模拟）
- 审判长开场→原告陈述→被告答辩→多轮辩论→法官追问→最终判决
- 法官自主选择追问时机（不和稀泥），原被告回答"不清楚"时必须向用户追问
- 原告/被告必须回答法官追问
- 关键证据缺失时向用户弹出窗口询问补充信息
- 判决打回时向用户追问关键证据（端水/无理由判决自动打回重判）
- **Autonomous Agent 集成**：子 agent 自主调用 law_search 工具检索法律条文（plan→tool→final 模式），前端展示 Agent 工具调用折叠面板
- AI 思考过程折叠展示（智能合并短碎片为横向段落）

### 4. 地图浏览
三种地图模式自由切换：
- **高德快速模式**：高德地图 JS API 2.0 3D地图（国内快速）
- **平面模式**：OpenFreeMap positron（免费开源）
- **3D模式**：MapTiler + maplibre-gl terrain DEM（3D地形）
- 可迭代地点数据系统（律所/法院/警察局/劳务派遣管理局）
- 类别筛选 + 搜索 + 详情卡片
- 360° 旋转拨盘 + 0-60° 俯视角度(pitch)垂直滑块（高德/3D 模式）
- 模式切换时保持中心坐标和缩放级别

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
| 前端 | React 18 + TypeScript + Vite + Tailwind v4 + Zustand + Framer Motion + tsparticles |
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
│   │   ├── multi_agents.py    # 法庭模拟器（旧）
│   │   ├── court_agents.py    # 法庭子 agent（法官/原告/被告 + RAG）
│   │   ├── court_orchestrator.py # 法庭主编排器（LangGraph 全流程）
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
- **v3.3** - 专家会诊多 agent 重构 + 地图 360° 旋转 + 首页动效 + chat 加固
  - 专家会诊大重构：1 主 agent + 3 子 agent（法官 / 原告 / 被告）架构
    - 新建 `court_agents.py`：CourtSubAgent 基类 + PlaintiffAgent / DefendantAgent / JudgeAgent，集成 RAG 检索（从项目蒸馏的法律文件找依据）+ skill 调用
    - 新建 `court_orchestrator.py`：CourtOrchestrator LangGraph 主编排器，真实法庭全流程（开庭→证据梳理→用户追问→多轮辩论→判决→打回检查）
    - 法官主动梳理关键证据清单 → 向用户针对性追问（证据是否真实存在、时间线是否清晰）→ 用户回答"不知道"才能以案件不详无法判决
    - 修复"LLM 服务不可用"误导文案：区分 LLM 真正失败 vs JSON 解析失败，后者从自由文本提取判决
    - 法官判决打回机制：端水 / 无理由无法判断时主 agent 打回重判（retry<2）
    - 修复 `user_question` 竞态：状态前置 + 5s 容错 + 300s 超时
    - 单轮异常容错不中断整体流程
    - 参考 Agno / CAMEL / CrewAI / elizaOS 多智能体框架理念
  - chat：思考过程竖排修复，`reasoning_content` 防御性加固（String 转换、Array.isArray 校验、数组自动 join）
  - 地图：新增 360° 可拖动旋转拨盘控件（MapRotationDial），pointer 事件拖动 0-360° 任意角度，实时同步 maplibre setBearing / 高德 setRotation，触屏兼容，rAF 节流
  - 首页：浮动粒子 + 渐变流光 + 卡片入场（IntersectionObserver）+ 数字滚动（requestAnimationFrame）+ hover 3D 倾斜 + 按钮流光扫过，纯 CSS 无新依赖，支持 prefers-reduced-motion
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
