# LvsheProject 2.0 - 法律AI Agent平台

> 红岩网校工作站 AI开发与应用部 Agent 方向考核项目
>
> 基于多智能体系统的法律咨询与合同审查平台

## 项目概述

LvsheProject 是一个面向法律领域的 AI Agent 平台，深度整合了红岩网校 Agent 方向考核任务 2-8 的全部核心技术栈。项目以 LangGraph 为编排核心，构建了包含自主 Agent、技能系统、记忆模块、GUI 代理、多智能体辩论、Graph RAG、图像 RAG 等在内的完整法律 AI 能力矩阵。

## 技术架构总览

```
┌─────────────────────────────────────────────────────────────┐
│                        Frontend (Streamlit)                  │
├─────────────────────────────────────────────────────────────┤
│                    FastAPI Backend Layer                     │
├─────────────┬──────────┬──────────┬──────────┬──────────────┤
│  LLM Gateway │  RAG 层  │  Agent   │  Skills  │  Memory 层   │
│  (LiteLLM)   │(ChromaDB)│(LangGraph│  系统    │  (mem0)      │
│             │ + Neo4j  │  + 工具)  │          │              │
├─────────────┴──────────┴──────────┴──────────┴──────────────┤
│                    文档解析 (Unstructured.io)                │
└─────────────────────────────────────────────────────────────┘
```

## 红岩考核任务覆盖情况

### 任务 2：Master Stacks（技术栈掌握）

#### ✅ Agent 编排框架：LangGraph
- **位置**：`backend/core/agents.py`, `backend/core/multi_agents.py`
- **实现要点**：
  - 使用 `StateGraph` 构建状态驱动的 Agent 工作流
  - 单 Agent 模式：Researcher → Planner → Executor 链式执行
  - 多 Agent 模式：原告 → 被告 → 法官 循环辩论
  - 条件边（Conditional Edges）实现动态流程控制
  - 状态持久化与增量更新机制

#### ✅ LLM API 网关：LiteLLM
- **位置**：`backend/core/llm_gateway.py`
- **实现要点**：
  - 统一封装多家 LLM 提供商（通义千问、智谱 GLM、硅基流动、豆包）
  - OpenAI 兼容接口标准化调用
  - 流式响应支持（SSE）
  - 统一异常处理与错误降级
  - 可配置默认模型与动态切换

#### ✅ 向量数据库：ChromaDB
- **位置**：`backend/core/rag.py`, `backend/core/image_rag.py`
- **实现要点**：
  - 文本向量库：法律文档语义检索
  - 图像向量库：合同图像视觉检索（基于 OpenCLIP）
  - 持久化存储与增量索引
  - 混合检索：向量相似度 + 关键词评分重排

#### ✅ 图数据库：Neo4j（选做完成）
- **位置**：`backend/core/graph_rag.py`
- **实现要点**：
  - 法律知识图谱构建：法律条款、案例、当事人、概念等实体
  - 实体与关系自动提取（规则 + LLM 辅助）
  - 图遍历检索与相似度匹配
  - 连接状态检测与内存降级方案
  - 与文本 RAG 协同实现混合检索增强

#### ✅ 文档解析器：Unstructured.io（选做完成）
- **位置**：`backend/utils/document_parser.py`
- **实现要点**：
  - 多格式支持：Word(.docx)、PDF、纯文本、图片
  - 智能路由：根据文件类型自动选择最佳解析器
  - 表格提取、页眉页脚识别
  - 本地解析 + Unstructured API 双模式降级
  - 解析结果结构化输出

---

### 任务 3：Further RAG（高级检索增强）

#### ✅ 进阶 RAG 技术实现（≥3 种）

**1. Query Transformation（查询转换）**
- LLM 将用户问题重写为多个子查询
- 并行检索后汇总结果，提升召回率
- 位置：`backend/core/rag.py` 中 `use_llm_query_transform` 参数

**2. HyDE（假设性文档嵌入）**
- 先生成假设性回答，再用假设回答向量检索
- 弥合查询与文档块之间的语义鸿沟
- 位置：`backend/core/rag.py` 中 `use_llm_hyde` 参数

**3. Hybrid Search（融合检索）**
- 向量相似度检索 + 关键词匹配评分
- 加权融合重排，兼顾语义与精确匹配
- 位置：`backend/core/rag.py` 中 `final_score` 计算

**4. Context Enrichment（上下文增强）**
- 检索小块保证精度，生成时扩展上下文窗口
- 位置：`backend/core/rag.py` 中 `enriched_text` 字段

**5. Graph RAG（基于图的 RAG）**
- 知识图谱实体关系遍历检索
- 适合涉及多实体、关系推理的法律问题
- 位置：`backend/core/graph_rag.py`

#### ✅ Agentic RAG（智能体驱动的 RAG）
- Agent 自主判断是否需要检索、检索什么
- 多轮对话中动态调用 RAG 工具
- 位置：`backend/core/agents.py` 中的 RAG Tool 集成

---

### 任务 4：Autonomous Agents（自主智能体）

#### ✅ 任务规划能力
- **位置**：`backend/core/agents.py`
- **实现要点**：
  - Planner 节点：将复杂任务拆解为可执行步骤
  - 迭代式规划：执行后根据结果调整后续计划
  - 法律领域专用规划提示词

#### ✅ 文件读取/编辑能力
- 安全沙箱内的文件读写操作
- 路径白名单限制，防止越权访问
- 位置：`backend/core/safe_commands.py`

#### ✅ 命令执行能力
- 受控的命令执行框架
- 支持的命令类型：文件清理、数据导出等
- 位置：`backend/core/safe_commands.py`

#### ✅ 安全机制
1. **目录范围限制**：所有操作限制在授权目录内
2. **手动/自动审批**：高危命令需用户确认后执行
3. **命令类型枚举**：白名单机制，仅允许预定义的安全操作
4. **审计追踪**：所有操作记录日志

---

### 任务 5：Agent Skills（智能体技能）

#### ✅ Skill 系统实现
- **位置**：`backend/core/skills.py`, `skills/`
- **架构设计**：
  - 基于 YAML 的 Skill 定义格式
  - 统一的 Skill 执行器与生命周期管理
  - 自动匹配：根据输入文本智能选择最合适的 Skill
  - 资源引用：Skill 可附带参考文档、检查清单等

#### ✅ 已实现的 Skill

**1. 合同风险审查（contract-risk-review）**
- 位置：`skills/contract-risk-review/`
- 功能：自动识别合同中的高/中/低风险点
- 附带：风险审查检查清单参考文档
- 输出：结构化风险点 + 修改建议

**2. 法律检索（law-search）**
- 位置：`skills/law-search/`
- 功能：专业法律文献与案例检索

**3. 法律咨询（legal-consultation）**
- 位置：`skills/legal-consultation/`
- 功能：标准化法律咨询应答流程

#### Skill 打包文件
项目根目录下 `contract-risk-review-skill.zip` 为完整的 Skill 压缩包，可直接导入支持 Skill 标准的平台。

---

### 任务 6：Agent Memory（智能体记忆）

#### ✅ mem0 集成
- **位置**：`backend/core/memory.py`
- **实现要点**：
  - 本地文件模式存储记忆，无需额外服务
  - 用户级记忆隔离
  - 自动记忆提取：对话中自动检索相关历史记忆
  - 自动记忆保存：重要信息自动存入记忆库
  - 记忆上下文注入：将相关历史记忆注入 LLM 提示词

#### 记忆类型
- **短期记忆**：当前会话上下文（LangGraph state）
- **长期记忆**：跨会话的用户偏好、历史咨询记录（mem0）
- **工作记忆**：短期记忆中的关键论点提取（多轮辩论模块）

---

### 任务 7：GUI Agents（图形界面智能体）

#### ✅ Web 浏览器 Agent：Playwright
- **位置**：`backend/core/gui_agent.py`
- **实现要点**：
  - 网页浏览与内容提取
  - 无头模式 / 有头模式可配置
  - 页面标题、URL、文本预览、链接提取
  - 截图功能支持
  - LLM 摘要：浏览后自动总结页面内容

#### 技术特点
- 基于 Playwright 的现代浏览器自动化
- 支持动态页面渲染（JavaScript 执行）
- 可配置 headless 模式适配不同环境

---

### 任务 8：Multi-Agent System（多智能体系统）

#### ✅ 专家会诊系统（多智能体辩论）
- **位置**：`backend/core/multi_agents.py`
- **架构**：基于 LangGraph 的三方辩论模型

**角色设计：**
1. **Researcher（检索员）**：法律资料检索与案情摘要
2. **Plaintiff Advocate（原告代理）**：从原告立场陈述主张、举证
3. **Defendant Advocate（被告代理）**：从被告立场进行抗辩、质证
4. **Judge（法官）**：中立评估、收敛度判断、最终判决

**核心机制：**
- **多轮迭代辩论**：可配置最大轮数，支持提前收敛终止
- **收敛度检测**：基于关键词相似度计算双方观点收敛程度
- **短期记忆**：每轮关键论点存入记忆，供下一轮参考
- **条件终止**：达到最大轮数 / 收敛阈值 / 法官判定 任一满足即结束
- **明确判决输出**：胜诉方、胜率、关键胜负点、行动建议

**技术亮点：**
- LangGraph 状态图编排，天然支持循环与条件分支
- 每轮独立状态更新，可追溯完整辩论过程
- 支持 LLM 模式与规则模式双轨运行

---

## 合同审查模块

### 功能特性
1. **风险点识别**：自动识别合同中的高/中/低风险
2. **标注合同生成**：生成带高亮标注的 Word 文档
3. **文件管理**：用户级文件存储与下载
4. **批量解析**：支持多文档批量上传解析

### 技术依赖
- **文档解析**：Unstructured.io + pdfplumber + python-docx
- **知识图谱**：Neo4j（Graph RAG 增强审查）
- **标注输出**：python-docx 颜色高亮 + 批注

## 项目结构

```
LvsheProject/
├── backend/
│   ├── api/                 # API 层（路由、请求响应模型）
│   │   ├── routes.py        # 所有 API 端点
│   │   └── schemas.py       # Pydantic 数据模型
│   ├── core/                # 核心业务逻辑
│   │   ├── agents.py        # 自主 Agent（任务4）
│   │   ├── multi_agents.py  # 多智能体辩论（任务8）
│   │   ├── llm_gateway.py   # LLM 网关（任务2）
│   │   ├── rag.py           # 文本 RAG（任务3）
│   │   ├── graph_rag.py     # 图 RAG（任务2+3）
│   │   ├── image_rag.py     # 图像 RAG
│   │   ├── memory.py        # 记忆系统（任务6）
│   │   ├── skills.py        # Skill 系统（任务5）
│   │   ├── gui_agent.py     # GUI Agent（任务7）
│   │   ├── contract_annotator.py  # 合同标注
│   │   └── safe_commands.py # 安全命令执行（任务4）
│   ├── utils/
│   │   └── document_parser.py     # 文档解析（任务2）
│   ├── config.py            # 配置管理
│   └── main.py              # 应用入口
├── frontend/                # Streamlit 前端
├── skills/                  # Agent Skills（任务5）
│   ├── contract-risk-review/
│   ├── law-search/
│   └── legal-consultation/
├── data/                    # 数据目录
│   ├── vector_store/        # ChromaDB 持久化
│   ├── memory/              # mem0 记忆存储
│   └── uploads/             # 用户上传文件
├── output/                  # 输出目录
│   └── contract_review/     # 合同审查输出
├── tests/                   # 测试用例
├── .env.example             # 环境变量模板
├── pyproject.toml           # 项目依赖
└── README.md                # 本文件
```

## 快速开始

### 环境要求
- Python ≥ 3.14（使用 uv 管理）
- 可选：Neo4j（Graph RAG 功能）
- 可选：Docker（Unstructured.io 本地部署）

### 安装步骤

```bash
# 1. 克隆仓库
git clone git@github.com:luoqiu654/LvsheProject-2.0.git
cd LvsheProject-2.0

# 2. 使用 uv 创建虚拟环境并安装依赖
uv venv
uv sync

# 3. 配置环境变量
cp .env.example .env
# 编辑 .env，填入 API Key 等配置

# 4. 启动后端
uv run uvicorn backend.main:app --reload
```

### 环境变量说明

详见 `.env.example`，主要配置项：
- LLM 提供商 API Key（通义千问、智谱等）
- ChromaDB 存储路径
- Neo4j 连接配置（可选）
- Unstructured.io API 配置（可选）
- MinIO 对象存储（可选，默认关闭）

## API 接口概览

| 模块 | 端点 | 说明 |
|------|------|------|
| 聊天 | `POST /api/chat` | 基础 LLM 对话 |
| RAG | `POST /api/rag/ask` | 检索增强问答 |
| Agent | `POST /api/agent/run` | 自主 Agent 执行 |
| 多智能体 | `POST /api/multi-agents/debate` | 专家会诊辩论 |
| Skill | `POST /api/skills/run` | 执行 Agent Skill |
| 记忆 | `POST /api/memory/chat` | 带记忆的对话 |
| GUI | `POST /api/gui/browse` | 网页浏览 Agent |
| 合同审查 | `POST /api/contract/review` | 合同风险审查 |
| Graph RAG | `POST /api/graph-rag/ask` | 知识图谱问答 |
| 文档解析 | `POST /api/document/parse` | 文档内容提取 |

## 开发记录

### v2.0 版本更新
- ✅ 新增 Graph RAG 模块（Neo4j 知识图谱）
- ✅ 新增图像 RAG 模块（OpenCLIP 图像检索）
- ✅ 文档解析升级（Unstructured.io 集成）
- ✅ 多智能体辩论增强（多轮迭代 + 收敛检测）
- ✅ 合同审查完整流程（风险识别 + 标注输出）
- ✅ 统一配置中心（pydantic-settings）
- ✅ MinIO 对象存储支持（可选，默认关闭）

### Bug 修复
- 修复专家会诊模块辩论轮数设置不生效的问题（硬编码 2 轮 → 尊重 max_rounds 参数）
- 完善 LangGraph 状态中 debate_round 字段的持久化

## 技术栈总结

| 考核任务 | 对应技术 | 完成状态 |
|---------|---------|---------|
| 任务2 - Agent 框架 | LangGraph | ✅ 完成 |
| 任务2 - LLM 网关 | LiteLLM | ✅ 完成 |
| 任务2 - 向量数据库 | ChromaDB | ✅ 完成 |
| 任务2 - 图数据库（选做） | Neo4j | ✅ 完成 |
| 任务2 - 文档解析（选做） | Unstructured.io | ✅ 完成 |
| 任务3 - 高级 RAG | HyDE / Query Transform / Hybrid / Graph / Context Enrichment | ✅ 5种 |
| 任务4 - 自主 Agent | 任务规划 + 文件操作 + 命令执行 + 安全机制 | ✅ 完成 |
| 任务5 - Agent Skills | Skill 系统 + 3个领域 Skill + 打包 | ✅ 完成 |
| 任务6 - Agent Memory | mem0 本地模式 + 自动读写 | ✅ 完成 |
| 任务7 - GUI Agent | Playwright 浏览器 Agent | ✅ 完成 |
| 任务8 - 多智能体系统 | 三方辩论模型 + LangGraph 编排 | ✅ 完成 |

## 许可证

本项目为红岩网校考核项目，仅供学习交流使用。

---

**项目作者**：luoqiu654
**GitHub**：https://github.com/luoqiu654/LvsheProject-2.0
