from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from frontend.api_client import APIClientError, LvsheAPIClient


st.set_page_config(
    page_title="律社复刻 - 法律 AI Agent",
    page_icon="⚖️",
    layout="wide",
)

# ========== 侧边栏设置 ==========
with st.sidebar:
    st.header("⚙️ 后端设置")
    api_base_url = st.text_input(
        "FastAPI 地址",
        value="http://127.0.0.1:8000",
    )
    st.info("请先启动后端：`uv run uvicorn backend.main:app --reload`")

    st.divider()
    st.subheader("🧭 快速导航")
    st.page_link("pages/1_智能咨询.py", label="💬 智能咨询", use_container_width=True)
    st.page_link("pages/2_合同审查.py", label="📄 合同审查", use_container_width=True)
    st.page_link("pages/3_专家会诊.py", label="⚖️ 专家会诊", use_container_width=True)
    st.page_link("pages/4_放松模式.py", label="🌿 放松模式", use_container_width=True)

client = LvsheAPIClient(base_url=api_base_url)

# ========== 页面标题 ==========
st.title("⚖️ 律社复刻：法律 AI Agent 系统")
st.caption("FastAPI + Streamlit + LiteLLM + LangGraph + ChromaDB + Agent Skills + Memory + Playwright + Multi-Agent")

# ========== 四大功能入口 ==========
st.divider()
st.subheader("🚀 功能模块")

col1, col2, col3, col4 = st.columns(4)

with col1:
    st.markdown(
        """
        <div style="padding: 20px; border-radius: 12px; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; text-align: center; min-height: 180px;">
            <div style="font-size: 40px; margin-bottom: 10px;">💬</div>
            <div style="font-weight: bold; font-size: 18px; margin-bottom: 8px;">智能咨询</div>
            <div style="font-size: 13px; opacity: 0.9; line-height: 1.4;">对话式法律咨询<br/>多模型自由切换<br/>RAG 知识库增强</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if st.button("进入咨询", type="primary", use_container_width=True, key="go_consult"):
        st.switch_page("pages/1_智能咨询.py")

with col2:
    st.markdown(
        """
        <div style="padding: 20px; border-radius: 12px; background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%); color: white; text-align: center; min-height: 180px;">
            <div style="font-size: 40px; margin-bottom: 10px;">📄</div>
            <div style="font-weight: bold; font-size: 18px; margin-bottom: 8px;">合同审查</div>
            <div style="font-size: 13px; opacity: 0.9; line-height: 1.4;">AI 自动风险识别<br/>条款标注与建议<br/>Skill 技能驱动</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if st.button("开始审查", type="primary", use_container_width=True, key="go_contract"):
        st.switch_page("pages/2_合同审查.py")

with col3:
    st.markdown(
        """
        <div style="padding: 20px; border-radius: 12px; background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%); color: white; text-align: center; min-height: 180px;">
            <div style="font-size: 40px; margin-bottom: 10px;">⚖️</div>
            <div style="font-weight: bold; font-size: 18px; margin-bottom: 8px;">专家会诊</div>
            <div style="font-size: 13px; opacity: 0.9; line-height: 1.4;">多智能体三方辩论<br/>原告被告法官角色<br/>自主检索法律依据</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if st.button("开始会诊", type="primary", use_container_width=True, key="go_debate"):
        st.switch_page("pages/3_专家会诊.py")

with col4:
    st.markdown(
        """
        <div style="padding: 20px; border-radius: 12px; background: linear-gradient(135deg, #43e97b 0%, #38f9d7 100%); color: white; text-align: center; min-height: 180px;">
            <div style="font-size: 40px; margin-bottom: 10px;">🌿</div>
            <div style="font-weight: bold; font-size: 18px; margin-bottom: 8px;">放松模式</div>
            <div style="font-size: 13px; opacity: 0.9; line-height: 1.4;">背景图片轮播<br/>背景音乐播放<br/>音量循环可调</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if st.button("进入放松", type="primary", use_container_width=True, key="go_relax"):
        st.switch_page("pages/4_放松模式.py")

# ========== 案情类型选择区 ==========
st.divider()
st.subheader("⚖️ 选择案情类型，开始智能咨询")
st.caption("选择你的案件类型，AI 将针对该领域法律规定为你提供更精准的解答")

case_types = [
    {"key": "civil", "name": "民事案件", "icon": "🏠", "desc": "合同纠纷、侵权责任、婚姻家庭、继承、物权等", "color": "blue"},
    {"key": "administrative", "name": "行政案件", "icon": "🏛️", "desc": "行政处罚、行政许可、行政复议、行政诉讼等", "color": "orange"},
    {"key": "criminal", "name": "刑事案件", "icon": "⚔️", "desc": "刑事犯罪、量刑标准、刑事辩护、取保候审等", "color": "red"},
    {"key": "execution", "name": "执行案件", "icon": "📋", "desc": "强制执行、执行异议、财产查封、失信被执行人等", "color": "green"},
    {"key": "state_compensation", "name": "国家赔偿", "icon": "💰", "desc": "行政赔偿、刑事赔偿、国家赔偿程序与标准等", "color": "purple"},
]

cols = st.columns(5)
selected_case_type = st.session_state.get("selected_case_type", None)

for idx, case in enumerate(case_types):
    with cols[idx]:
        is_selected = selected_case_type == case["key"]
        card_style = "border: 2px solid #1f77b4; background-color: #e8f4fd;" if is_selected else "border: 1px solid #ddd; background-color: #fafafa;"

        st.markdown(
            f"""
            <div style="
                padding: 20px;
                border-radius: 10px;
                text-align: center;
                {card_style}
                cursor: pointer;
                min-height: 160px;
            ">
                <div style="font-size: 36px; margin-bottom: 10px;">{case['icon']}</div>
                <div style="font-weight: bold; font-size: 16px; margin-bottom: 8px;">{case['name']}</div>
                <div style="font-size: 12px; color: #666; line-height: 1.4;">{case['desc']}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        if st.button(f"选择{case['name']}", key=f"btn_{case['key']}", type="primary" if is_selected else "secondary", use_container_width=True):
            st.session_state.selected_case_type = case["key"]
            st.session_state.selected_case_name = case["name"]
            st.rerun()

# 不指定类型选项
st.markdown("<br>", unsafe_allow_html=True)
col1, col2, col3 = st.columns([1, 2, 1])
with col2:
    no_type = selected_case_type is None
    if st.button(
        "🎯 不指定类型，让 AI 自动分析",
        type="primary" if no_type else "secondary",
        use_container_width=True,
    ):
        st.session_state.selected_case_type = None
        st.session_state.selected_case_name = None
        st.rerun()

# 显示当前选择
if selected_case_type:
    case_name = st.session_state.get("selected_case_name", "未知类型")
    st.success(f"✅ 已选择：{case_name}")
else:
    st.info("💡 未指定类型，AI 将根据你的问题自动分析案情类型")

# ========== 系统能力介绍 ==========
st.divider()
st.subheader("🧠 系统能力")

col1, col2, col3 = st.columns(3)

with col1:
    st.subheader("🧠 AI 底座")
    st.markdown(
        """
        - **LiteLLM 多模型网关**
          - 千问 Qwen / 智谱 GLM 自由切换
        - **ChromaDB 法律知识库**
          - Query Transformation 查询改写
          - HyDE 假设性文档嵌入
          - Context Enrichment 上下文增强
          - Hybrid Search 融合检索
          - Category-aware 分类检索
        """
    )

with col2:
    st.subheader("🤖 Agent 能力")
    st.markdown(
        """
        - **LangGraph 单智能体**
          - 任务规划 + 工具调用
          - 法律检索 / 合同审查 / 计算器
        - **Agent Skills 技能系统**
          - 合同风险审查 Skill
          - 法律检索 Skill
        - **Mem0 长期记忆**
          - 用户历史记忆
        - **Playwright GUI Agent**
          - 网页浏览与信息提取
        - **多智能体法律会诊**
          - 原告 / 被告 / 法官 三方辩论
          - 子 Agent 自主检索攻防
        """
    )

with col3:
    st.subheader("🧪 工程化")
    st.markdown(
        """
        - **FastAPI 后端接口**
          - RESTful API 设计
          - SSE 流式响应
        - **Streamlit 多页面前端**
          - Chat 对话式交互
          - 多文件批量上传
          - 放松模式（背景+音乐）
        - **Pytest 单元测试**
        - **Docker 容器化准备**
        - **uv 依赖管理**
        - **8大法律分类知识库**
        """
    )

# ========== 后端状态检查 ==========
st.divider()
st.subheader("🔌 后端连接状态")

if st.button("检查后端状态", type="primary"):
    try:
        health = client.health()
        status = client.status()

        st.success("✅ 后端连接成功")

        left, right = st.columns(2)
        with left:
            st.markdown("**健康检查**")
            st.json(health)
        with right:
            st.markdown("**系统状态**")
            st.json(status)

    except APIClientError as exc:
        st.error(str(exc))
        st.warning("请确认 FastAPI 后端已经启动，并且端口是 8000。")

# ========== 初始化知识库 ==========
st.divider()
st.subheader("📚 初始化法律知识库")

st.write("第一次运行请点击下方按钮，将 `data/raw/` 目录下的法律文档索引到 ChromaDB。")

if st.button("索引全部法律文档"):
    try:
        result = client.index_sample()
        st.success("✅ 索引完成")
        st.json(result)
    except APIClientError as exc:
        st.error(str(exc))

# ========== 使用指引 ==========
st.divider()
st.subheader("🚀 快速开始")

st.markdown(
    """
    ### 1. 💬 智能咨询
    打开左侧 `智能咨询`，选择案情类型和模型，开始对话式法律咨询。

    ### 2. 📄 合同审查
    打开 `合同审查`，上传合同文件或粘贴合同文本，AI 自动识别风险点。

    ### 3. ⚖️ 专家会诊
    打开 `专家会诊`，输入案件描述，体验多智能体三方辩论。

    ### 4. 🌿 放松模式
    打开 `放松模式`，搭配背景图片和轻音乐，享受沉浸式法律咨询体验。

    ### 5. 功能组合
    可在侧边栏自由组合 RAG / Agent / Memory 等功能，体验不同效果。
    """
)
