from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field, HttpUrl


class BaseAPIResponse(BaseModel):
    ok: bool = True
    message: str = "success"


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, description="用户消息")
    provider: Optional[str] = Field(default=None, description="LLM provider，例如 qwen / glm")
    use_llm: bool = Field(default=True)


class ChatResponse(BaseAPIResponse):
    answer: str


class RAGAskRequest(BaseModel):
    question: str = Field(..., min_length=1)
    top_k: int = Field(default=3, ge=1, le=10)
    use_llm_query_transform: bool = True
    use_llm_hyde: bool = True
    use_llm_answer: bool = True


class RAGAskResponse(BaseAPIResponse):
    question: str
    answer: str
    transformed_queries: list[str]
    hyde_answer: str
    contexts: list[dict[str, Any]]


class AgentRunRequest(BaseModel):
    question: str = Field(..., min_length=1)
    use_llm: bool = True


class AgentRunResponse(BaseAPIResponse):
    question: str
    final_answer: str
    tool_name: str
    tool_input: str
    tool_result: str
    steps: list[str]


class SkillRunRequest(BaseModel):
    input_text: str = Field(..., min_length=1)
    skill_name: Optional[str] = Field(default=None, description="不填则自动匹配")
    use_llm: bool = True


class SkillRunResponse(BaseAPIResponse):
    skill_name: str
    input_text: str
    output_text: str
    used_resources: list[str]


class MemoryChatRequest(BaseModel):
    message: str = Field(..., min_length=1)
    user_id: str = Field(default="default_user")
    use_llm: bool = True


class MemoryChatResponse(BaseAPIResponse):
    user_id: str
    message: str
    memory_context: str
    answer: str
    saved_memories: list[dict[str, Any]]


class GUIBrowseRequest(BaseModel):
    task: str = Field(default="打开网页并总结主要内容")
    start_url: HttpUrl
    take_screenshot: bool = True
    use_llm_summary: bool = True
    use_browser: bool = True


class GUIBrowseResponse(BaseAPIResponse):
    task: str
    start_url: str
    title: str
    url: str
    text_preview: str
    links: list[dict[str, str]]
    screenshot_path: Optional[str]
    summary: str
    steps: list[str]


class MultiAgentDebateRequest(BaseModel):
    case: str = Field(..., min_length=1)
    use_llm: bool = True
    max_rounds: int = Field(default=3, ge=1, le=5, description="辩论轮数，1-5轮")


class MultiAgentDebateResponse(BaseAPIResponse):
    case: str
    research_summary: str
    opinions: list[dict[str, str]]  # 兼容旧接口
    debate_rounds: list[dict[str, Any]]  # 多轮辩论记录
    judge_verdict: dict[str, Any]  # 法官明确判决
    judge_summary: str
    steps: list[str]


class StatusResponse(BaseAPIResponse):
    app_name: str
    available_llm_providers: list[str]
    modules: dict[str, bool]


class IndexSampleResponse(BaseAPIResponse):
    indexed_chunks: int
    total_chunks: int


class DocumentParseResponse(BaseAPIResponse):
    filename: str
    text: str
    char_count: int


# ========== 合同审查相关 ==========

class ContractReviewRequest(BaseModel):
    """合同审查请求。"""
    contract_text: str = Field(..., min_length=1, description="合同内容")
    user_id: str = Field(default="demo_user", description="用户ID")
    use_llm: bool = Field(default=True, description="是否使用LLM")


class RiskPointSchema(BaseModel):
    """风险点。"""
    clause: str = Field(..., description="问题条款")
    risk_type: str = Field(..., description="风险类型")
    severity: str = Field(..., description="严重程度：high/medium/low")
    description: str = Field(..., description="风险说明")
    suggestion: str = Field(default="", description="修改建议")


class ContractReviewResponse(BaseAPIResponse):
    """合同审查响应。"""
    risk_points: list[RiskPointSchema]
    total_risks: int
    high_risk_count: int
    medium_risk_count: int
    low_risk_count: int
    summary: str


class GenerateAnnotatedRequest(BaseModel):
    """生成带标注合同的请求。"""
    original_file_name: str = Field(..., description="原始文件名")
    contract_text: str = Field(..., description="合同内容")
    risk_points: list[RiskPointSchema]
    user_id: str = Field(default="demo_user", description="用户ID")


class GenerateAnnotatedResponse(BaseAPIResponse):
    """生成带标注合同的响应。"""
    annotated_filename: str
    annotated_file_path: str
    risk_count: int
    high_risk_count: int
    medium_risk_count: int
    low_risk_count: int


class ListFilesRequest(BaseModel):
    """列出用户文件请求。"""
    user_id: str = Field(default="demo_user", description="用户ID")


class FileInfoSchema(BaseModel):
    """文件信息。"""
    filename: str
    file_path: str
    file_size: int
    created_at: str


class ListFilesResponse(BaseAPIResponse):
    """列出用户文件响应。"""
    files: list[FileInfoSchema]
    total_count: int


class ConfirmCommandRequest(BaseModel):
    """确认命令请求。"""
    command_id: str = Field(..., description="命令ID")
    user_id: str = Field(default="demo_user", description="用户ID")
    confirm: bool = Field(default=True, description="是否确认")


class CommandResponse(BaseAPIResponse):
    """命令执行响应。"""
    command_id: str
    status: str
    result: dict[str, Any]


# ========== 图像RAG相关 ==========

class ImageSearchRequest(BaseModel):
    """图像检索请求。"""
    query: str = Field(..., min_length=1, description="查询文本")
    top_k: int = Field(default=5, ge=1, le=20)
    search_type: str = Field(default="text", description="检索类型：text/image/hybrid")


class ImageSearchResultSchema(BaseModel):
    """图像检索结果。"""
    image_id: str
    image_path: str
    description: str
    similarity_score: float
    visual_elements: dict[str, Any]


class ImageSearchResponse(BaseAPIResponse):
    """图像检索响应。"""
    query: str
    results: list[ImageSearchResultSchema]
    total_count: int


class ImageAnalyzeRequest(BaseModel):
    """图像分析请求。"""
    pass  # 通过文件上传


class ImageAnalyzeResponse(BaseAPIResponse):
    """图像分析响应。"""
    width: int
    height: int
    has_signature: bool
    has_seal: bool
    has_handwriting: bool
    text_density: float
    layout_type: str


# ========== Graph RAG相关 ==========

class GraphRAGSearchRequest(BaseModel):
    """Graph RAG检索请求。"""
    query: str = Field(..., min_length=1, description="查询文本")
    top_k: int = Field(default=5, ge=1, le=20)
    search_type: str = Field(default="auto", description="检索类型：auto/case/law/relation")


class GraphNodeSchema(BaseModel):
    """图谱节点。"""
    node_id: str
    node_type: str
    name: str
    confidence: float
    properties: dict[str, Any]


class GraphRelationSchema(BaseModel):
    """图谱关系。"""
    relation_id: str
    relation_type: str
    source_id: str
    target_id: str
    confidence: float


class GraphRAGSearchResponse(BaseAPIResponse):
    """Graph RAG检索响应。"""
    query: str
    nodes: list[GraphNodeSchema]
    relations: list[GraphRelationSchema]
    summary: str
    confidence: float


class GraphRAGAnswerResponse(BaseAPIResponse):
    """Graph RAG问答响应。"""
    query: str
    answer: str
    related_laws: list[GraphNodeSchema]
    related_cases: list[GraphNodeSchema]
    confidence: float


class GraphStatsResponse(BaseAPIResponse):
    """图谱统计响应。"""
    nodes: int
    relations: int
    is_connected: bool
    use_memory_fallback: bool
