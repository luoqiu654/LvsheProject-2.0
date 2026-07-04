# ⚖️ 律社复刻 - 法律 AI Agent 系统

一个基于大语言模型的法律咨询 Agent 系统，集成 RAG 知识库、自主 Agent、多智能体辩论、技能系统等多种 AI 能力。

> 本项目为红岩网校工作站 AI 开发与应用部 Agent 方向学习项目，旨在系统性实践 Agent 开发的各项核心技术栈。

## ✨ 功能特性

### 💬 智能咨询
- 对话式法律咨询，支持多模型切换（千问、智谱等）
- RAG 知识库增强，基于法律条文给出精准解答
- 支持 5 种案情类型分类咨询
- 集成记忆系统，记住用户历史对话

### 📄 合同审查
- 上传合同文件或粘贴文本，AI 自动识别风险点
- 风险条款高亮标注
- 基于 Skill 技能系统的专业审查逻辑
- 支持 Word、PDF 等多种格式

### ⚖️ 专家会诊
- 多智能体三方辩论：原告 / 被告 / 法官
- 每个角色都是独立子 Agent，自主检索法律依据
- 针对性攻防辩论，每轮反驳对方漏洞
- 自动收敛检测，法官最终判决
- 支持自定义辩论轮数

### 🌿 放松模式
- 背景图片轮播（支持 1~9 张，可调节间隔）
- 背景虚化效果开关
- 背景音乐播放（支持 1~9 首 MP3）
- 音量调节、多种循环模式
- 视觉+听觉双重放松体验

## 🛠️ 技术栈

### 核心框架
- **LangGraph** - Agent 编排与状态管理
- **LiteLLM** - 多模型统一 API 网关
- **ChromaDB** - 向量数据库
- **FastAPI** - 后端服务框架
- **Streamlit** - 前端交互界面

### 进阶能力
- **进阶 RAG**：Query Transformation、HyDE、Context Enrichment、Hybrid Search、Graph RAG
- **Agent 系统**：任务规划、工具调用、文件操作、命令执行
- **Skill 系统**：可插拔技能包，支持热加载
- **记忆系统**：Mem0 三级记忆架构
- **GUI Agent**：Playwright 浏览器自动化
- **多智能体**：三方角色辩论、自主检索攻防

### 工程化
- **uv** - Python 依赖管理
- **pydantic-settings** - 配置管理
- **pytest** - 单元测试
- **Docker** - 容器化支持（准备中）

## 🚀 快速开始

### 环境要求
- Python 3.11+
- uv（Python 包管理器）
- Git

### 1. 克隆项目
```bash
git clone https://github.com/luoqiu654/LvsheProject-2.0.git
cd LvsheProject-2.0
```

### 2. 安装依赖
```bash
uv sync
```

### 3. 配置环境变量
复制 `.env.example` 为 `.env`，填入你的 API 密钥：
```bash
cp .env.example .env
```

编辑 `.env` 文件：
```env
# 大模型配置（至少配置一个）
QWEN_API_KEY=your_qwen_api_key
ZHIPU_API_KEY=your_zhipu_api_key

# 默认模型
DEFAULT_MODEL=qwen-plus

# 向量数据库路径
CHROMA_PATH=./data/vector_store
```

### 4. 启动后端
```bash
uv run uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
```

### 5. 启动前端
```bash
uv run streamlit run frontend/Home.py
```

### 6. 初始化知识库
首次运行请在首页点击「索引全部法律文档」，将法律知识库写入向量数据库。

## 📁 项目结构

```
LvsheProject/
├── backend/                 # 后端服务
│   ├── api/                 # API 路由
│   │   ├── routes.py        # 所有接口定义
│   │   └── schemas.py       # 请求响应模型
│   ├── core/                # 核心业务逻辑
│   │   ├── agents.py        # 自主 Agent
│   │   ├── multi_agents.py  # 多智能体辩论系统
│   │   ├── llm_gateway.py   # LLM API 网关
│   │   ├── rag.py           # 文本 RAG 引擎
│   │   ├── graph_rag.py     # 图 RAG（Neo4j）
│   │   ├── image_rag.py     # 图像 RAG
│   │   ├── memory.py        # 记忆系统
│   │   ├── skills.py        # Skill 技能系统
│   │   ├── gui_agent.py     # GUI Agent
│   │   └── safe_commands.py # 安全命令执行
│   ├── utils/               # 工具函数
│   ├── config.py            # 配置中心
│   └── main.py              # 入口文件
├── frontend/                # 前端（Streamlit）
│   ├── Home.py              # 首页
│   ├── api_client.py        # API 客户端
│   ├── assets/              # 静态资源
│   │   ├── backgrounds/     # 背景图片
│   │   └── music/           # 背景音乐
│   └── pages/               # 子页面
│       ├── 1_智能咨询.py
│       ├── 2_合同审查.py
│       ├── 3_专家会诊.py
│       └── 4_放松模式.py
├── skills/                  # Skill 技能包
│   ├── contract-risk-review/
│   ├── law-search/
│   └── legal-consultation/
├── data/                    # 数据目录
│   ├── raw/                 # 原始法律文档
│   │   ├── civil_code.md    # 民法典
│   │   ├── criminal_law.md  # 刑法
│   │   ├── administrative_law.md
│   │   ├── constitution.md  # 宪法
│   │   ├── economic_law.md  # 经济法
│   │   ├── environmental_law.md
│   │   ├── social_law.md    # 社会法
│   │   └── commercial_law.md # 商法
│   ├── vector_store/        # ChromaDB 持久化
│   ├── memory/              # 记忆存储
│   └── uploads/             # 用户上传
├── tests/                   # 测试用例
├── .env.example             # 环境变量模板
├── .gitignore
├── pyproject.toml           # 项目配置
├── uv.lock                  # 依赖锁定
└── README.md                # 项目说明
```

## 📖 使用指南

### 智能咨询
1. 在首页选择案情类型（可选）
2. 点击「立即开始智能咨询」
3. 在对话框输入你的法律问题
4. AI 会结合知识库给出专业解答

### 合同审查
1. 进入「合同审查」页面
2. 上传合同文件或直接粘贴文本
3. 点击「开始审查」
4. 查看风险点标注和修改建议

### 专家会诊
1. 进入「专家会诊」页面
2. 输入案件描述
3. 设置辩论轮数（默认 5 轮）
4. 点击「开始会诊」
5. 观看原告被告多轮辩论，最后看法官判决

### 放松模式
1. 将背景图片放入 `frontend/assets/backgrounds/`
2. 将音乐文件放入 `frontend/assets/music/`
3. 进入「放松模式」
4. 开启背景和音乐，调节到舒适状态

## 🔧 开发指南

### 添加新的法律类别
1. 在 `data/raw/` 下创建新的 `.md` 文件
2. 在 `backend/core/rag.py` 的 `LAW_CATEGORY_KEYWORDS` 中添加关键词
3. 重新索引知识库

### 开发新 Skill
1. 在 `skills/` 下创建新目录
2. 编写 `skill.yaml` 配置文件
3. 实现技能逻辑
4. 在 `skills.py` 中注册

### 切换大模型
修改 `.env` 中的 `DEFAULT_MODEL`，支持：
- `qwen-plus` - 阿里千问
- `glm-4` - 智谱清言
- 其他 LiteLLM 支持的模型

## 📚 法律知识库

目前内置 8 大法律分类框架：
- 民法典（已有内容）
- 刑法
- 行政法
- 宪法
- 经济法
- 环境法
- 社会法
- 商法

> 各法律文件已建好目录框架，可按需填充具体条文内容。

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

## 📄 License

MIT License
