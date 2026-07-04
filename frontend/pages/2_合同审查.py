from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from frontend.api_client import APIClientError, LvsheAPIClient, stream_text_generator


st.set_page_config(
    page_title="合同审查",
    page_icon="📄",
    layout="wide",
)

st.title("📄 合同审查")
st.caption("调用 Agent Skills，对合同条款进行风险初筛，并生成带标注的修订版文件。")

with st.sidebar:
    st.header("后端设置")
    api_base_url = st.text_input("FastAPI 地址", value="http://127.0.0.1:8000")
    use_llm = st.checkbox("启用 LLM 总结", value=True)
    enable_stream = st.checkbox("⚡ 启用流式输出", value=True, help="逐字显示审查结果，提升体验")

    skill_mode = st.radio(
        "Skill 模式",
        ["自动匹配", "固定使用 contract-risk-review"],
    )

    st.divider()
    st.subheader("🧠 长期记忆")
    enable_memory = st.checkbox("启用长期记忆", value=False)
    user_id = st.text_input("用户 ID", value="demo_user")
    save_to_memory = st.checkbox("审查后保存到记忆", value=True)

    if enable_memory:
        st.info("已启用记忆：审查时会参考历史合同审查记录")

    st.divider()
    st.subheader("📁 文件管理")
    show_files = st.checkbox("显示我的文件", value=False)

client = LvsheAPIClient(base_url=api_base_url)

# ========== 初始化会话历史 ==========
if "contract_history" not in st.session_state:
    st.session_state.contract_history = []

if "last_review_result" not in st.session_state:
    st.session_state.last_review_result = None

if "last_contract_text" not in st.session_state:
    st.session_state.last_contract_text = ""

if "pending_annotation" not in st.session_state:
    st.session_state.pending_annotation = False

# ========== 文件列表（侧边栏） ==========
if show_files:
    with st.sidebar:
        st.divider()
        st.subheader("📂 我的文件")
        try:
            files_result = client.contract_list_files(user_id)
            files = files_result.get("files", [])
            if files:
                for f in files:
                    st.markdown(f"- {f.get('filename', '未知')}")
            else:
                st.info("暂无文件")
        except APIClientError as exc:
            st.error(f"获取文件列表失败：{exc}")

st.subheader("📄 上传合同文件")
st.caption("支持 Word(.docx)、PDF(.pdf)、纯文本(.txt/.md) 格式，可同时上传多个文件")

uploaded_files = st.file_uploader(
    "上传合同文件（支持多选）",
    type=["docx", "pdf", "txt", "md"],
    accept_multiple_files=True,
    help="上传后自动提取文本内容，多个文件会合并显示，也可以手动修改",
)

if uploaded_files:
    all_texts = []
    success_count = 0
    fail_count = 0

    for uploaded_file in uploaded_files:
        try:
            with st.spinner(f"正在解析：{uploaded_file.name}..."):
                file_bytes = uploaded_file.getvalue()
                result = client.document_parse(file_bytes, uploaded_file.name)

            all_texts.append(
                f"{'='*60}\n"
                f"文件：{result['filename']}（{result['char_count']} 字）\n"
                f"{'='*60}\n\n"
                f"{result['text']}\n"
            )
            success_count += 1

        except APIClientError as exc:
            all_texts.append(
                f"{'='*60}\n"
                f"文件：{uploaded_file.name}（解析失败）\n"
                f"{'='*60}\n\n"
                f"错误：{exc}\n"
            )
            fail_count += 1

    if success_count > 0:
        st.success(f"✅ 成功解析 {success_count} 个文件" + (f"，失败 {fail_count} 个" if fail_count else ""))

        # 将解析结果填入文本框
        combined_text = "\n\n".join(all_texts)
        st.session_state.uploaded_text = combined_text
        st.info(f"已将 {success_count} 个文件的内容合并填入下方文本框，可继续编辑后再审查")
    else:
        st.error("所有文件解析失败，请检查文件格式")

sample_contract = """甲方委托乙方开发网站，费用5000元。
双方约定乙方完成网站设计与开发。
但合同中没有明确交付时间、验收标准、违约责任和争议解决方式。
"""

# 如果有上传的文本，优先使用
default_text = st.session_state.get("uploaded_text", sample_contract)

contract_text = st.text_area(
    "合同内容（可手动编辑）",
    value=default_text,
    height=260,
)

# ========== 审查按钮 ==========
col1, col2 = st.columns([1, 4])

with col1:
    review_button = st.button("开始审查", type="primary")

with col2:
    generate_button = st.button(
        "📝 生成带标注的修订版",
        disabled=not st.session_state.pending_annotation,
        help="审查完成后可生成带红色高亮和批注的修订版Word文件",
    )

if review_button:
    if not contract_text.strip():
        st.warning("请输入合同内容。")
        st.stop()

    skill_name = None
    if skill_mode == "固定使用 contract-risk-review":
        skill_name = "contract-risk-review"

    try:
        with st.spinner("正在审查合同风险..."):
            # ========== 步骤1：检索记忆（如果开启） ==========
            memory_context = ""
            if enable_memory:
                memory_result = client.memory_chat(
                    message=f"合同审查：{contract_text[:200]}...",
                    user_id=user_id,
                    use_llm=use_llm,
                )
                memory_context = memory_result["memory_context"]

            # ========== 步骤2：构建增强输入 ==========
            enhanced_input = contract_text
            if enable_memory and memory_context:
                enhanced_input = f"【历史审查记忆】\n{memory_context}\n\n【当前合同内容】\n{contract_text}"

            # ========== 步骤3：执行 Skill 审查 ==========
            result = client.skill_run(
                input_text=enhanced_input,
                skill_name=skill_name,
                use_llm=use_llm,
            )

        st.success(f"已使用 Skill：{result['skill_name']}")

        st.subheader("📌 审查结果")

        if enable_stream:
            # 流式输出
            answer_placeholder = st.empty()
            full_text = ""
            for chunk in stream_text_generator(result["output_text"], chunk_size=5):
                full_text += chunk
                answer_placeholder.markdown(full_text + "▌")
            answer_placeholder.markdown(full_text)
        else:
            st.markdown(result["output_text"])

        # ========== 步骤4：保存审查结果 ==========
        st.session_state.last_review_result = result
        st.session_state.last_contract_text = contract_text
        st.session_state.pending_annotation = True

        # ========== 步骤5：显示确认提示 ==========
        st.info(
            "💡 审查完成！点击上方「生成带标注的修订版」按钮，"
            "可以生成带红色高亮和风险批注的Word文件，方便下载和分享。"
        )

        # ========== 步骤6：保存到会话历史 ==========
        st.session_state.contract_history.insert(0, {
            "contract": contract_text[:100] + "..." if len(contract_text) > 100 else contract_text,
            "result": result["output_text"],
            "skill": result["skill_name"],
        })

        # 只保留最近 10 条
        if len(st.session_state.contract_history) > 10:
            st.session_state.contract_history = st.session_state.contract_history[:10]

        # ========== 步骤7：显示记忆信息（如果开启） ==========
        if enable_memory:
            with st.expander("🧠 长期记忆"):
                st.markdown("**参考的历史记忆：**")
                st.write(memory_context if memory_context else "暂无相关历史记忆")
                if save_to_memory:
                    st.success("✅ 本次审查结果已自动保存到记忆")

        with st.expander("📦 使用的技能资源"):
            if result["used_resources"]:
                for item in result["used_resources"]:
                    st.write("- " + item)
            else:
                st.write("无额外资源。")

    except APIClientError as exc:
        st.error(str(exc))

# ========== 生成带标注的修订版 ==========
if generate_button and st.session_state.pending_annotation:
    try:
        with st.spinner("正在生成带标注的修订版文件..."):
            # 从审查结果中提取风险点（简化版）
            review_text = st.session_state.last_review_result["output_text"]
            risk_points = _extract_risk_points_simple(review_text)

            # 调用API生成标注文件
            result = client.contract_generate_annotated(
                original_file_name="contract_review.docx",
                contract_text=st.session_state.last_contract_text,
                risk_points=risk_points,
                user_id=user_id,
            )

        st.success("✅ 带标注的修订版文件已生成！")

        # 显示文件信息
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("风险点总数", result.get("risk_count", 0))
        with col2:
            st.metric("高风险", result.get("high_risk_count", 0))
        with col3:
            st.metric("中风险", result.get("medium_risk_count", 0))

        # 下载按钮
        st.markdown("### 📥 下载文件")

        filename = result.get("annotated_filename", "annotated_contract.docx")
        download_url = client.contract_download_url(filename, user_id)

        st.markdown(
            f'<a href="{download_url}" target="_blank" '
            f'style="display: inline-block; padding: 10px 20px; '
            f'background-color: #4CAF50; color: white; text-decoration: none; '
            f'border-radius: 5px; font-weight: bold;">'
            f'⬇️ 下载带标注的修订版（{filename}）</a>',
            unsafe_allow_html=True,
        )

        st.caption("文件包含：红色高亮的问题条款 + 批注形式的风险说明")

        # 重置状态
        st.session_state.pending_annotation = False

    except APIClientError as exc:
        st.error(f"生成标注文件失败：{exc}")


def _extract_risk_points_simple(review_text: str) -> list[dict]:
    """
    从审查结果文本中简单提取风险点。

    实际项目中应该让Skill输出结构化的风险点。
    这里做简化处理。
    """
    risk_points = []
    lines = review_text.split("\n")

    current_risk = None
    for line in lines:
        line = line.strip()

        # 检测风险点
        if line.startswith(("风险", "问题", "⚠️", "🔴", "🟡", "🟢")) or "风险" in line[:10]:
            if current_risk:
                risk_points.append(current_risk)

            severity = "medium"
            if "高风险" in line or "🔴" in line or "严重" in line or "重大" in line:
                severity = "high"
            elif "低风险" in line or "🟢" in line or "轻微" in line:
                severity = "low"

            current_risk = {
                "clause": line[:50],
                "risk_type": "合同风险",
                "severity": severity,
                "description": line,
                "suggestion": "建议修改相关条款",
            }
        elif current_risk and line and not line.startswith(("建议", "说明")):
            current_risk["description"] += "\n" + line

    if current_risk:
        risk_points.append(current_risk)

    # 如果没有解析到，创建默认风险点
    if not risk_points:
        risk_points.append({
            "clause": "合同整体审查",
            "risk_type": "general",
            "severity": "medium",
            "description": review_text[:200],
            "suggestion": "建议仔细审查合同条款，确保各方权益明确",
        })

    return risk_points


# ========== 显示会话历史 ==========
st.divider()

with st.expander(f"📜 本次审查历史（{len(st.session_state.contract_history)} 条）", expanded=False):
    if not st.session_state.contract_history:
        st.info("暂无历史记录，开始你的第一次合同审查吧！")
    else:
        for idx, item in enumerate(st.session_state.contract_history):
            st.markdown(f"**审查 {idx+1}（{item['skill']}）**")
            st.markdown(f"合同摘要：{item['contract']}")
            st.markdown(f"审查结果：{item['result'][:150]}...")
            st.divider()

st.divider()

st.subheader("✅ 建议重点检查项")

st.markdown(
    """
    - 合同主体是否明确
    - 标的和交付成果是否明确
    - 付款金额和付款时间是否明确
    - 交付时间是否明确
    - 验收标准是否明确
    - 违约责任是否明确
    - 争议解决方式是否明确
    - 解除条件是否明确
    - 知识产权归属是否明确
    """
)

st.divider()

st.info(
    "💡 **使用提示**：\n"
    "1. 上传合同文件或直接粘贴合同内容\n"
    "2. 点击「开始审查」进行风险初筛\n"
    "3. 审查完成后，点击「生成带标注的修订版」获取Word文件\n"
    "4. 所有生成的文件都保存在你的个人目录下，可随时下载"
)
