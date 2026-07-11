"""法庭模拟常量定义（v3.7 从 multi_agents.py 提取）。

包含角色标识、发言种类、System Prompts、模型选择和关键词模式。
被 ``court_agents.py``、``court_orchestrator.py`` 和 ``debate_adapter.py`` 引用。
"""
from __future__ import annotations

from backend.config import settings


# ========== 角色常量 ==========

ROLE_CHIEF_JUDGE = "chief_judge"   # 审判长
ROLE_PLAINTIFF = "plaintiff"       # 原告
ROLE_DEFENDANT = "defendant"       # 被告
ROLE_JUDGE = "judge"               # 中立法官
ROLE_VERDICT = "verdict"           # 判决

# 发言种类（用于区分陈述 / 追问 / 回答）
KIND_OPENING = "opening"
KIND_STATEMENT = "statement"       # 原被告陈述
KIND_INQUIRY = "inquiry"           # 法官追问
KIND_ANSWER = "answer"             # 原被告回答法官
KIND_VERDICT = "verdict"
KIND_USER = "user"                 # 用户回答

# ========== System Prompts ==========

SYSTEM_CHIEF_JUDGE = (
    "你是庭审审判长（主Agent），负责组织庭审秩序与控制节奏。根据案件描述，拆分案件核心事实，"
    "分别向原告和被告介绍。用庄重威严的语气。"
    "你同时也是用户与庭审之间的桥梁：当法官认为某项关键证据对判决有重大影响，"
    "且原被告双方均无法确认是否能提供该证据时，由你向用户（当事人）发起询问，"
    "让用户回答是否持有相关证据。"
)

SYSTEM_PLAINTIFF = (
    "你是原告代理人。\n"
    "1. 代表原告利益，坚定有力地陈述\n"
    "2. 必须正面回答法官的追问，不得回避\n"
    "3. 如果你方确实不清楚某个事实，如实回答\"不清楚此事，需要当事人确认\"\n"
    "4. 引用法律条文支持你的主张"
)

SYSTEM_DEFENDANT = (
    "你是被告代理人。\n"
    "1. 代表被告利益，坚定有力地陈述\n"
    "2. 必须正面回答法官的追问，不得回避\n"
    "3. 如果你方确实不清楚某个事实，如实回答\"不清楚此事，需要当事人确认\"\n"
    "4. 引用法律条文支持你的主张"
)

SYSTEM_JUDGE = (
    "你是中立法官，正在审理一起案件。你的职责：\n"
    "1. 仔细倾听原告和被告的辩论，发现矛盾点和证据薄弱环节\n"
    "2. 主动追问，不要和稀泥。如果某方说法有漏洞，直接追问\n"
    "3. 如果双方都无法确认关键事实，向用户询问补充信息\n"
    "4. 只有当用户也表示不知道时，才判定证据不足\n"
    "5. 最终判决要明确：谁胜诉、谁败诉、为什么、引用哪条法律\n"
    "6. 不要给出\"原告50%被告50%\"这种端水判决\n"
    "你是犀利、专业、公正的法官。"
)

# ========== 模型选择（从配置读取，支持多供应商） ==========

MODEL_SPEECH = settings.active_model_speech    # 陈述/回答（有思考过程可展示）
MODEL_DECISION = settings.active_model_decision  # 法官追问决策（稳定 JSON）
MODEL_VERDICT = settings.active_model_verdict    # 最终判决（旗舰）

# ========== 关键词模式 ==========

# 当事人"不清楚"关键事实的关键词（触发向用户询问）
UNCLEAR_PATTERNS = (
    "不清楚", "不知道", "无法确认", "暂无此证据", "需要当事人确认",
    "无法提供", "记不清", "不记得", "尚无证据", "无法核实",
)

# 用户明确表示"不知道"的关键词（触发证据不足判决）
USER_UNKNOWN_PATTERNS = (
    "不知道", "不清楚", "无法确认", "记不清", "不记得", "无从得知", "确实没有",
)
