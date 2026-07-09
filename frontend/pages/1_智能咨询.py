from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from frontend.api_client import APIClientError, LvsheAPIClient, stream_text_generator


st.set_page_config(
    page_title="智能咨询",
    page_icon="💬",
    layout="wide",
)

st.title("💬 智能法律咨询")
st.caption("支持 RAG 知识库检索、Agent 工具调用、长期记忆、多模型切换的对话式法律咨询。")

# ========== 侧边栏设置 ==========
with st.sidebar:
    st.header("⚙️ 系统设置")
    api_base_url = st.text_input("后端地址", value="http://127.0.0.1:8000")

# 先创建 client，后续侧边栏和主区域都需要用到
client = LvsheAPIClient(base_url=api_base_url)

with st.sidebar:
    st.divider()
    st.subheader("🤖 模型选择")
    # 获取可用模型列表（4 个 GLM 文本模型）
    try:
        temp_client = LvsheAPIClient(base_url=api_base_url)
        status_data = temp_client.status()
        available_models = status_data.get(
            "available_llm_providers",
            ["glm-4.7-flash", "glm-4.7-flashx", "glm-4.6", "glm-5.2"],
        )
    except Exception:
        available_models = ["glm-4.7-flash", "glm-4.7-flashx", "glm-4.6", "glm-5.2"]

    # 模型显示名映射
    model_display = {
        "glm-4.7-flash": "GLM-4.7-Flash（轻量高速）",
        "glm-4.7-flashx": "GLM-4.7-FlashX（轻量增强）",
        "glm-4.6": "GLM-4.6（通用文本）",
        "glm-5.2": "GLM-5.2（旗舰模型）",
    }
    # 只显示已配置的模型，未匹配的保留原名
    model_options = [m for m in available_models if m in model_display]
    if not model_options:
        model_options = available_models

    selected_model = st.selectbox(
        "选择对话模型",
        options=model_options,
        format_func=lambda x: model_display.get(x, x),
        index=0,
        help="选择要使用的智谱 GLM 文本模型",
    )
    st.info(f"当前使用：{model_display.get(selected_model, selected_model)}")

    st.divider()
    st.subheader("📚 功能模块")
    enable_rag = st.checkbox("🧠 RAG 法律知识库", value=True, help="启用法律知识库检索增强")
    enable_agent = st.checkbox("🤖 Agent 工具调用", value=True, help="启用智能体自动选择工具")
    enable_memory = st.checkbox("💾 长期记忆", value=False, help="启用用户历史记忆")
    enable_stream = st.checkbox("⚡ 流式输出", value=True, help="逐字显示回答，提升体验")

    st.divider()
    st.subheader("⚖️ 案情类型")

    # 从首页传递过来的选择
    default_case_type = st.session_state.get("selected_case_name", "不指定，AI 自动分析")
    case_type_options = ["不指定，AI 自动分析", "民事案件", "行政案件", "刑事案件", "执行案件", "国家赔偿"]

    # 确定默认索引
    default_index = 0
    if default_case_type in case_type_options:
        default_index = case_type_options.index(default_case_type)

    case_type = st.selectbox(
        "选择案情类型（可选）",
        options=case_type_options,
        index=default_index,
        help="选择案情类型可让 AI 更精准地回答，也可在首页选择后直接跳转",
    )

    # 更新 session_state
    if case_type == "不指定，AI 自动分析":
        st.session_state.selected_case_type = None
        st.session_state.selected_case_name = None
    else:
        case_type_map = {
            "民事案件": "civil",
            "行政案件": "administrative",
            "刑事案件": "criminal",
            "执行案件": "execution",
            "国家赔偿": "state_compensation",
        }
        st.session_state.selected_case_type = case_type_map.get(case_type)
        st.session_state.selected_case_name = case_type

    st.divider()
    st.subheader("📄 上传参考文件")
    st.caption("上传法律文件作为参考，支持多选")

    uploaded_files = st.file_uploader(
        "上传文件（支持 .docx .pdf .txt .md）",
        type=["docx", "pdf", "txt", "md"],
        accept_multiple_files=True,
        help="上传后文件内容会作为上下文提供给 AI",
    )

    # 处理上传的文件
    if uploaded_files:
        if "uploaded_file_contents" not in st.session_state:
            st.session_state.uploaded_file_contents = []

        # 检查是否有新文件
        current_filenames = {f.name for f in uploaded_files}
        existing_filenames = {item["filename"] for item in st.session_state.uploaded_file_contents}
        new_files = [f for f in uploaded_files if f.name not in existing_filenames]

        if new_files:
            for uploaded_file in new_files:
                try:
                    with st.spinner(f"解析中：{uploaded_file.name}"):
                        file_bytes = uploaded_file.getvalue()
                        result = client.document_parse(file_bytes, uploaded_file.name)
                        st.session_state.uploaded_file_contents.append({
                            "filename": result["filename"],
                            "content": result["text"],
                            "char_count": result["char_count"],
                        })
                except APIClientError as exc:
                    st.error(f"解析失败 {uploaded_file.name}：{exc}")

        # 显示已上传文件
        if st.session_state.uploaded_file_contents:
            st.success(f"✅ 已上传 {len(st.session_state.uploaded_file_contents)} 个文件")
            for item in st.session_state.uploaded_file_contents:
                with st.expander(f"📄 {item['filename']} ({item['char_count']} 字)"):
                    st.text_area(
                        "文件内容",
                        value=item["content"][:500] + "..." if len(item["content"]) > 500 else item["content"],
                        height=150,
                        disabled=True,
                        key=f"preview_{item['filename']}",
                    )

            if st.button("🗑️ 清除所有上传文件", type="secondary"):
                st.session_state.uploaded_file_contents = []
                st.rerun()

    st.divider()
    st.subheader("🔧 高级设置")
    top_k = st.slider("RAG 检索条数", min_value=1, max_value=10, value=3)
    user_id = st.text_input("用户 ID", value="demo_user")

    if st.button("🗑️ 清空对话历史", type="secondary"):
        st.session_state.messages = []
        st.session_state.uploaded_file_contents = []
        st.rerun()

# ========== 初始化会话历史 ==========
if "messages" not in st.session_state:
    st.session_state.messages = []

# ========== 显示欢迎消息 ==========
if not st.session_state.messages:
    welcome_msg = (
        "你好！我是你的法律咨询助手 ⚖️\n\n"
        "我可以帮你：\n"
        "- 解答各类法律问题\n"
        "- 审查合同风险\n"
        "- 计算法律相关金额\n"
        "- 检索法律条文\n\n"
        "请在下方输入你的问题开始咨询！"
    )
    st.session_state.messages.append({
        "role": "assistant",
        "content": welcome_msg,
    })

# ========== 显示聊天历史 ==========
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# ========== 聊天输入框 ==========
if prompt := st.chat_input("请输入你的法律问题..."):
    # 添加用户消息
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # 生成助手回复
    with st.chat_message("assistant"):
        message_placeholder = st.empty()
        full_response = ""

        try:
            # ========== 构建增强问题 ==========
            enhanced_question = prompt

            # 添加上传文件内容作为上下文
            uploaded_contents = st.session_state.get("uploaded_file_contents", [])
            if uploaded_contents:
                file_context_parts = []
                for item in uploaded_contents:
                    file_context_parts.append(
                        f"【参考文件：{item['filename']}】\n{item['content']}"
                    )
                file_context = "\n\n".join(file_context_parts)
                enhanced_question = f"{file_context}\n\n【用户问题】\n{enhanced_question}\n\n请基于上述参考文件内容回答用户问题。"

            # 添加案情类型提示
            if case_type and case_type != "不指定，AI 自动分析":
                case_type_hint = f"【案情类型】{case_type}\n请针对{case_type}相关的法律规定进行回答。\n\n"
                enhanced_question = case_type_hint + enhanced_question

            # ========== 步骤1：获取记忆上下文 ==========
            memory_context = ""
            saved_memories = []
            if enable_memory:
                try:
                    memory_result = client.memory_chat(
                        message=prompt,
                        user_id=user_id,
                        use_llm=True,
                    )
                    memory_context = memory_result.get("memory_context", "")
                    saved_memories = memory_result.get("saved_memories", [])
                    if memory_context:
                        enhanced_question = f"【用户历史记忆】\n{memory_context}\n\n【用户问题】\n{enhanced_question}"
                except Exception:
                    pass

            # ========== 步骤2：根据模式选择回答方式 ==========
            is_pure_chat = not enable_rag and not enable_agent

            # 用于存放开发者调试信息
            debug_info: dict = {}

            if is_pure_chat:
                # 纯对话模式 - 真正的流式输出
                if enable_stream:
                    for chunk in client.chat_stream(prompt, provider=selected_model):
                        full_response += chunk
                        message_placeholder.markdown(full_response + "▌")
                    message_placeholder.markdown(full_response)
                else:
                    chat_result = client.chat(prompt, provider=selected_model)
                    full_response = chat_result.get("answer", "")
                    message_placeholder.markdown(full_response)

            elif enable_agent:
                # Agent 模式：先用 Agent 调用工具获取上下文，再确保 LLM 生成回答
                with st.spinner("🤖 Agent 正在分析并调用工具..."):
                    agent_result = client.agent_run(
                        question=enhanced_question,
                        use_llm=True,
                    )
                full_response = agent_result.get("final_answer", "")

                # 检查 final_answer 是否是有效的 LLM 回答
                # 如果是 _fallback_final_answer 的输出（以"结论：我已根据问题调用工具"开头），
                # 说明 LLM 失败了，需要重新调用 LLM
                is_invalid_fallback = (
                    not full_response.strip()
                    or full_response.startswith("结论：我已根据问题调用工具")
                )

                if is_invalid_fallback:
                    # Agent 回答无效，用工具结果作为上下文，直接调用 LLM 生成回答
                    with st.spinner("正在生成专业回复..."):
                        tool_context = agent_result.get("tool_result", "")
                        if tool_context and "无需调用" not in tool_context:
                            enhanced_with_tool = (
                                f"【Agent 工具检索结果】\n{tool_context}\n\n"
                                f"【用户问题】\n{prompt}\n\n"
                                f"请基于上述工具检索结果，以专业法律顾问的身份回答用户问题。"
                                f"要求：先给结论，再说明依据，最后给出建议。"
                            )
                        else:
                            enhanced_with_tool = enhanced_question

                        try:
                            chat_result = client.chat(
                                enhanced_with_tool, provider=selected_model
                            )
                            full_response = chat_result.get("answer", "")
                        except Exception:
                            # chat 也失败，用 Agent 的原始回答
                            if not full_response.strip():
                                full_response = "抱歉，AI 服务暂时不可用，请稍后重试。"

                # 流式显示效果
                if enable_stream and full_response:
                    display_text = ""
                    for chunk in stream_text_generator(full_response, chunk_size=5):
                        display_text += chunk
                        message_placeholder.markdown(display_text + "▌")
                    message_placeholder.markdown(display_text)
                else:
                    message_placeholder.markdown(full_response)

                # 收集 Agent 调试信息（稍后折叠显示）
                debug_info["agent"] = agent_result

            elif enable_rag:
                # 纯 RAG 模式
                with st.spinner("🔍 正在检索法律知识库..."):
                    rag_result = client.rag_ask(
                        question=enhanced_question,
                        top_k=top_k,
                        use_llm_query_transform=True,
                        use_llm_hyde=True,
                        use_llm_answer=True,
                    )
                full_response = rag_result.get("answer", "")

                # 如果 RAG 返回空，回退到直接对话
                if not full_response.strip():
                    with st.spinner("正在生成回复..."):
                        try:
                            rag_context = "\n".join(
                                ctx.get("enriched_text", "")
                                for ctx in rag_result.get("contexts", [])
                            )
                            if rag_context:
                                enhanced_with_rag = (
                                    f"【法律知识库检索结果】\n{rag_context}\n\n"
                                    f"【用户问题】\n{prompt}\n\n"
                                    f"请基于上述检索结果回答用户问题。"
                                )
                            else:
                                enhanced_with_rag = enhanced_question
                            chat_result = client.chat(
                                enhanced_with_rag, provider=selected_model
                            )
                            full_response = chat_result.get("answer", "")
                        except Exception:
                            full_response = "抱歉，AI 服务暂时不可用，请稍后重试。"

                # 流式显示效果
                if enable_stream and full_response:
                    display_text = ""
                    for chunk in stream_text_generator(full_response, chunk_size=5):
                        display_text += chunk
                        message_placeholder.markdown(display_text + "▌")
                    message_placeholder.markdown(display_text)
                else:
                    message_placeholder.markdown(full_response)

                # 收集 RAG 调试信息
                debug_info["rag"] = rag_result

            # ========== 开发者调试信息（折叠显示） ==========
            if debug_info.get("agent"):
                agent_result = debug_info["agent"]
                with st.expander("🔧 开发者详情：Agent 执行记录", expanded=False):
                    col1, col2 = st.columns(2)
                    with col1:
                        st.markdown("**调用工具：**")
                        st.code(agent_result.get("tool_name", "无"))
                        st.markdown("**工具输入：**")
                        st.write(agent_result.get("tool_input", "无"))
                    with col2:
                        st.markdown("**执行步骤：**")
                        for step in agent_result.get("steps", []):
                            st.write("- " + step)
                    st.markdown("**工具原始结果：**")
                    st.write(agent_result.get("tool_result", "无"))

            if debug_info.get("rag"):
                rag_result = debug_info["rag"]
                with st.expander("🔧 开发者详情：RAG 检索记录", expanded=False):
                    if rag_result.get("transformed_queries"):
                        st.markdown("**查询改写 (Query Transformation)：**")
                        for item in rag_result["transformed_queries"]:
                            st.write("- " + item)
                    if rag_result.get("hyde_answer"):
                        st.markdown("**HyDE 假设回答：**")
                        st.write(rag_result["hyde_answer"])
                    st.markdown("**检索到的资料：**")
                    for idx, ctx in enumerate(rag_result.get("contexts", []), start=1):
                        st.markdown(f"### 资料 {idx}")
                        st.write(f"来源：{ctx.get('source', '未知')}")
                        st.write(f"相关度分数：{ctx.get('final_score', 0)}")
                        st.write(ctx.get("enriched_text", ""))

            # ========== 记忆信息（折叠显示） ==========
            if enable_memory and (saved_memories or memory_context):
                with st.expander("🧠 记忆信息（开发者）", expanded=False):
                    st.markdown("**本轮使用的记忆：**")
                    st.write(memory_context if memory_context else "暂无相关记忆")
                    st.markdown("**本轮保存的新记忆：**")
                    st.json(saved_memories)

        except APIClientError as exc:
            full_response = f"❌ 出错了：{exc}\n\n请确认后端服务已启动：`uv run uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000`"
            message_placeholder.markdown(full_response)
        except Exception as exc:
            full_response = f"❌ 发生未知错误：{exc}"
            message_placeholder.markdown(full_response)

    # 添加助手回复到历史
    st.session_state.messages.append({"role": "assistant", "content": full_response})

# ========== 底部提示 ==========
st.divider()
st.caption(
    "💡 提示：支持连续对话，可上滑查看历史记录 | "
    f"当前模式：{'RAG + ' if enable_rag else ''}{'Agent + ' if enable_agent else ''}{'Memory + ' if enable_memory else ''}{model_display.get(selected_model, selected_model)}"
)
