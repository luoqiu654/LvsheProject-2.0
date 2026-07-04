from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"


class Settings(BaseSettings):
    """
    项目统一配置中心。

    原则：
    1. 所有密钥只从 .env 或环境变量读取
    2. 代码里不能硬编码 API Key
    3. 对外打印配置时不能泄露密钥
    """

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # App
    app_name: str = Field(default="LvsheProject", alias="APP_NAME")
    app_env: str = Field(default="dev", alias="APP_ENV")
    app_debug: bool = Field(default=True, alias="APP_DEBUG")

    # Backend
    backend_host: str = Field(default="127.0.0.1", alias="BACKEND_HOST")
    backend_port: int = Field(default=8000, alias="BACKEND_PORT")

    # LLM default
    default_llm_provider: str = Field(default="qwen", alias="DEFAULT_LLM_PROVIDER")
    default_llm_model: str = Field(default="qwen3.7-plus", alias="DEFAULT_LLM_MODEL")

    # Qwen
    qwen_api_key: Optional[SecretStr] = Field(default=None, alias="QWEN_API_KEY")
    qwen_base_url: Optional[str] = Field(default=None, alias="QWEN_BASE_URL")

    # Zhipu GLM
    zhipu_api_key: Optional[SecretStr] = Field(default=None, alias="ZHIPU_API_KEY")
    zhipu_base_url: str = Field(
        default="https://open.bigmodel.cn/api/paas/v4",
        alias="ZHIPU_BASE_URL",
    )

    # SiliconFlow
    siliconflow_api_key: Optional[SecretStr] = Field(
        default=None,
        alias="SILICONFLOW_API_KEY",
    )
    siliconflow_base_url: str = Field(
        default="https://api.siliconflow.cn/v1",
        alias="SILICONFLOW_BASE_URL",
    )

    # Doubao
    doubao_api_key: Optional[SecretStr] = Field(default=None, alias="DOUBAO_API_KEY")
    doubao_base_url: Optional[str] = Field(default=None, alias="DOUBAO_BASE_URL")

    # ChromaDB
    chroma_persist_dir: str = Field(default="data/vector_store", alias="CHROMA_PERSIST_DIR")
    chroma_collection_name: str = Field(
        default="lvshe_law_docs",
        alias="CHROMA_COLLECTION_NAME",
    )

    # Upload
    upload_dir: str = Field(default="data/uploads", alias="UPLOAD_DIR")

    # Memory
    memory_enabled: bool = Field(default=True, alias="MEMORY_ENABLED")
    memory_store_path: str = Field(default="data/memory", alias="MEMORY_STORE_PATH")

    # Browser
    browser_headless: bool = Field(default=True, alias="BROWSER_HEADLESS")

    # ===== 图像RAG配置 =====
    image_rag_enabled: bool = Field(default=True, alias="IMAGE_RAG_ENABLED")
    image_chroma_collection_name: str = Field(
        default="lvshe_law_images",
        alias="IMAGE_CHROMA_COLLECTION_NAME",
    )
    clip_model_name: str = Field(
        default="ViT-B-32",
        alias="CLIP_MODEL_NAME",
    )
    clip_pretrained: str = Field(
        default="laion2b_s34b_b79k",
        alias="CLIP_PRETRAINED",
    )

    # ===== Graph RAG (Neo4j) 配置 =====
    graph_rag_enabled: bool = Field(default=True, alias="GRAPH_RAG_ENABLED")
    neo4j_uri: str = Field(default="bolt://localhost:7687", alias="NEO4J_URI")
    neo4j_user: str = Field(default="neo4j", alias="NEO4J_USER")
    neo4j_password: Optional[SecretStr] = Field(default=None, alias="NEO4J_PASSWORD")
    neo4j_database: str = Field(default="lvshe_law", alias="NEO4J_DATABASE")

    # ===== MinIO 配置 =====
    minio_enabled: bool = Field(default=False, alias="MINIO_ENABLED")
    minio_endpoint: str = Field(default="localhost:9000", alias="MINIO_ENDPOINT")
    minio_access_key: Optional[str] = Field(default=None, alias="MINIO_ACCESS_KEY")
    minio_secret_key: Optional[SecretStr] = Field(default=None, alias="MINIO_SECRET_KEY")
    minio_bucket: str = Field(default="lvshe-documents", alias="MINIO_BUCKET")
    minio_secure: bool = Field(default=False, alias="MINIO_SECURE")

    # ===== Unstructured.io 配置 =====
    unstructured_enabled: bool = Field(default=True, alias="UNSTRUCTURED_ENABLED")
    unstructured_api_url: Optional[str] = Field(default=None, alias="UNSTRUCTURED_API_URL")
    unstructured_api_key: Optional[SecretStr] = Field(default=None, alias="UNSTRUCTURED_API_KEY")

    # ===== 合同审查输出 =====
    contract_output_dir: str = Field(
        default="output/contract_review",
        alias="CONTRACT_OUTPUT_DIR",
    )

    @property
    def chroma_path(self) -> Path:
        return PROJECT_ROOT / self.chroma_persist_dir

    @property
    def upload_path(self) -> Path:
        return PROJECT_ROOT / self.upload_dir

    @property
    def memory_path(self) -> Path:
        return PROJECT_ROOT / self.memory_store_path

    @property
    def contract_output_path(self) -> Path:
        return PROJECT_ROOT / self.contract_output_dir

    @property
    def image_chroma_path(self) -> Path:
        return PROJECT_ROOT / "data" / "image_vector_store"

    def safe_summary(self) -> dict:
        """
        返回不会泄露密钥的配置摘要。
        用于调试和测试。
        """
        return {
            "app_name": self.app_name,
            "app_env": self.app_env,
            "app_debug": self.app_debug,
            "backend": f"{self.backend_host}:{self.backend_port}",
            "default_llm_provider": self.default_llm_provider,
            "default_llm_model": self.default_llm_model,
            "has_qwen_api_key": self.qwen_api_key is not None and bool(self.qwen_api_key.get_secret_value()),
            "has_zhipu_api_key": self.zhipu_api_key is not None and bool(self.zhipu_api_key.get_secret_value()),
            "has_siliconflow_api_key": self.siliconflow_api_key is not None and bool(self.siliconflow_api_key.get_secret_value()),
            "has_doubao_api_key": self.doubao_api_key is not None and bool(self.doubao_api_key.get_secret_value()),
            "chroma_path": str(self.chroma_path),
            "upload_path": str(self.upload_path),
            "memory_path": str(self.memory_path),
            "browser_headless": self.browser_headless,
            # 新增模块
            "image_rag_enabled": self.image_rag_enabled,
            "image_chroma_collection": self.image_chroma_collection_name,
            "clip_model": self.clip_model_name,
            "graph_rag_enabled": self.graph_rag_enabled,
            "neo4j_uri": self.neo4j_uri,
            "has_neo4j_password": self.neo4j_password is not None and bool(self.neo4j_password.get_secret_value()),
            "minio_enabled": self.minio_enabled,
            "minio_endpoint": self.minio_endpoint,
            "unstructured_enabled": self.unstructured_enabled,
            "contract_output_dir": str(self.contract_output_path),
        }


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()


if __name__ == "__main__":
    from pprint import pprint

    pprint(settings.safe_summary())
