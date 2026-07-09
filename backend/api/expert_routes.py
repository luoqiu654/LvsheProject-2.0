"""专家会诊子路由 — 法庭模拟。

端点：
  POST /api/expert/trial          — 启动庭审（非流式），返回完整 TrialResult
  POST /api/expert/trial/stream    — 启动庭审（SSE 流式），实时推送每个角色发言
  GET  /api/expert/trials/{id}     — 获取历史庭审记录
  GET  /api/expert/health          — 健康检查
"""
from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from backend.core.multi_agents import court_simulator


router = APIRouter(prefix="/api/expert", tags=["专家会诊"])

# 庭审历史记录（内存存储，进程重启后丢失）
_trial_store: dict[str, dict[str, Any]] = {}


# ========== 请求 / 响应模型 ==========


class TrialRequest(BaseModel):
    """启动庭审请求。"""

    case_description: str = Field(
        ..., min_length=10, description="案件描述（至少 10 字）",
    )
    rounds: int = Field(
        default=2, ge=1, le=5, description="辩论轮数（1-5）",
    )


class TrialStatusResponse(BaseModel):
    """庭审状态。"""

    ok: bool
    llm_available: bool


# ========== 端点 ==========


@router.get("/health")
async def expert_health() -> dict[str, Any]:
    """专家会诊健康检查。"""
    return {
        "ok": True,
        "llm_available": court_simulator.gateway.is_available,
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

    注意：庭审可能耗时较长（每轮 3 次 LLM 调用 + 1 次判决），
    建议前端设置 5 分钟以上超时，或使用流式接口。
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
    启动庭审（SSE 流式）。

    实时推送每个角色的发言片段，事件格式：
      data: {"event":"speech_start","role":"chief_judge","round":0}\\n\\n
      data: {"event":"speech_chunk","role":"chief_judge","text":"...","round":0}\\n\\n
      data: {"event":"speech_end","role":"chief_judge","round":0}\\n\\n
      ...
      data: {"event":"done","trial_id":"...","result":{...}}\\n\\n
      data: {"event":"error","message":"..."}\\n\\n
    """

    async def generate():
        try:
            async for event in court_simulator.stream_trial(
                case_description=request.case_description,
                rounds=request.rounds,
            ):
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        except Exception as exc:
            yield f"data: {json.dumps({'event': 'error', 'message': str(exc)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/trials/{trial_id}")
async def get_trial(trial_id: str) -> dict[str, Any]:
    """获取历史庭审记录。"""
    data = _trial_store.get(trial_id)
    if not data:
        raise HTTPException(
            status_code=404,
            detail=f"庭审记录不存在：{trial_id}（可能已过期或未创建）",
        )
    return data
