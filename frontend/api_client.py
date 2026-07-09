from __future__ import annotations
from typing import Any, Optional

import requests


DEFAULT_API_BASE_URL = "http://127.0.0.1:8000"


def stream_text_generator(text: str, chunk_size: int = 3):
    """
    将完整文本转换为逐块输出的生成器，用于模拟流式输出效果。

    Args:
        text: 完整文本
        chunk_size: 每次输出的字符数

    Yields:
        文本片段
    """
    import time

    for i in range(0, len(text), chunk_size):
        yield text[i:i + chunk_size]
        time.sleep(0.01)  # 控制输出速度


class APIClientError(RuntimeError):
    """前端 API 客户端异常。"""


class LvsheAPIClient:
    """
    Streamlit 前端调用 FastAPI 后端的统一客户端。
    """

    def __init__(self, base_url: str = DEFAULT_API_BASE_URL, timeout: int = 300) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def health(self) -> dict[str, Any]:
        return self._get("/health")

    def status(self) -> dict[str, Any]:
        return self._get("/api/status")

    def chat(self, message: str, provider: Optional[str] = None) -> dict[str, Any]:
        return self._post(
            "/api/chat",
            {
                "message": message,
                "provider": provider,
                "use_llm": True,
            },
        )

    def rag_ask(
        self,
        question: str,
        top_k: int = 3,
        use_llm_query_transform: bool = True,
        use_llm_hyde: bool = True,
        use_llm_answer: bool = True,
    ) -> dict[str, Any]:
        return self._post(
            "/api/rag/ask",
            {
                "question": question,
                "top_k": top_k,
                "use_llm_query_transform": use_llm_query_transform,
                "use_llm_hyde": use_llm_hyde,
                "use_llm_answer": use_llm_answer,
            },
        )

    def agent_run(self, question: str, use_llm: bool = True) -> dict[str, Any]:
        return self._post(
            "/api/agent/run",
            {
                "question": question,
                "use_llm": use_llm,
            },
        )

    def skill_run(
        self,
        input_text: str,
        skill_name: Optional[str] = None,
        use_llm: bool = True,
    ) -> dict[str, Any]:
        return self._post(
            "/api/skills/run",
            {
                "input_text": input_text,
                "skill_name": skill_name,
                "use_llm": use_llm,
            },
        )

    def memory_chat(
        self,
        message: str,
        user_id: str = "default_user",
        use_llm: bool = True,
    ) -> dict[str, Any]:
        return self._post(
            "/api/memory/chat",
            {
                "message": message,
                "user_id": user_id,
                "use_llm": use_llm,
            },
        )

    def multi_agents_debate(
        self,
        case: str,
        use_llm: bool = True,
        max_rounds: int = 3,
    ) -> dict[str, Any]:
        return self._post(
            "/api/multi-agents/debate",
            {
                "case": case,
                "use_llm": use_llm,
                "max_rounds": max_rounds,
            },
        )

    def gui_browse(
        self,
        task: str,
        start_url: str,
        take_screenshot: bool = True,
        use_llm_summary: bool = True,
        use_browser: bool = True,
    ) -> dict[str, Any]:
        return self._post(
            "/api/gui/browse",
            {
                "task": task,
                "start_url": start_url,
                "take_screenshot": take_screenshot,
                "use_llm_summary": use_llm_summary,
                "use_browser": use_browser,
            },
        )

    def index_sample(self) -> dict[str, Any]:
        return self._post("/api/rag/index-sample", {})

    def document_parse(self, file_bytes: bytes, filename: str) -> dict[str, Any]:
        """
        上传并解析单个文档。
        """
        try:
            files = {"file": (filename, file_bytes)}
            response = requests.post(
                self.base_url + "/api/document/parse",
                files=files,
                timeout=self.timeout,
            )
            return self._handle_response(response)
        except requests.RequestException as exc:
            raise APIClientError(f"请求后端失败：{exc}") from exc

    def document_parse_batch(self, files_list: list[tuple[str, bytes]]) -> dict[str, Any]:
        """
        批量上传并解析多个文档。

        Args:
            files_list: [(filename, file_bytes), ...] 列表

        Returns:
            包含 success_count, fail_count, results 的字典
        """
        try:
            files = [("files", (filename, content)) for filename, content in files_list]
            response = requests.post(
                self.base_url + "/api/document/parse-batch",
                files=files,
                timeout=self.timeout,
            )
            return self._handle_response(response)
        except requests.RequestException as exc:
            raise APIClientError(f"请求后端失败：{exc}") from exc

    def chat_stream(self, message: str, provider: Optional[str] = None):
        """
        流式聊天，返回一个生成器，逐块 yield 文本。

        用法：
            for chunk in client.chat_stream("你好"):
                print(chunk, end="")
        """
        import json

        try:
            response = requests.post(
                self.base_url + "/api/chat/stream",
                json={
                    "message": message,
                    "provider": provider,
                    "use_llm": True,
                },
                stream=True,
                timeout=self.timeout,
            )

            if response.status_code >= 400:
                try:
                    detail = response.json()
                except Exception:
                    detail = response.text
                raise APIClientError(f"后端返回错误 {response.status_code}：{detail}")

            for line in response.iter_lines(decode_unicode=True):
                if not line:
                    continue

                if line.startswith("data: "):
                    data = line[6:]  # 去掉 "data: " 前缀

                    if data == "[DONE]":
                        break

                    try:
                        parsed = json.loads(data)
                        if "text" in parsed:
                            yield parsed["text"]
                        elif "error" in parsed:
                            raise APIClientError(parsed["error"])
                    except json.JSONDecodeError:
                        continue

        except requests.RequestException as exc:
            raise APIClientError(f"请求后端失败：{exc}") from exc

    def _get(self, path: str) -> dict[str, Any]:
        try:
            response = requests.get(
                self.base_url + path,
                timeout=self.timeout,
            )
            return self._handle_response(response)
        except requests.RequestException as exc:
            raise APIClientError(f"请求后端失败：{exc}") from exc

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            response = requests.post(
                self.base_url + path,
                json=payload,
                timeout=self.timeout,
            )
            return self._handle_response(response)
        except requests.RequestException as exc:
            raise APIClientError(f"请求后端失败：{exc}") from exc

    # ========== 合同审查相关 ==========

    def contract_review(
        self,
        contract_text: str,
        user_id: str = "demo_user",
        use_llm: bool = True,
    ) -> dict[str, Any]:
        """审查合同，识别风险点。"""
        return self._post(
            "/api/contract/review",
            {
                "contract_text": contract_text,
                "user_id": user_id,
                "use_llm": use_llm,
            },
        )

    def contract_generate_annotated(
        self,
        original_file_name: str,
        contract_text: str,
        risk_points: list[dict[str, Any]],
        user_id: str = "demo_user",
    ) -> dict[str, Any]:
        """生成带标注的合同文件。"""
        return self._post(
            "/api/contract/generate-annotated",
            {
                "original_file_name": original_file_name,
                "contract_text": contract_text,
                "risk_points": risk_points,
                "user_id": user_id,
            },
        )

    def contract_list_files(self, user_id: str = "demo_user") -> dict[str, Any]:
        """列出用户的合同文件。"""
        return self._get(f"/api/contract/files?user_id={user_id}")

    def contract_download_url(self, filename: str, user_id: str = "demo_user") -> str:
        """获取合同文件下载URL。"""
        return f"{self.base_url}/api/contract/download?filename={filename}&user_id={user_id}"

    # ========== 图像RAG相关 ==========

    def image_rag_search(
        self,
        query: str,
        top_k: int = 5,
        search_type: str = "text",
    ) -> dict[str, Any]:
        """图像RAG检索。"""
        return self._post(
            "/api/image-rag/search",
            {
                "query": query,
                "top_k": top_k,
                "search_type": search_type,
            },
        )

    def image_rag_analyze(self, file_bytes: bytes, filename: str) -> dict[str, Any]:
        """分析合同图像。"""
        try:
            files = {"file": (filename, file_bytes)}
            response = requests.post(
                self.base_url + "/api/image-rag/analyze",
                files=files,
                timeout=self.timeout,
            )
            return self._handle_response(response)
        except requests.RequestException as exc:
            raise APIClientError(f"请求后端失败：{exc}") from exc

    # ========== Graph RAG相关 ==========

    def graph_rag_search(
        self,
        query: str,
        top_k: int = 5,
        search_type: str = "auto",
    ) -> dict[str, Any]:
        """Graph RAG检索。"""
        return self._post(
            "/api/graph-rag/search",
            {
                "query": query,
                "top_k": top_k,
                "search_type": search_type,
            },
        )

    def graph_rag_ask(
        self,
        query: str,
        top_k: int = 5,
    ) -> dict[str, Any]:
        """Graph RAG问答。"""
        return self._post(
            "/api/graph-rag/ask",
            {
                "query": query,
                "top_k": top_k,
            },
        )

    def graph_rag_stats(self) -> dict[str, Any]:
        """获取知识图谱统计。"""
        return self._get("/api/graph-rag/stats")

    # ========== 视觉模型（GLM-OCR）与图像生成（GLM-Image）相关 ==========

    def models_info(self) -> dict[str, Any]:
        """获取所有可用模型信息。"""
        return self._get("/api/models")

    def vision_analyze(self, image_base64: str, prompt: str = "请识别并提取图片中的所有文字内容。") -> dict[str, Any]:
        """使用 GLM-OCR 视觉模型识别图片文字（base64 方式）。"""
        return self._post(
            "/api/vision/analyze",
            {
                "image_base64": image_base64,
                "prompt": prompt,
            },
        )

    def vision_analyze_file(self, file_bytes: bytes, filename: str, prompt: str = "请识别并提取图片中的所有文字内容。") -> dict[str, Any]:
        """上传图片文件，使用 GLM-OCR 视觉模型识别文字。"""
        try:
            files = {"file": (filename, file_bytes)}
            response = requests.post(
                self.base_url + "/api/vision/analyze-file",
                files=files,
                data={"prompt": prompt},
                timeout=self.timeout,
            )
            return self._handle_response(response)
        except requests.RequestException as exc:
            raise APIClientError(f"请求后端失败：{exc}") from exc

    def image_generate(
        self,
        prompt: str,
        size: str = "1024x1024",
        n: int = 1,
        user_id: str = "default",
    ) -> dict[str, Any]:
        """使用 GLM-Image 模型生成图片。"""
        return self._post(
            "/api/image/generate",
            {
                "prompt": prompt,
                "size": size,
                "n": n,
                "user_id": user_id,
            },
        )

    def image_download_url(self, filename: str, user_id: str = "default") -> str:
        """获取生成图片的下载URL。"""
        return f"{self.base_url}/api/image/download?filename={filename}&user_id={user_id}"

    def llm_health_check(self, model: str | None = None) -> dict[str, Any]:
        """LLM 网关健康检查。"""
        params = f"?model={model}" if model else ""
        return self._get(f"/api/llm/health{params}")

    def _handle_response(self, response: requests.Response) -> dict[str, Any]:
        if response.status_code >= 400:
            try:
                detail = response.json()
            except Exception:
                detail = response.text
            raise APIClientError(f"后端返回错误 {response.status_code}：{detail}")

        return response.json()
