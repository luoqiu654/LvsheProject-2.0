from __future__ import annotations

import asyncio
from dataclasses import asdict
import json
import tempfile
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse

from backend.config import PROJECT_ROOT, settings
from backend.api.schemas import (
    AgentRunRequest,
    AgentRunResponse,
    ChatRequest,
    ChatResponse,
    CommandResponse,
    ConfirmCommandRequest,
    ContractReviewRequest,
    ContractReviewResponse,
    DocumentParseResponse,
    FileInfoSchema,
    GenerateAnnotatedRequest,
    GenerateAnnotatedResponse,
    GraphNodeSchema,
    GraphRAGAnswerResponse,
    GraphRAGSearchRequest,
    GraphRAGSearchResponse,
    GraphRelationSchema,
    GraphStatsResponse,
    GUIBrowseRequest,
    GUIBrowseResponse,
    ImageAnalyzeResponse,
    ImageGenerateRequest,
    ImageGenerateResponse,
    ImageSearchRequest,
    ImageSearchResponse,
    ImageSearchResultSchema,
    IndexSampleResponse,
    ListFilesRequest,
    ListFilesResponse,
    MemoryChatRequest,
    MemoryChatResponse,
    ModelsInfoResponse,
    MultiAgentDebateRequest,
    MultiAgentDebateResponse,
    MultiTurnChatRequest,
    RAGAskRequest,
    RAGAskResponse,
    RiskPointSchema,
    SkillRunRequest,
    SkillRunResponse,
    StatusResponse,
    VisionAnalyzeRequest,
    VisionAnalyzeResponse,
)
from backend.core.agents import agent
from backend.core.contract_annotator import contract_annotator
from backend.core.gui_agent import gui_agent
from backend.core.llm_gateway import LLMGatewayError, gateway
from backend.core.memory import memory_manager
from backend.core.multi_agents import multi_agent_debate
from backend.core.rag import rag
from backend.core.safe_commands import CommandType, safe_command_executor
from backend.core.skills import skill_executor
from backend.utils.document_parser import DocumentParseError, document_parser


router = APIRouter(prefix="/api", tags=["LvsheProject API"])

# 延迟导入，避免循环导入
_image_rag = None
_graph_rag = None


def _get_image_rag():
    global _image_rag
    if _image_rag is None:
        from backend.core.image_rag import get_image_rag
        _image_rag = get_image_rag()
    return _image_rag


def _get_graph_rag():
    global _graph_rag
    if _graph_rag is None:
        from backend.core.graph_rag import get_graph_rag
        _graph_rag = get_graph_rag()
    return _graph_rag


@router.get("/status", response_model=StatusResponse)
async def status() -> StatusResponse:
    # 检查各模块状态
    modules = {
        "llm_gateway": True,
        "rag": True,
        "agent": True,
        "skills": True,
        "memory": True,
        "gui_agent": True,
        "multi_agents": True,
        "contract_annotator": True,
        "safe_commands": True,
    }

    # 检查图像RAG
    try:
        image_rag = _get_image_rag()
        modules["image_rag"] = settings.image_rag_enabled
    except Exception:
        modules["image_rag"] = False

    # 检查Graph RAG
    try:
        graph_rag = _get_graph_rag()
        stats = graph_rag.get_stats()
        modules["graph_rag"] = settings.graph_rag_enabled
        modules["graph_rag_connected"] = stats.get("is_connected", False)
    except Exception:
        modules["graph_rag"] = False

    # 检查文档解析增强
    try:
        parser_info = document_parser.get_parser_info()
        modules["unstructured"] = parser_info.get("unstructured_available", False)
        modules["minio"] = parser_info.get("minio_connected", False)
    except Exception:
        modules["unstructured"] = False
        modules["minio"] = False

    return StatusResponse(
        app_name=settings.app_name,
        available_llm_providers=gateway.available_providers(),
        modules=modules,
    )


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    try:
        answer = await gateway.chat_text(
            user_message=request.message,
            provider=request.provider,
        )
        return ChatResponse(answer=answer)

    except LLMGatewayError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/rag/index-sample", response_model=IndexSampleResponse)
async def index_sample() -> IndexSampleResponse:
    # 用 asyncio.to_thread 在线程中运行同步方法，避免阻塞事件循环
    indexed = await asyncio.to_thread(
        rag.index_directory, PROJECT_ROOT / "data" / "raw"
    )

    return IndexSampleResponse(
        indexed_chunks=indexed,
        total_chunks=rag.count(),
    )


@router.post("/rag/ask", response_model=RAGAskResponse)
async def rag_ask(request: RAGAskRequest) -> RAGAskResponse:
    result = await rag.answer(
        question=request.question,
        top_k=request.top_k,
        use_llm_query_transform=request.use_llm_query_transform,
        use_llm_hyde=request.use_llm_hyde,
        use_llm_answer=request.use_llm_answer,
    )

    contexts = [
        {
            "chunk_id": item.chunk_id,
            "text": item.text,
            "enriched_text": item.enriched_text,
            "source": item.source,
            "distance": item.distance,
            "keyword_score": item.keyword_score,
            "final_score": item.final_score,
        }
        for item in result.contexts
    ]

    return RAGAskResponse(
        question=result.question,
        answer=result.answer,
        transformed_queries=result.transformed_queries,
        hyde_answer=result.hyde_answer,
        contexts=contexts,
    )


@router.post("/agent/run", response_model=AgentRunResponse)
async def agent_run(request: AgentRunRequest) -> AgentRunResponse:
    result = await agent.run(
        question=request.question,
        use_llm=request.use_llm,
    )

    return AgentRunResponse(
        question=result.question,
        final_answer=result.final_answer,
        tool_name=result.tool_name,
        tool_input=result.tool_input,
        tool_result=result.tool_result,
        steps=result.steps,
    )


@router.post("/skills/run", response_model=SkillRunResponse)
async def skill_run(request: SkillRunRequest) -> SkillRunResponse:
    if request.skill_name:
        result = await skill_executor.execute(
            skill_name=request.skill_name,
            input_text=request.input_text,
            use_llm=request.use_llm,
        )
    else:
        result = await skill_executor.execute_best_match(
            input_text=request.input_text,
            use_llm=request.use_llm,
        )

    return SkillRunResponse(
        skill_name=result.skill_name,
        input_text=result.input_text,
        output_text=result.output_text,
        used_resources=result.used_resources,
    )


@router.post("/memory/chat", response_model=MemoryChatResponse)
async def memory_chat(request: MemoryChatRequest) -> MemoryChatResponse:
    result = await memory_manager.chat_with_memory(
        message=request.message,
        user_id=request.user_id,
        use_llm=request.use_llm,
    )

    saved_memories = []
    for item in result["saved_memories"]:
        if hasattr(item, "__dataclass_fields__"):
            saved_memories.append(asdict(item))
        else:
            saved_memories.append({"raw": str(item)})

    return MemoryChatResponse(
        user_id=result["user_id"],
        message=result["message"],
        memory_context=result["memory_context"],
        answer=result["answer"],
        saved_memories=saved_memories,
    )


@router.post("/gui/browse", response_model=GUIBrowseResponse)
async def gui_browse(request: GUIBrowseRequest) -> GUIBrowseResponse:
    result = await gui_agent.run(
        task=request.task,
        start_url=str(request.start_url),
        take_screenshot=request.take_screenshot,
        use_llm_summary=request.use_llm_summary,
        use_browser=request.use_browser,
    )

    return GUIBrowseResponse(
        task=result.task,
        start_url=result.start_url,
        title=result.observation.title,
        url=result.observation.url,
        text_preview=result.observation.text_preview,
        links=[
            {
                "text": link.text,
                "href": link.href,
            }
            for link in result.observation.links
        ],
        screenshot_path=result.observation.screenshot_path,
        summary=result.summary,
        steps=result.steps,
    )


@router.post("/multi-agents/debate", response_model=MultiAgentDebateResponse)
async def multi_agents_debate(
    request: MultiAgentDebateRequest,
) -> MultiAgentDebateResponse:
    result = await multi_agent_debate.run(
        case=request.case,
        use_llm=request.use_llm,
        max_rounds=request.max_rounds,
    )

    # 多轮辩论记录
    debate_rounds = [
        {
            "round_num": r.round_num,
            "plaintiff_statement": r.plaintiff_statement,
            "defendant_statement": r.defendant_statement,
        }
        for r in result.debate_rounds
    ]

    # 法官判决
    judge_verdict = {
        "winner": result.judge_verdict.winner,
        "plaintiff_win_rate": result.judge_verdict.plaintiff_win_rate,
        "defendant_win_rate": result.judge_verdict.defendant_win_rate,
        "key_points": result.judge_verdict.key_points,
        "reasoning": result.judge_verdict.reasoning,
        "action_suggestions": result.judge_verdict.action_suggestions,
    }

    return MultiAgentDebateResponse(
        case=result.case,
        research_summary=result.research_summary,
        opinions=[
            {
                "role": opinion.role,
                "viewpoint": opinion.viewpoint,
                "content": opinion.content,
            }
            for opinion in result.opinions
        ],
        debate_rounds=debate_rounds,
        judge_verdict=judge_verdict,
        judge_summary=result.judge_summary,
        steps=result.steps,
    )


@router.post("/document/parse", response_model=DocumentParseResponse)
async def document_parse(
    file: UploadFile = File(...),
) -> DocumentParseResponse:
    """
    上传并解析单个文档，提取纯文本内容。

    支持格式：Word(.docx)、PDF(.pdf)、纯文本(.txt/.md)、图片(.png/.jpg等)
    图片类型使用 GLM-OCR 视觉模型识别文字。
    """
    try:
        content = await file.read()
        text = await document_parser.parse_bytes_async(content, file.filename)

        return DocumentParseResponse(
            filename=file.filename,
            text=text,
            char_count=len(text),
        )

    except DocumentParseError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"解析失败：{exc}") from exc


@router.post("/document/parse-batch")
async def document_parse_batch(
    files: list[UploadFile] = File(...),
):
    """
    批量上传并解析多个文档，提取纯文本内容。

    支持格式：Word(.docx)、PDF(.pdf)、纯文本(.txt/.md)
    图片类型使用 GLM-OCR 视觉模型识别文字。
    返回每个文件的解析结果，成功和失败分开统计。
    """
    results = []
    success_count = 0
    fail_count = 0

    for file in files:
        try:
            content = await file.read()
            text = await document_parser.parse_bytes_async(content, file.filename)
            results.append({
                "filename": file.filename,
                "success": True,
                "text": text,
                "char_count": len(text),
                "error": None,
            })
            success_count += 1
        except DocumentParseError as exc:
            results.append({
                "filename": file.filename,
                "success": False,
                "text": "",
                "char_count": 0,
                "error": str(exc),
            })
            fail_count += 1
        except Exception as exc:
            results.append({
                "filename": file.filename,
                "success": False,
                "text": "",
                "char_count": 0,
                "error": f"解析失败：{exc}",
            })
            fail_count += 1

    return {
        "ok": True,
        "total": len(files),
        "success_count": success_count,
        "fail_count": fail_count,
        "results": results,
    }


@router.post("/chat/stream")
async def chat_stream(request: ChatRequest):
    """
    流式聊天接口，返回 SSE 格式的流式响应。

    每个事件格式：data: {"text": "片段内容"}\n\n
    结束事件：data: [DONE]\n\n
    """
    async def generate():
        try:
            async for chunk in gateway.chat_text_stream(
                user_message=request.message,
                provider=request.provider,
            ):
                yield f"data: {json.dumps({'text': chunk}, ensure_ascii=False)}\n\n"

            yield "data: [DONE]\n\n"

        except LLMGatewayError as exc:
            yield f"data: {json.dumps({'error': str(exc)}, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/chat/multi-turn")
async def chat_multi_turn(request: MultiTurnChatRequest):
    """
    多轮对话流式接口，返回 SSE 格式。

    请求体接受完整的对话历史 messages，后端直接透传给 LLM，
    支持真正的多轮上下文。

    事件格式：
        data: {"text": "片段"}\n\n
        data: {"done": true}\n\n   (结束)
        data: {"error": "..."}\n\n  (出错)
    """
    # 组装消息列表
    raw_messages = [{"role": m.role, "content": m.content} for m in request.messages]

    # 如果开启 RAG，用最后一条用户消息检索法律知识并注入系统提示
    if request.use_rag:
        last_user_msg = next(
            (m.content for m in reversed(request.messages) if m.role == "user"),
            "",
        )
        if last_user_msg:
            try:
                contexts = rag.search(last_user_msg, top_k=4)
                if contexts:
                    context_text = "\n\n---\n\n".join(
                        c.get("content", "")[:800] for c in contexts if c.get("content")
                    )
                    rag_system = (
                        "你是严谨、专业、友好的中文法律 AI 助手。"
                        "以下是与用户问题相关的法律知识片段，请在回答时参考：\n\n"
                        f"{context_text}\n\n"
                        "请基于以上知识和你的专业判断回答用户问题。"
                    )
                    # 如果首条不是 system，则插入；否则替换
                    if raw_messages and raw_messages[0]["role"] == "system":
                        raw_messages[0]["content"] = rag_system
                    else:
                        raw_messages.insert(0, {"role": "system", "content": rag_system})
            except Exception:
                # RAG 检索失败不阻断对话
                pass

    async def generate():
        try:
            async for chunk in gateway.chat_stream(
                messages=raw_messages,
                model=request.model,
                temperature=request.temperature,
                max_tokens=request.max_tokens,
            ):
                yield f"data: {json.dumps({'text': chunk}, ensure_ascii=False)}\n\n"

            yield f"data: {json.dumps({'done': True}, ensure_ascii=False)}\n\n"

        except LLMGatewayError as exc:
            yield f"data: {json.dumps({'error': str(exc)}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'done': True}, ensure_ascii=False)}\n\n"
        except Exception as exc:
            yield f"data: {json.dumps({'error': f'服务端错误: {exc}'}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'done': True}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ============================================================================
# 合同审查相关接口
# ============================================================================

@router.post("/contract/review", response_model=ContractReviewResponse)
async def contract_review(request: ContractReviewRequest) -> ContractReviewResponse:
    """
    审查合同，识别风险点。

    使用Skill系统进行合同风险审查。
    """
    try:
        # 使用合同审查Skill
        result = await skill_executor.execute(
            skill_name="contract-risk-review",
            input_text=request.contract_text,
            use_llm=request.use_llm,
        )

        # 解析风险点（简化版，实际应该从Skill输出中结构化提取）
        risk_points = _parse_risk_points(result.output_text)

        high_count = sum(1 for r in risk_points if r.risk_level == "high")
        medium_count = sum(1 for r in risk_points if r.risk_level == "medium")
        low_count = sum(1 for r in risk_points if r.risk_level == "low")

        summary = f"共发现 {len(risk_points)} 处风险点，其中高风险 {high_count} 处，中风险 {medium_count} 处，低风险 {low_count} 处。"

        return ContractReviewResponse(
            risk_points=risk_points,
            total_risks=len(risk_points),
            high_risk_count=high_count,
            medium_risk_count=medium_count,
            low_risk_count=low_count,
            summary=summary,
        )

    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"合同审查失败：{exc}") from exc


@router.post("/contract/generate-annotated", response_model=GenerateAnnotatedResponse)
async def contract_generate_annotated(
    request: GenerateAnnotatedRequest,
) -> GenerateAnnotatedResponse:
    """
    生成带标注的合同文件。

    这是一个需要用户确认的操作。
    """
    try:
        # 将风险点转换为contract_annotator需要的格式
        from backend.core.contract_annotator import RiskPoint

        risk_points = [
            RiskPoint(
                id=rp.id or f"risk-{idx}",
                clause_text=rp.clause_text,
                risk_level=rp.risk_level,
                risk_type=rp.risk_type,
                description=rp.description,
                suggestion=rp.suggestion,
            )
            for idx, rp in enumerate(request.risk_points, start=1)
        ]

        # 将 contract_text 转为 docx bytes，然后用 save_original 保存到 user_dir
        # 这样 annotate_contract 的安全检查（文件必须在 user_dir 下）才能通过
        import io
        from docx import Document as DocxDocument

        doc = DocxDocument()
        for line in request.contract_text.split("\n"):
            doc.add_paragraph(line)

        buffer = io.BytesIO()
        doc.save(buffer)
        docx_bytes = buffer.getvalue()

        # 用 save_original 保存到用户隔离目录（安全检查要求文件在 user_dir 下）
        original_path = contract_annotator.save_original(
            file_bytes=docx_bytes,
            original_filename=request.original_file_name or "contract_review.docx",
            user_id=request.user_id,
        )

        # 生成标注文件
        result = contract_annotator.annotate_contract(
            original_path=original_path,
            risk_points=risk_points,
            user_id=request.user_id,
        )

        if not result.success:
            raise HTTPException(status_code=500, detail=result.error_message)

        return GenerateAnnotatedResponse(
            annotated_filename=result.annotated_filename,
            annotated_file_path=result.annotated_path,
            risk_count=result.risk_count,
            high_risk_count=result.high_risk_count,
            medium_risk_count=result.medium_risk_count,
            low_risk_count=result.low_risk_count,
        )

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"生成标注文件失败：{exc}") from exc


@router.get("/contract/files", response_model=ListFilesResponse)
async def contract_list_files(user_id: str = "demo_user") -> ListFilesResponse:
    """
    列出用户的合同文件。
    """
    try:
        files = contract_annotator.list_user_files(user_id)

        file_infos = []
        for f in files:
            file_infos.append(
                FileInfoSchema(
                    filename=f.get("filename", ""),
                    file_path=f.get("file_path", ""),
                    file_size=f.get("file_size", 0),
                    created_at=f.get("created_at", ""),
                )
            )

        return ListFilesResponse(
            files=file_infos,
            total_count=len(file_infos),
        )

    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"获取文件列表失败：{exc}") from exc


@router.get("/contract/download")
async def contract_download(filename: str, user_id: str = "demo_user"):
    """
    下载合同文件。
    """
    try:
        file_path = contract_annotator.get_file_path(filename, user_id)
        if not file_path or not Path(file_path).exists():
            raise HTTPException(status_code=404, detail="文件不存在")

        return FileResponse(
            path=file_path,
            filename=filename,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"下载文件失败：{exc}") from exc


@router.post("/contract/cleanup", response_model=CommandResponse)
async def contract_cleanup(request: ConfirmCommandRequest) -> CommandResponse:
    """
    清理过期文件（需要用户确认）。
    """
    try:
        # 创建命令（需要确认）
        command = safe_command_executor.create_command(
            command_type=CommandType.CLEANUP_EXPIRED,
            params={},
            user_id=request.user_id,
            description="清理超过24小时的临时文件",
        )

        if request.confirm:
            command = safe_command_executor.confirm_command(
                command.command_id, request.user_id
            )

        return CommandResponse(
            command_id=command.command_id,
            status=command.status.value,
            result=command.result or {},
        )

    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"清理失败：{exc}") from exc


def _parse_risk_points(output_text: str) -> list[RiskPointSchema]:
    """
    从Skill输出中解析风险点。

    简化实现：基于关键词匹配。
    实际项目中应该让Skill输出结构化的风险点。
    """
    risk_points = []
    lines = output_text.split("\n")

    current_risk = None
    for idx, line in enumerate(lines, start=1):
        line = line.strip()

        # 检测风险点开头
        if line.startswith(("风险", "问题", "⚠️", "🔴", "🟡", "🟢")):
            if current_risk:
                risk_points.append(current_risk)

            risk_level = "medium"
            if "高风险" in line or "🔴" in line or "严重" in line:
                risk_level = "high"
            elif "低风险" in line or "🟢" in line or "轻微" in line:
                risk_level = "low"

            current_risk = RiskPointSchema(
                id=f"risk-{idx}",
                clause_text=line[:50],
                risk_type="未知",
                risk_level=risk_level,
                description=line,
                suggestion="",
            )
        elif current_risk and line:
            current_risk.description += "\n" + line

    if current_risk:
        risk_points.append(current_risk)

    # 如果没有解析到，创建一个默认的
    if not risk_points:
        risk_points.append(
            RiskPointSchema(
                id="risk-1",
                clause_text="合同整体",
                risk_type="general",
                risk_level="medium",
                description=output_text[:200],
                suggestion="建议仔细审查合同条款",
            )
        )

    return risk_points


# ============================================================================
# 图像RAG相关接口
# ============================================================================

@router.post("/image-rag/search", response_model=ImageSearchResponse)
async def image_rag_search(request: ImageSearchRequest) -> ImageSearchResponse:
    """
    图像RAG检索。

    支持文本搜图、图搜图、混合检索。
    """
    try:
        image_rag = _get_image_rag()

        if request.search_type == "text":
            results = image_rag.search_by_text(request.query, top_k=request.top_k)
        elif request.search_type == "image":
            # 图搜图需要上传图片，这里简化
            results = []
        else:
            results = image_rag.search_by_text(request.query, top_k=request.top_k)

        result_schemas = [
            ImageSearchResultSchema(
                image_id=r.image_id,
                image_path=r.image_path,
                description=r.description,
                similarity_score=r.similarity_score,
                visual_elements=r.visual_elements,
            )
            for r in results
        ]

        return ImageSearchResponse(
            query=request.query,
            results=result_schemas,
            total_count=len(result_schemas),
        )

    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"图像检索失败：{exc}") from exc


@router.post("/image-rag/analyze", response_model=ImageAnalyzeResponse)
async def image_rag_analyze(file: UploadFile = File(...)) -> ImageAnalyzeResponse:
    """
    分析合同图像，提取视觉元素。
    """
    try:
        image_rag = _get_image_rag()

        # 保存临时文件
        suffix = Path(file.filename).suffix
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            content = await file.read()
            tmp.write(content)
            tmp_path = tmp.name

        try:
            analysis = image_rag.analyze_contract_image(tmp_path)

            return ImageAnalyzeResponse(
                width=analysis.get("width", 0),
                height=analysis.get("height", 0),
                has_signature=analysis.get("has_signature", False),
                has_seal=analysis.get("has_seal", False),
                has_handwriting=analysis.get("has_handwriting", False),
                text_density=analysis.get("text_density", 0.0),
                layout_type=analysis.get("layout_type", "unknown"),
            )
        finally:
            # 清理临时文件
            Path(tmp_path).unlink(missing_ok=True)

    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"图像分析失败：{exc}") from exc


@router.post("/image-rag/index")
async def image_rag_index(file: UploadFile = File(...), description: str = ""):
    """
    索引图像到图像RAG。
    """
    try:
        image_rag = _get_image_rag()

        # 保存临时文件
        suffix = Path(file.filename).suffix
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            content = await file.read()
            tmp.write(content)
            tmp_path = tmp.name

        try:
            image_id = image_rag.index_image(
                tmp_path,
                description=description,
                analyze=True,
            )

            return {
                "ok": True,
                "image_id": image_id,
                "total_images": image_rag.count(),
            }
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"图像索引失败：{exc}") from exc


# ============================================================================
# Graph RAG相关接口
# ============================================================================

@router.post("/graph-rag/search", response_model=GraphRAGSearchResponse)
async def graph_rag_search(request: GraphRAGSearchRequest) -> GraphRAGSearchResponse:
    """
    Graph RAG检索。

    搜索相似案例、相关法律、法律关系等。
    """
    try:
        graph_rag = _get_graph_rag()

        result = await graph_rag.search(
            query=request.query,
            search_type=request.search_type,
            top_k=request.top_k,
        )

        node_schemas = [
            GraphNodeSchema(
                node_id=n.node_id,
                node_type=n.node_type,
                name=n.name,
                confidence=n.confidence,
                properties=n.properties,
            )
            for n in result.nodes
        ]

        relation_schemas = [
            GraphRelationSchema(
                relation_id=r.relation_id,
                relation_type=r.relation_type,
                source_id=r.source_id,
                target_id=r.target_id,
                confidence=r.confidence,
            )
            for r in result.relations
        ]

        return GraphRAGSearchResponse(
            query=request.query,
            nodes=node_schemas,
            relations=relation_schemas,
            summary=result.summary,
            confidence=result.confidence,
        )

    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"图谱检索失败：{exc}") from exc


@router.post("/graph-rag/ask", response_model=GraphRAGAnswerResponse)
async def graph_rag_ask(request: GraphRAGSearchRequest) -> GraphRAGAnswerResponse:
    """
    Graph RAG问答。

    基于知识图谱回答法律问题。
    """
    try:
        graph_rag = _get_graph_rag()

        result = await graph_rag.answer(
            query=request.query,
            top_k=request.top_k,
            use_llm_answer=True,
        )

        law_schemas = [
            GraphNodeSchema(
                node_id=n.node_id,
                node_type=n.node_type,
                name=n.name,
                confidence=n.confidence,
                properties=n.properties,
            )
            for n in result.related_laws
        ]

        case_schemas = [
            GraphNodeSchema(
                node_id=n.node_id,
                node_type=n.node_type,
                name=n.name,
                confidence=n.confidence,
                properties=n.properties,
            )
            for n in result.related_cases
        ]

        return GraphRAGAnswerResponse(
            query=result.query,
            answer=result.answer,
            related_laws=law_schemas,
            related_cases=case_schemas,
            confidence=result.search_result.confidence,
        )

    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"图谱问答失败：{exc}") from exc


@router.get("/graph-rag/stats", response_model=GraphStatsResponse)
async def graph_rag_stats() -> GraphStatsResponse:
    """
    获取知识图谱统计信息。
    """
    try:
        graph_rag = _get_graph_rag()
        stats = graph_rag.get_stats()

        return GraphStatsResponse(
            nodes=stats.get("nodes", 0),
            relations=stats.get("relations", 0),
            is_connected=stats.get("is_connected", False),
            use_memory_fallback=stats.get("use_memory_fallback", True),
        )

    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"获取图谱统计失败：{exc}") from exc


@router.post("/graph-rag/index")
async def graph_rag_index_text(text: str, source: str = "api", use_llm: bool = True):
    """
    索引文本到知识图谱。
    """
    try:
        graph_rag = _get_graph_rag()

        nodes, relations = graph_rag.index_text(
            text=text,
            source=source,
            use_llm=use_llm,
        )

        return {
            "ok": True,
            "nodes_indexed": nodes,
            "relations_indexed": relations,
        }

    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"图谱索引失败：{exc}") from exc


# ============================================================================
# 视觉模型（GLM-OCR）与图像生成（GLM-Image）相关接口
# ============================================================================

@router.get("/models", response_model=ModelsInfoResponse)
async def models_info() -> ModelsInfoResponse:
    """
    获取当前可用的所有模型信息。

    返回 4 个文本模型、1 个视觉模型、1 个图像生成模型。
    """
    return ModelsInfoResponse(
        text_models=gateway.available_providers(),
        vision_model=settings.zhipu_vision_model,
        image_model=settings.zhipu_image_model,
        default_model=settings.default_llm_model,
    )


@router.post("/vision/analyze", response_model=VisionAnalyzeResponse)
async def vision_analyze(request: VisionAnalyzeRequest) -> VisionAnalyzeResponse:
    """
    使用 GLM-OCR 视觉模型识别图片中的文字。

    接收 base64 编码的图片，返回识别到的文本。
    适用于合同扫描件、法律文书照片等场景。
    """
    try:
        import base64 as _b64

        image_bytes = _b64.b64decode(request.image_base64)
        text = await gateway.chat_with_vision(
            image=image_bytes,
            prompt=request.prompt,
        )

        return VisionAnalyzeResponse(
            model=settings.zhipu_vision_model,
            text=text,
            char_count=len(text),
        )

    except LLMGatewayError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"视觉识别失败：{exc}") from exc


@router.post("/vision/analyze-file", response_model=VisionAnalyzeResponse)
async def vision_analyze_file(
    file: UploadFile = File(...),
    prompt: str = "请识别并提取图片中的所有文字内容，保持原有格式。",
) -> VisionAnalyzeResponse:
    """
    上传图片文件，使用 GLM-OCR 视觉模型识别文字。

    支持 .png / .jpg / .jpeg / .bmp / .webp 格式。
    """
    try:
        content = await file.read()
        text = await gateway.chat_with_vision(
            image=content,
            prompt=prompt,
        )

        return VisionAnalyzeResponse(
            model=settings.zhipu_vision_model,
            text=text,
            char_count=len(text),
        )

    except LLMGatewayError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"视觉识别失败：{exc}") from exc


@router.post("/image/generate", response_model=ImageGenerateResponse)
async def image_generate(request: ImageGenerateRequest) -> ImageGenerateResponse:
    """
    使用 GLM-Image 模型生成图片。

    生成的图片会保存到用户隔离目录，返回本地文件路径列表。
    适用于文档批注配图、法律场景示意图等。
    """
    try:
        image_paths = await gateway.generate_image(
            prompt=request.prompt,
            size=request.size,
            n=request.n,
            user_id=request.user_id,
        )

        return ImageGenerateResponse(
            model=settings.zhipu_image_model,
            image_paths=image_paths,
            image_count=len(image_paths),
            prompt=request.prompt,
        )

    except LLMGatewayError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"图像生成失败：{exc}") from exc


@router.get("/image/download")
async def image_download(filename: str, user_id: str = "default"):
    """
    下载生成的图片文件。
    """
    try:
        import re

        safe_user_id = re.sub(r'[^a-zA-Z0-9_\-]', '_', user_id) or "anonymous"
        file_path = (
            settings.contract_output_path
            / safe_user_id
            / "generated_images"
            / filename
        )

        if not file_path.exists():
            raise HTTPException(status_code=404, detail="图片文件不存在")

        return FileResponse(
            path=str(file_path),
            filename=filename,
            media_type="image/png",
        )

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"下载图片失败：{exc}") from exc


@router.get("/llm/health")
async def llm_health_check(model: str | None = None):
    """
    LLM 网关健康检查。

    会真实调用指定模型（默认为默认模型），消耗少量 token。
    """
    try:
        result = await gateway.health_check(model=model)
        return {"ok": True, **result}
    except LLMGatewayError as exc:
        return {"ok": False, "error": str(exc)}
