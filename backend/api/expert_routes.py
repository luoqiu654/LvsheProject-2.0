"""专家会诊子路由 — 法庭模拟（交互式 SSE）。

端点：
  POST /api/expert/trial/stream       — 启动庭审（SSE 流式交互），实时推送发言
  POST /api/expert/trial/{id}/answer  — 用户提交对法官追问的回答，恢复暂停的流
  GET  /api/expert/trial/{id}         — 获取历史庭审记录
  POST /api/expert/trial              — 启动庭审（非流式），返回完整 TrialResult
  GET  /api/expert/health             — 健康检查

交互式流程：
  1. 前端 POST /trial/stream，建立 SSE 连接
  2. 后端先发 ``trial_started`` 事件（含 trial_id）
  3. 流式推送每个角色发言（thinking/speech/speech_end）
  4. 法官自主判断是否追问；被问方必须回答
  5. 当回答含"不清楚/不知道"时，发 ``user_question`` 事件，流暂停
  6. 前端弹模态窗，用户回答后 POST /trial/{id}/answer
  7. 后端将答案推入 asyncio.Queue，庭审继续
  8. 最终发 ``verdict`` 事件（结构化判决）和 ``done`` 事件
"""
from __future__ import annotations

import asyncio
import json
import time
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from backend.core.court_orchestrator import CourtOrchestrator
from backend.core.llm_gateway import gateway as default_gateway
from backend.core.rag import rag as default_rag
from backend.core.skills import registry as default_skill_registry


router = APIRouter(prefix="/api/expert", tags=["专家会诊"])

# 庭审历史记录（内存存储，进程重启后丢失）
_trial_store: dict[str, dict[str, Any]] = {}

# 交互式庭审运行态：trial_id -> {"queue": asyncio.Queue, "status": str}
# status: "running" / "waiting_answer" / "done"
_trials: dict[str, dict[str, Any]] = {}

# CourtOrchestrator 实例（v3.3 专家会诊重构，注入 gateway/rag/skill_registry 单例）
court_orchestrator = CourtOrchestrator(
    gateway=default_gateway,
    rag=default_rag,
    skill_registry=default_skill_registry,
)


# ========== 请求 / 响应模型 ==========


class TrialRequest(BaseModel):
    """启动庭审请求。"""

    case_description: str = Field(
        ..., min_length=10, description="案件描述（至少 10 字）",
    )
    rounds: int = Field(
        default=2, ge=1, le=5, description="辩论轮数（1-5）",
    )


class AnswerRequest(BaseModel):
    """用户回答法官追问的请求体。"""

    question_id: str = Field(..., description="问题 ID（与 user_question 事件一致）")
    answer: str = Field(..., min_length=1, description="用户的回答")


class TrialStatusResponse(BaseModel):
    """庭审状态。"""

    ok: bool
    llm_available: bool


# ========== 内部工具 ==========


def _new_trial_id() -> str:
    return uuid.uuid4().hex[:16]


def _get_trial(trial_id: str) -> dict[str, Any] | None:
    return _trials.get(trial_id)


def _set_trial_status(trial_id: str, status: str) -> None:
    state = _trials.get(trial_id)
    if state is not None:
        state["status"] = status


# ========== 端点 ==========


@router.get("/health")
async def expert_health() -> dict[str, Any]:
    """专家会诊健康检查。"""
    return {
        "ok": True,
        "llm_available": default_gateway.is_available,
    }


@router.post("/trial")
async def start_trial(request: TrialRequest) -> dict[str, Any]:
    """
    启动庭审（非流式）。

    返回完整的 TrialResult，包含：
    - opening: 审判长开场白
    - rounds: 多轮辩论记录
    - verdict: 法官判决（结构化 + 判决书全文）
    - summary: 庭审总结
    - speeches: 所有发言记录

    注意：庭审可能耗时较长，建议使用流式接口。
    """
    result = await court_simulator.run_trial(
        case_description=request.case_description,
        rounds=request.rounds,
    )
    data = result.to_dict()
    _trial_store[data["trial_id"]] = data
    return data


@router.post("/trial/stream")
async def start_trial_stream(request: TrialRequest) -> StreamingResponse:
    """
    启动庭审（SSE 流式交互）。

    事件格式（data: {JSON}\\n\\n）：
      {"type":"trial_started","trial_id":"..."}
      {"type":"thinking","role":"plaintiff","text":"...","round":1}
      {"type":"speech","role":"plaintiff","text":"...","kind":"statement","round":1}
      {"type":"speech_end","role":"plaintiff","kind":"statement","round":1}
      {"type":"user_question","question_id":"q1_p","question":"...","context":"...","round":1}
      （流暂停，等待用户回答）
      {"type":"user_answer","question_id":"q1_p","answer":"...","round":1}
      {"type":"round_end","round":1}
      {"type":"verdict","verdict":{...},"round":N}
      {"type":"done","trial_id":"...","result":{...}}
      {"type":"error","message":"..."}
    """
    trial_id = _new_trial_id()
    answer_queue: asyncio.Queue[str] = asyncio.Queue()
    _trials[trial_id] = {"queue": answer_queue, "status": "running"}

    async def answer_callback(
        question_id: str, question: str, context: str,
    ) -> str:
        """当法官触发证据询问时调用，阻塞等待用户通过 /answer 端点提交。

        状态已在 generate() 转发 user_question 事件前设置为 "waiting_answer"，
        此处仅阻塞等待用户回答，并增加 5 分钟超时保护避免永久阻塞。

        v3.6 修复：移除 finally 中的 _set_trial_status(trial_id, "running")，
        改为在 generate() 收到 user_answer 事件后再切换状态，消除双击提交时
        的竞态窗口（finally 立即设 running 导致第二次提交被 409 拒绝）。
        """
        try:
            # 超时保护：5 分钟无回答自动回退
            answer = await asyncio.wait_for(answer_queue.get(), timeout=300)
        except asyncio.TimeoutError:
            return "（用户未在规定时间内回答）"
        return answer

    async def generate():
        try:
            async for event in court_orchestrator.stream_trial(
                case=request.case_description,
                rounds=request.rounds,
                answer_callback=answer_callback,
            ):
                # 在转发 user_question 事件前，先设置状态为 waiting_answer
                # （消除竞态窗口：用户在状态切换前提交回答会被 /answer 拒绝）
                if event.get("type") == "user_question":
                    _set_trial_status(trial_id, "waiting_answer")
                    state = _trials.get(trial_id)
                    if state is not None:
                        state["user_question_at"] = time.monotonic()
                # v3.6 修复：收到 user_answer 事件后将状态切回 running
                # （原 answer_callback 的 finally 块立即设 running 导致竞态，
                #   现统一在 generate() 事件流转中管理状态切换）
                if event.get("type") == "user_answer":
                    _set_trial_status(trial_id, "running")
                # 持久化 done 事件的结果
                if event.get("type") == "done":
                    result = event.get("result")
                    if isinstance(result, dict):
                        _trial_store[trial_id] = result
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        except Exception as exc:
            yield f"data: {json.dumps({'type': 'error', 'message': str(exc)}, ensure_ascii=False)}\n\n"
        finally:
            _set_trial_status(trial_id, "done")

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "X-Trial-Id": trial_id,
        },
    )


@router.post("/trial/{trial_id}/answer")
async def submit_trial_answer(
    trial_id: str, request: AnswerRequest,
) -> dict[str, Any]:
    """
    用户提交对法官追问的回答。

    当 SSE 流发出 ``user_question`` 事件后，流会暂停等待用户回答。
    前端收集用户回答后调用此端点，答案会被推入对应庭审的 asyncio.Queue，
    被阻塞的庭审流程随即恢复。

    请求体：
      {"question_id": "q1_p", "answer": "是，我持有书面合同"}
    """
    state = _get_trial(trial_id)
    if state is None:
        raise HTTPException(
            status_code=404,
            detail=f"庭审不存在或已结束：{trial_id}",
        )
    # 竞态容错：若状态为 running 但距 user_question 时间 < 5s，
    # 短暂等待状态切换到 waiting_answer 后再判定
    if state["status"] == "running":
        user_q_at = state.get("user_question_at")
        if user_q_at is not None and (time.monotonic() - user_q_at) < 5:
            # 短暂等待状态切换（最多 2 秒）
            for _ in range(20):
                await asyncio.sleep(0.1)
                state = _get_trial(trial_id)
                if state is None:
                    raise HTTPException(
                        status_code=404,
                        detail=f"庭审不存在或已结束：{trial_id}",
                    )
                if state["status"] == "waiting_answer":
                    break
    if state["status"] != "waiting_answer":
        raise HTTPException(
            status_code=409,
            detail=f"当前庭审未在等待回答（状态：{state['status']}）",
        )
    queue: asyncio.Queue[str] = state["queue"]
    await queue.put(request.answer)
    return {
        "ok": True,
        "trial_id": trial_id,
        "question_id": request.question_id,
        "status": "resumed",
    }


@router.get("/trial/{trial_id}")
async def get_trial(trial_id: str) -> dict[str, Any]:
    """获取历史庭审记录。"""
    data = _trial_store.get(trial_id)
    if not data:
        raise HTTPException(
            status_code=404,
            detail=f"庭审记录不存在：{trial_id}（可能已过期或未创建）",
        )
    return data
