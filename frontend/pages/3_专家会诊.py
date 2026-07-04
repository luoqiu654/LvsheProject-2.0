from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from frontend.api_client import APIClientError, LvsheAPIClient, stream_text_generator


st.set_page_config(
    page_title="专家会诊",
    page_icon="⚖️",
    layout="wide",
)

st.title("⚖️ 多智能体专家会诊")
st.caption("Researcher + 原告代理 + 被告代理 + 中立法官，多轮辩论后给出明确判决。")

with st.sidebar:
    st.header("后端设置")
    api_base_url = st.text_input("FastAPI 地址", value="http://127.0.0.1:8000")
    use_llm = st.checkbox("启用 LLM 多智能体分析", value=True)
    enable_stream = st.checkbox("⚡ 启用流式输出", value=True, help="逐字显示辩论和判决结果，提升体验")

    st.divider()
    st.subheader("🎯 辩论设置")
    max_rounds = st.slider("辩论轮数", min_value=1, max_value=5, value=3)
    st.caption(f"当前设置：{max_rounds} 轮辩论，原告被告轮流发言")

    st.divider()
    st.subheader("🧠 长期记忆")
    enable_memory = st.checkbox("启用长期记忆", value=False)
    user_id = st.text_input("用户 ID", value="demo_user")
    save_to_memory = st.checkbox("会诊后保存到记忆", value=True)

    if enable_memory:
        st.info("已启用记忆：会诊时会参考历史案件分析记录")

client = LvsheAPIClient(base_url=api_base_url)

# ========== 初始化会话历史 ==========
if "debate_history" not in st.session_state:
    st.session_state.debate_history = []

sample_case = """甲方委托乙方开发网站，合同金额5000元。
乙方迟迟没有交付，合同没有明确写交付时间，也没有明确违约金。
甲方想要求赔偿，应该怎么办？
"""

case_text = st.text_area(
    "请输入案件事实",
    value=sample_case,
    height=220,
)

if st.button("开始专家会诊", type="primary"):
    if not case_text.strip():
        st.warning("请输入案件事实。")
        st.stop()

    try:
        with st.spinner(f"多智能体正在进行 {max_rounds} 轮辩论，可能需要几十秒..."):
            # ========== 步骤1：检索记忆（如果开启） ==========
            memory_context = ""
            if enable_memory:
                memory_result = client.memory_chat(
                    message=f"案件分析：{case_text[:200]}...",
                    user_id=user_id,
                    use_llm=use_llm,
                )
                memory_context = memory_result["memory_context"]

            # ========== 步骤2：构建增强输入 ==========
            enhanced_case = case_text
            if enable_memory and memory_context:
                enhanced_case = f"【历史案件记忆】\n{memory_context}\n\n【当前案件事实】\n{case_text}"

            # ========== 步骤3：多智能体会诊 ==========
            result = client.multi_agents_debate(
                case=enhanced_case,
                use_llm=use_llm,
                max_rounds=max_rounds,
            )

        # ========== 步骤4：显示执行步骤 ==========
        with st.expander("🧭 执行步骤", expanded=False):
            for step in result["steps"]:
                st.write("- " + step)

        # ========== 步骤5：显示记忆信息（如果开启） ==========
        if enable_memory:
            with st.expander("🧠 长期记忆"):
                st.markdown("**参考的历史记忆：**")
                st.write(memory_context if memory_context else "暂无相关历史记忆")
                if save_to_memory:
                    st.success("✅ 本次会诊结果已自动保存到记忆")

        # ========== 步骤6：显示法律检索结果 ==========
        with st.expander("🔎 法律检索员", expanded=False):
            st.markdown(result["research_summary"])

        # ========== 步骤7：显示多轮辩论 ==========
        st.subheader("🗣️ 多轮法庭辩论")

        for round_data in result["debate_rounds"]:
            round_num = round_data["round_num"]

            st.markdown(f"### 第 {round_num} 轮")

            col1, col2 = st.columns(2)

            with col1:
                st.info(f"👤 原告代理律师 - 第 {round_num} 轮陈述")
                if enable_stream:
                    placeholder = st.empty()
                    full_text = ""
                    for chunk in stream_text_generator(round_data["plaintiff_statement"], chunk_size=5):
                        full_text += chunk
                        placeholder.markdown(full_text + "▌")
                    placeholder.markdown(full_text)
                else:
                    st.markdown(round_data["plaintiff_statement"])

            with col2:
                st.warning(f"👤 被告代理律师 - 第 {round_num} 轮抗辩")
                if enable_stream:
                    placeholder = st.empty()
                    full_text = ""
                    for chunk in stream_text_generator(round_data["defendant_statement"], chunk_size=5):
                        full_text += chunk
                        placeholder.markdown(full_text + "▌")
                    placeholder.markdown(full_text)
                else:
                    st.markdown(round_data["defendant_statement"])

            st.divider()

        # ========== 步骤8：显示法官最终判决 ==========
        st.subheader("⚖️ 法官最终判决")

        verdict = result["judge_verdict"]

        # 判决结果大卡片
        if verdict["winner"] == "原告":
            st.success(f"### 🎯 判决结果：**原告更可能胜诉**")
        elif verdict["winner"] == "被告":
            st.error(f"### 🎯 判决结果：**被告更可能胜诉**")
        else:
            st.warning(f"### 🎯 判决结果：**暂时无法判断，需更多证据**")

        # 胜率条形图（用进度条模拟）
        st.markdown("#### 📊 胜率评估")
        col1, col2 = st.columns(2)
        with col1:
            st.metric("原告胜诉概率", f"{verdict['plaintiff_win_rate']:.0f}%")
            st.progress(verdict["plaintiff_win_rate"] / 100)
        with col2:
            st.metric("被告胜诉概率", f"{verdict['defendant_win_rate']:.0f}%")
            st.progress(verdict["defendant_win_rate"] / 100)

        st.divider()

        # 关键胜负点
        st.markdown("#### 🔑 关键胜负点")
        for i, point in enumerate(verdict["key_points"], start=1):
            st.markdown(f"{i}. {point}")

        st.divider()

        # 判决理由
        st.markdown("#### 📝 判决理由")
        if enable_stream:
            placeholder = st.empty()
            full_text = ""
            for chunk in stream_text_generator(verdict["reasoning"], chunk_size=5):
                full_text += chunk
                placeholder.markdown(full_text + "▌")
            placeholder.markdown(full_text)
        else:
            st.write(verdict["reasoning"])

        st.divider()

        # 行动建议
        st.markdown("#### 💡 实务行动建议")
        for i, suggestion in enumerate(verdict["action_suggestions"], start=1):
            st.markdown(f"{i}. {suggestion}")

        st.divider()

        # 法官详细总结
        with st.expander("📜 法官详细总结全文"):
            st.markdown(result["judge_summary"])

        # ========== 保存到会话历史 ==========
        verdict = result["judge_verdict"]
        st.session_state.debate_history.insert(0, {
            "case": case_text[:100] + "..." if len(case_text) > 100 else case_text,
            "winner": verdict["winner"],
            "plaintiff_rate": verdict["plaintiff_win_rate"],
            "defendant_rate": verdict["defendant_win_rate"],
            "rounds": max_rounds,
        })

        # 只保留最近 5 条
        if len(st.session_state.debate_history) > 5:
            st.session_state.debate_history = st.session_state.debate_history[:5]

    except APIClientError as exc:
        st.error(str(exc))

# ========== 显示会话历史 ==========
st.divider()

with st.expander(f"📜 本次会诊历史（{len(st.session_state.debate_history)} 条）", expanded=False):
    if not st.session_state.debate_history:
        st.info("暂无历史记录，开始你的第一次专家会诊吧！")
    else:
        for idx, item in enumerate(st.session_state.debate_history):
            st.markdown(f"**会诊 {idx+1}（{item['rounds']} 轮辩论）**")
            st.markdown(f"案件摘要：{item['case']}")
            st.markdown(f"判决结果：**{item['winner']}** ｜ 原告 {item['plaintiff_rate']:.0f}% vs 被告 {item['defendant_rate']:.0f}%")
            st.divider()

st.divider()

st.info("提示：如果 LLM 模式太慢，可以在左侧关闭 LLM，使用本地规则模式快速演示。增加辩论轮数会让论证更充分，但耗时也会更长。")
