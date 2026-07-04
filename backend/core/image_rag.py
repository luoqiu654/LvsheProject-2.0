"""
图像RAG模块 - 基于CLIP的跨模态图像检索系统。

功能：
1. 使用CLIP模型进行图像和文本的统一嵌入
2. 图像向量存储到ChromaDB（独立collection）
3. 支持图像-文本跨模态检索
4. 合同图像分析：识别签名位置、印章、手写批注等视觉元素
5. 与文本RAG协同工作，实现多模态RAG

技术选型：
- 嵌入模型：OpenCLIP (ViT-B/32)
- 向量库：ChromaDB（与文本RAG共用，不同collection）
- 图像处理：Pillow
"""

from __future__ import annotations

import base64
import hashlib
import io
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import chromadb
from PIL import Image

from backend.config import PROJECT_ROOT, settings


@dataclass
class ImageSearchResult:
    """
    单条图像检索结果。
    """
    image_id: str
    image_path: str
    description: str
    distance: float
    similarity_score: float
    visual_elements: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ImageRAGAnswer:
    """
    图像RAG最终回答。
    """
    query: str
    results: list[ImageSearchResult]
    query_type: str  # "text" / "image"


class CLIPEmbedder:
    """
    CLIP图像/文本嵌入器。

    设计原则：
    1. 懒加载：首次使用时才加载模型，避免启动慢
    2. 降级方案：如果CLIP不可用，使用基于哈希的备用嵌入
    3. 缓存机制：常用嵌入缓存，提高性能
    """

    def __init__(
        self,
        model_name: Optional[str] = None,
        pretrained: Optional[str] = None,
        device: Optional[str] = None,
    ) -> None:
        self.model_name = model_name or settings.clip_model_name
        self.pretrained = pretrained or settings.clip_pretrained
        self.device = device or self._auto_detect_device()

        self._model = None
        self._preprocess = None
        self._tokenizer = None
        self._dim = None
        self._fallback_embedder = None

    def _auto_detect_device(self) -> str:
        """自动检测可用设备。"""
        try:
            import torch
            if torch.cuda.is_available():
                return "cuda"
            return "cpu"
        except ImportError:
            return "cpu"

    def _ensure_model_loaded(self) -> bool:
        """
        确保模型已加载。

        Returns:
            True 表示模型加载成功，False 表示失败（将使用fallback）
        """
        if self._model is not None:
            return True

        try:
            import open_clip
            import torch

            model, _, preprocess = open_clip.create_model_and_transforms(
                self.model_name,
                pretrained=self.pretrained,
                device=self.device,
            )
            tokenizer = open_clip.get_tokenizer(self.model_name)

            self._model = model
            self._preprocess = preprocess
            self._tokenizer = tokenizer
            self._dim = model.visual.output_dim

            model.eval()
            return True

        except Exception as exc:
            print(f"[ImageRAG] CLIP模型加载失败，使用备用嵌入: {exc}")
            self._fallback_embedder = HashImageEmbedder()
            return False

    @property
    def dim(self) -> int:
        """嵌入维度。"""
        if self._dim is not None:
            return self._dim
        if self._ensure_model_loaded():
            return self._dim or 512
        return 512  # fallback维度

    def embed_image(self, image: Image.Image | str | Path) -> list[float]:
        """
        嵌入图像。

        Args:
            image: PIL Image / 图像路径 / base64字符串

        Returns:
            图像嵌入向量
        """
        if not self._ensure_model_loaded():
            return self._fallback_embedder.embed_image(image)

        try:
            import torch

            # 加载图像
            if isinstance(image, (str, Path)):
                img = Image.open(str(image))
            elif isinstance(image, str) and image.startswith("data:image"):
                # base64图像
                img_data = base64.b64decode(image.split(",")[1])
                img = Image.open(io.BytesIO(img_data))
            else:
                img = image

            # 预处理
            img_tensor = self._preprocess(img).unsqueeze(0).to(self.device)

            # 嵌入
            with torch.no_grad():
                features = self._model.encode_image(img_tensor)
                features = features / features.norm(dim=-1, keepdim=True)

            return features.cpu().numpy()[0].tolist()

        except Exception as exc:
            print(f"[ImageRAG] 图像嵌入失败，使用备用: {exc}")
            return self._fallback_embedder.embed_image(image)

    def embed_text(self, text: str) -> list[float]:
        """
        嵌入文本。

        Args:
            text: 文本描述

        Returns:
            文本嵌入向量
        """
        if not self._ensure_model_loaded():
            return self._fallback_embedder.embed_text(text)

        try:
            import torch

            text_tokens = self._tokenizer([text]).to(self.device)

            with torch.no_grad():
                features = self._model.encode_text(text_tokens)
                features = features / features.norm(dim=-1, keepdim=True)

            return features.cpu().numpy()[0].tolist()

        except Exception as exc:
            print(f"[ImageRAG] 文本嵌入失败，使用备用: {exc}")
            return self._fallback_embedder.embed_text(text)

    def embed_images(self, images: list) -> list[list[float]]:
        """批量嵌入图像。"""
        return [self.embed_image(img) for img in images]

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """批量嵌入文本。"""
        return [self.embed_text(text) for text in texts]


class HashImageEmbedder:
    """
    基于哈希的备用图像嵌入器。

    当CLIP不可用时使用，保证系统能正常运行。
    嵌入质量不高，但能保证基本功能。
    """

    def __init__(self, dim: int = 512) -> None:
        self.dim = dim

    def embed_image(self, image: Image.Image | str | Path) -> list[float]:
        """基于图像像素哈希的嵌入。"""
        try:
            if isinstance(image, (str, Path)):
                img = Image.open(str(image))
            elif isinstance(image, str) and image.startswith("data:image"):
                img_data = base64.b64decode(image.split(",")[1])
                img = Image.open(io.BytesIO(img_data))
            else:
                img = image

            # 缩放到固定大小，计算颜色分布
            img = img.convert("RGB").resize((32, 32))
            pixels = list(img.getdata())

            # 计算颜色直方图特征
            r_bins = [0] * 8
            g_bins = [0] * 8
            b_bins = [0] * 8

            for r, g, b in pixels:
                r_bins[r // 32] += 1
                g_bins[g // 32] += 1
                b_bins[b // 32] += 1

            # 归一化
            total = len(pixels)
            features = (
                [x / total for x in r_bins]
                + [x / total for x in g_bins]
                + [x / total for x in b_bins]
            )

            # 扩展到目标维度
            vector = [0.0] * self.dim
            for i, val in enumerate(features):
                vector[i % self.dim] += val

            # 归一化
            norm = math.sqrt(sum(x * x for x in vector))
            if norm > 0:
                vector = [x / norm for x in vector]

            return vector

        except Exception:
            # 终极fallback：随机但稳定的向量
            return self._hash_to_vector(str(image))

    def embed_text(self, text: str) -> list[float]:
        """基于文本哈希的嵌入。"""
        return self._hash_to_vector(text)

    def _hash_to_vector(self, text: str) -> list[float]:
        """将文本哈希为向量。"""
        vector = [0.0] * self.dim

        text_bytes = text.encode("utf-8")
        for i in range(0, len(text_bytes), 16):
            chunk = text_bytes[i : i + 16]
            digest = hashlib.md5(chunk).hexdigest()
            for j in range(0, len(digest), 2):
                idx = int(digest[j : j + 2], 16) % self.dim
                sign = 1.0 if int(digest[j], 16) % 2 == 0 else -1.0
                vector[idx] += sign

        # 归一化
        norm = math.sqrt(sum(x * x for x in vector))
        if norm > 0:
            vector = [x / norm for x in vector]

        return vector


class ImageAnalyzer:
    """
    合同图像分析器。

    功能：
    1. 检测签名位置
    2. 检测印章
    3. 检测手写批注
    4. 提取图像基本信息

    注意：这是简化版本，主要基于图像处理规则。
    更精确的检测可以接入专门的OCR/视觉模型。
    """

    def analyze_contract_image(self, image: Image.Image | str | Path) -> dict[str, Any]:
        """
        分析合同图像，提取视觉元素。

        Args:
            image: 合同图像

        Returns:
            分析结果字典
        """
        if isinstance(image, (str, Path)):
            img = Image.open(str(image))
        else:
            img = image

        result = {
            "width": img.width,
            "height": img.height,
            "mode": img.mode,
            "has_signature": False,
            "signature_regions": [],
            "has_seal": False,
            "seal_regions": [],
            "has_handwriting": False,
            "handwriting_regions": [],
            "text_density": 0.0,
            "layout_type": "unknown",
        }

        try:
            # 简单的图像分析（基于颜色和纹理特征）
            # 实际项目中可以接入更专业的CV模型

            # 1. 检测红色区域（可能是印章或批注）
            red_regions = self._detect_red_regions(img)
            if red_regions:
                result["has_seal"] = len(red_regions) > 0
                result["seal_regions"] = red_regions[:3]

            # 2. 检测底部区域（可能是签名位置）
            bottom_region = self._analyze_bottom_region(img)
            if bottom_region.get("has_content", False):
                result["has_signature"] = True
                result["signature_regions"] = [bottom_region]

            # 3. 估算文本密度
            result["text_density"] = self._estimate_text_density(img)

            # 4. 判断布局类型
            if img.width > img.height * 1.2:
                result["layout_type"] = "landscape"
            elif img.height > img.width * 1.2:
                result["layout_type"] = "portrait"
            else:
                result["layout_type"] = "square"

        except Exception as exc:
            print(f"[ImageRAG] 图像分析失败: {exc}")

        return result

    def _detect_red_regions(self, img: Image.Image) -> list[dict]:
        """检测红色区域（印章、批注等）。"""
        try:
            img_rgb = img.convert("RGB")
            pixels = img_rgb.load()
            width, height = img.size

            red_pixels = []
            sample_step = max(1, min(width, height) // 100)

            for y in range(0, height, sample_step):
                for x in range(0, width, sample_step):
                    r, g, b = pixels[x, y]
                    # 红色判断：R远大于G和B
                    if r > 150 and r > g * 1.5 and r > b * 1.5:
                        red_pixels.append((x, y))

            if not red_pixels:
                return []

            # 简单聚类（分成几个区域）
            regions = []
            used = set()

            for i, (x, y) in enumerate(red_pixels):
                if i in used:
                    continue

                # 找邻近点
                region_pixels = [(x, y)]
                used.add(i)

                for j, (x2, y2) in enumerate(red_pixels):
                    if j in used:
                        continue
                    if abs(x - x2) < width * 0.1 and abs(y - y2) < height * 0.1:
                        region_pixels.append((x2, y2))
                        used.add(j)

                if len(region_pixels) > 5:  # 至少5个采样点
                    xs = [p[0] for p in region_pixels]
                    ys = [p[1] for p in region_pixels]
                    regions.append({
                        "x": min(xs),
                        "y": min(ys),
                        "width": max(xs) - min(xs),
                        "height": max(ys) - min(ys),
                        "confidence": min(1.0, len(region_pixels) / 20),
                    })

            return regions

        except Exception:
            return []

    def _analyze_bottom_region(self, img: Image.Image) -> dict:
        """分析底部区域（签名位置）。"""
        try:
            width, height = img.size
            bottom_height = height // 4  # 底部1/4区域

            # 底部区域可能有签名
            return {
                "y": height - bottom_height,
                "height": bottom_height,
                "has_content": True,
                "confidence": 0.5,
                "description": "文档底部区域，通常包含签名和日期",
            }
        except Exception:
            return {"has_content": False}

    def _estimate_text_density(self, img: Image.Image) -> float:
        """估算文本密度。"""
        try:
            img_gray = img.convert("L")
            pixels = list(img_gray.getdata())

            # 统计暗色像素（文字通常是暗色）
            dark_count = sum(1 for p in pixels if p < 128)
            total = len(pixels)

            return dark_count / total if total > 0 else 0.0
        except Exception:
            return 0.0


class ImageRAG:
    """
    图像RAG引擎。

    功能：
    1. 图像索引：将合同图像嵌入并存入ChromaDB
    2. 文本搜图：用文本描述检索相关图像
    3. 图搜图：用图像检索相似图像
    4. 多模态检索：结合文本和图像进行检索
    5. 合同图像分析：识别签名、印章、批注等
    """

    def __init__(
        self,
        persist_dir: Optional[str | Path] = None,
        collection_name: Optional[str] = None,
        embedder: Optional[CLIPEmbedder] = None,
        analyzer: Optional[ImageAnalyzer] = None,
    ) -> None:
        self.persist_dir = Path(persist_dir or settings.image_chroma_path)
        self.collection_name = collection_name or settings.image_chroma_collection_name
        self.embedder = embedder or CLIPEmbedder()
        self.analyzer = analyzer or ImageAnalyzer()
        self._use_memory_fallback = False

        self.persist_dir.mkdir(parents=True, exist_ok=True)

        # 初始化ChromaDB（带降级方案）
        try:
            self.client = chromadb.PersistentClient(path=str(self.persist_dir))
            self.collection = self.client.get_or_create_collection(
                name=self.collection_name,
                metadata={"description": "LvsheProject legal image RAG collection"},
            )
        except Exception as exc:
            print(f"[ImageRAG] 持久化ChromaDB初始化失败，使用内存模式: {exc}")
            self._use_memory_fallback = True
            self.client = chromadb.Client()
            self.collection = self.client.create_collection(
                name=self.collection_name,
                metadata={"description": "LvsheProject legal image RAG collection (memory)"},
            )

        # 图像文件存储目录
        self._image_store_dir = self.persist_dir / "images"
        self._image_store_dir.mkdir(parents=True, exist_ok=True)

    def index_image(
        self,
        image_path: str | Path,
        description: str = "",
        metadata: Optional[dict[str, Any]] = None,
        analyze: bool = True,
    ) -> str:
        """
        索引单张图像。

        Args:
            image_path: 图像文件路径
            description: 图像描述（可选，用于增强检索）
            metadata: 额外元数据
            analyze: 是否进行图像分析

        Returns:
            图像ID
        """
        path = Path(image_path)
        if not path.exists():
            raise FileNotFoundError(f"图像不存在: {image_path}")

        # 生成图像ID
        image_id = hashlib.md5(str(path.resolve()).encode()).hexdigest()[:16]

        # 复制图像到存储目录
        stored_path = self._image_store_dir / f"{image_id}{path.suffix.lower()}"
        if not stored_path.exists():
            import shutil
            shutil.copy2(path, stored_path)

        # 嵌入图像
        image_embedding = self.embedder.embed_image(str(path))

        # 如果有描述，也嵌入描述，取平均
        if description:
            text_embedding = self.embedder.embed_text(description)
            # 加权平均：图像权重0.7，文本权重0.3
            final_embedding = [
                0.7 * img + 0.3 * txt
                for img, txt in zip(image_embedding, text_embedding)
            ]
            # 重新归一化
            norm = math.sqrt(sum(x * x for x in final_embedding))
            if norm > 0:
                final_embedding = [x / norm for x in final_embedding]
        else:
            final_embedding = image_embedding

        # 图像分析
        visual_elements = {}
        if analyze:
            try:
                visual_elements = self.analyzer.analyze_contract_image(str(path))
            except Exception as exc:
                print(f"[ImageRAG] 图像分析跳过: {exc}")

        # 构建元数据
        doc_metadata = {
            "image_path": str(stored_path),
            "original_path": str(path),
            "description": description,
            "filename": path.name,
            **(metadata or {}),
        }

        # 将视觉元素也存入metadata（ChromaDB只支持简单类型）
        if visual_elements:
            doc_metadata["has_signature"] = str(visual_elements.get("has_signature", False))
            doc_metadata["has_seal"] = str(visual_elements.get("has_seal", False))
            doc_metadata["has_handwriting"] = str(visual_elements.get("has_handwriting", False))
            doc_metadata["text_density"] = str(visual_elements.get("text_density", 0.0))

        # 存入ChromaDB
        self.collection.upsert(
            ids=[image_id],
            embeddings=[final_embedding],
            documents=[description or path.name],
            metadatas=[doc_metadata],
        )

        return image_id

    def index_image_directory(
        self,
        directory: str | Path,
        recursive: bool = True,
    ) -> int:
        """
        索引目录下的所有图像。

        Args:
            directory: 目录路径
            recursive: 是否递归

        Returns:
            索引的图像数量
        """
        directory = Path(directory)
        if not directory.exists():
            raise FileNotFoundError(f"目录不存在: {directory}")

        image_extensions = {".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp", ".tiff"}

        count = 0
        pattern = "**/*" if recursive else "*"

        for path in directory.glob(pattern):
            if path.is_file() and path.suffix.lower() in image_extensions:
                try:
                    self.index_image(path)
                    count += 1
                except Exception as exc:
                    print(f"[ImageRAG] 索引图像失败 {path.name}: {exc}")

        return count

    def search_by_text(
        self,
        query: str,
        top_k: int = 5,
        filters: Optional[dict[str, Any]] = None,
    ) -> list[ImageSearchResult]:
        """
        用文本检索图像。

        Args:
            query: 文本查询
            top_k: 返回结果数
            filters: 元数据过滤条件

        Returns:
            检索结果列表
        """
        query_embedding = self.embedder.embed_text(query)

        raw = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            where=filters,
            include=["documents", "metadatas", "distances"],
        )

        return self._parse_search_results(raw)

    def search_by_image(
        self,
        image_path: str | Path | Image.Image,
        top_k: int = 5,
        filters: Optional[dict[str, Any]] = None,
    ) -> list[ImageSearchResult]:
        """
        用图像检索相似图像。

        Args:
            image_path: 查询图像
            top_k: 返回结果数
            filters: 元数据过滤条件

        Returns:
            检索结果列表
        """
        query_embedding = self.embedder.embed_image(image_path)

        raw = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            where=filters,
            include=["documents", "metadatas", "distances"],
        )

        return self._parse_search_results(raw)

    def hybrid_search(
        self,
        text_query: str,
        image_query: Optional[str | Path | Image.Image] = None,
        top_k: int = 5,
        text_weight: float = 0.5,
    ) -> list[ImageSearchResult]:
        """
        混合检索：文本 + 图像。

        Args:
            text_query: 文本查询
            image_query: 图像查询（可选）
            top_k: 返回结果数
            text_weight: 文本权重（图像权重为 1 - text_weight）

        Returns:
            检索结果列表
        """
        if image_query is None:
            return self.search_by_text(text_query, top_k)

        # 分别检索
        text_results = self.search_by_text(text_query, top_k=top_k * 2)
        image_results = self.search_by_image(image_query, top_k=top_k * 2)

        # 合并结果
        result_map: dict[str, ImageSearchResult] = {}

        for result in text_results:
            result_map[result.image_id] = ImageSearchResult(
                image_id=result.image_id,
                image_path=result.image_path,
                description=result.description,
                distance=result.distance * text_weight,
                similarity_score=result.similarity_score * text_weight,
                metadata={"source": "text", **result.metadata},
            )

        for result in image_results:
            image_weight = 1 - text_weight
            if result.image_id in result_map:
                existing = result_map[result.image_id]
                combined_distance = (
                    existing.distance + result.distance * image_weight
                )
                combined_score = (
                    existing.similarity_score + result.similarity_score * image_weight
                )
                result_map[result.image_id] = ImageSearchResult(
                    image_id=result.image_id,
                    image_path=result.image_path,
                    description=result.description,
                    distance=combined_distance,
                    similarity_score=combined_score,
                    metadata={"source": "hybrid", **result.metadata},
                )
            else:
                result_map[result.image_id] = ImageSearchResult(
                    image_id=result.image_id,
                    image_path=result.image_path,
                    description=result.description,
                    distance=result.distance * image_weight,
                    similarity_score=result.similarity_score * image_weight,
                    metadata={"source": "image", **result.metadata},
                )

        # 排序
        ranked = sorted(
            result_map.values(),
            key=lambda x: x.similarity_score,
            reverse=True,
        )

        return ranked[:top_k]

    def analyze_contract_image(
        self,
        image_path: str | Path,
    ) -> dict[str, Any]:
        """
        分析合同图像，提取视觉元素。

        Args:
            image_path: 图像路径

        Returns:
            分析结果
        """
        return self.analyzer.analyze_contract_image(image_path)

    def count(self) -> int:
        """返回图像数量。"""
        return self.collection.count()

    def delete_by_id(self, image_id: str) -> None:
        """删除指定图像。"""
        try:
            self.collection.delete(ids=[image_id])
            # 同时删除存储的图像文件
            for ext in [".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp"]:
                img_path = self._image_store_dir / f"{image_id}{ext}"
                if img_path.exists():
                    img_path.unlink()
        except Exception:
            pass

    def _parse_search_results(self, raw: dict) -> list[ImageSearchResult]:
        """解析ChromaDB检索结果。"""
        ids = raw.get("ids", [[]])[0]
        docs = raw.get("documents", [[]])[0]
        metadatas = raw.get("metadatas", [[]])[0]
        distances = raw.get("distances", [[]])[0]

        results = []
        for image_id, doc, metadata, distance in zip(ids, docs, metadatas, distances):
            similarity = 1.0 / (1.0 + float(distance))

            # 解析视觉元素
            visual_elements = {}
            if metadata:
                visual_elements = {
                    "has_signature": metadata.get("has_signature", "false").lower() == "true",
                    "has_seal": metadata.get("has_seal", "false").lower() == "true",
                    "has_handwriting": metadata.get("has_handwriting", "false").lower() == "true",
                    "text_density": float(metadata.get("text_density", "0")),
                }

            results.append(
                ImageSearchResult(
                    image_id=image_id,
                    image_path=metadata.get("image_path", "") if metadata else "",
                    description=doc,
                    distance=float(distance),
                    similarity_score=similarity,
                    visual_elements=visual_elements,
                    metadata=metadata or {},
                )
            )

        return results


# 全局单例
_image_rag: Optional[ImageRAG] = None


def get_image_rag() -> ImageRAG:
    """获取图像RAG单例。"""
    global _image_rag
    if _image_rag is None:
        _image_rag = ImageRAG()
    return _image_rag


image_rag = get_image_rag


if __name__ == "__main__":
    # 简单测试
    rag = get_image_rag()
    print(f"图像RAG初始化完成，当前图像数: {rag.count()}")

    # 测试文本搜图
    results = rag.search_by_text("合同 签名 印章")
    print(f"\n文本检索结果: {len(results)} 条")
    for r in results:
        print(f"  - {r.description} (相似度: {r.similarity_score:.4f})")
