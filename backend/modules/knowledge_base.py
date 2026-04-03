# M3: 知识边界感知模块
import hashlib
import re
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Optional

from loguru import logger

from backend.config import settings

class _LRUCache:

    def __init__(self, maxsize: int = 500):
        self.maxsize = maxsize
        self._cache: OrderedDict = OrderedDict()

    def get(self, key: str):
        if key in self._cache:
            self._cache.move_to_end(key)
            return self._cache[key]
        return None

    def set(self, key: str, value):
        if key in self._cache:
            self._cache.move_to_end(key)
        else:
            if len(self._cache) >= self.maxsize:
                self._cache.popitem(last=False)
        self._cache[key] = value

_query_cache = _LRUCache(maxsize=500)

@dataclass
class KBResult:
    kb_confidence:    float        # 知识库匹配置信度（越高说明越像已知攻击）
    matched_entries:  list         # 匹配到的知识条目
    is_out_of_domain: bool         # 是否超出系统知识边界

    boundary_state:   str = "known"  # "known" | "fuzzy" | "unknown"
    calibration_variance: float = 0.0  # 置信度校准方差（越高说明边界越模糊）
    boundary_risk_bonus:  float = 0.0  # 知识边界模糊带来的额外风险加成

# ── 输入扰动策略（用于置信度校准）───────────────────────────────────────
def _generate_perturbations(text: str) -> list[str]:
    """
    生成轻微扰动版本的 Prompt，用于置信度校准。
    策略：句式改写（不改变语义），检测知识库匹配的稳定性。
    """
    perturbations = []

    # 扰动1：在句首加入无害前缀
    perturbations.append(f"请问：{text}")

    # 扰动2：替换常见代词
    p2 = re.sub(r"\b(you|your)\b", "the system", text, flags=re.I)
    if p2 != text:
        perturbations.append(p2)

    # 扰动3：去除标点符号
    p3 = re.sub(r"[，。！？,.!?]", " ", text).strip()
    if p3 != text:
        perturbations.append(p3)

    return perturbations[:2]  # 最多2个扰动，控制延迟

class KnowledgeBaseModule:

    # 知识边界阈值
    _KNOWN_THRESHOLD   = 0.45   # >= 此值：已知攻击模式
    _FUZZY_THRESHOLD   = 0.25   # >= 此值：边界模糊区
    # 低于 _FUZZY_THRESHOLD：超出知识边界（可能是新型攻击）

    # 置信度方差阈值：方差超过此值说明模型在该输入上不稳定
    _VARIANCE_THRESHOLD = 0.04

    def __init__(self):
        self._degraded = False
        # 懒导入 chromadb，避免未安装时导入失败
        try:
            import chromadb
            self.client = chromadb.PersistentClient(
                path="./backend/data/knowledge_base/chroma_db"
            )
            self.collection = self.client.get_collection("security_knowledge")
            logger.info("ChromaDB 知识库加载成功")
        except Exception as e:
            logger.warning(f"ChromaDB 加载失败，已降级为空知识库: {e}")
            self.client = None
            self.collection = None
            self._degraded = True

        # 懒导入 sentence_transformers
        try:
            from sentence_transformers import SentenceTransformer
            self.embedder = SentenceTransformer(
                settings.kb_embed_model,
                local_files_only=True,
            )
        except Exception as e:
            logger.warning(f"SentenceTransformer 加载失败，知识库嵌入功能将降级: {e}")
            self.embedder = None
            self._degraded = True

    def query(self, text: str, n_results: int = 3) -> KBResult:
        """
        查询知识库并进行置信度校准。
        """
        if self._degraded or self.collection is None:
            return KBResult(
                kb_confidence=0.3,
                matched_entries=[],
                is_out_of_domain=True,
                boundary_state="unknown",
                calibration_variance=0.0,
                boundary_risk_bonus=0.05,
            )

        # LRU 缓存
        cache_key = hashlib.md5(text.encode()).hexdigest()
        cached = _query_cache.get(cache_key)
        if cached is not None:
            return cached

        try:
            # 主查询
            main_confidence, matched = self._raw_query(text, n_results)

            # 置信度校准
            calibration_variance = 0.0
            if main_confidence > 0.1:  # 只对有一定匹配度的输入进行校准
                perturbations = _generate_perturbations(text)
                perturb_scores = []
                for p in perturbations:
                    score, _ = self._raw_query(p, n_results=1)
                    perturb_scores.append(score)

                if perturb_scores:
                    all_scores = [main_confidence] + perturb_scores
                    mean = sum(all_scores) / len(all_scores)
                    calibration_variance = sum(
                        (s - mean) ** 2 for s in all_scores
                    ) / len(all_scores)

            # 三态知识边界判断
            boundary_state, is_out_of_domain, boundary_risk_bonus = (
                self._classify_boundary(main_confidence, calibration_variance)
            )

            result = KBResult(
                kb_confidence=main_confidence,
                matched_entries=matched,
                is_out_of_domain=is_out_of_domain,
                boundary_state=boundary_state,
                calibration_variance=round(calibration_variance, 5),
                boundary_risk_bonus=boundary_risk_bonus,
            )
            _query_cache.set(cache_key, result)
            return result

        except Exception as e:
            logger.warning(f"知识库查询异常: {e}，返回默认值")
            return KBResult(
                kb_confidence=0.3,
                matched_entries=[],
                is_out_of_domain=True,
                boundary_state="unknown",
                calibration_variance=0.0,
                boundary_risk_bonus=0.05,
            )

    def _raw_query(
        self, text: str, n_results: int = 3
    ) -> tuple[float, list]:
        if self.embedder is None:
            return 0.3, []
        embedding = self.embedder.encode([text]).tolist()
        results = self.collection.query(
            query_embeddings=embedding,
            n_results=n_results,
            include=["documents", "metadatas", "distances"],
        )
        distances = results["distances"][0]
        # ChromaDB cosine distance: 0=完全相同, 2=完全不同 → 转换为相似度
        similarities = [max(0.0, 1.0 - d) for d in distances]
        kb_confidence = max(similarities) if similarities else 0.0

        matched = []
        for i, meta in enumerate(results["metadatas"][0]):
            matched.append({
                "source":     meta.get("source"),
                "id":         meta.get("id"),
                "title":      meta.get("title") or meta.get("name"),
                "similarity": round(similarities[i], 4),
            })
        return kb_confidence, matched

    def _classify_boundary(
        self, confidence: float, variance: float
    ) -> tuple[str, bool, float]:
        high_variance = variance > self._VARIANCE_THRESHOLD

        if confidence >= self._KNOWN_THRESHOLD and not high_variance:
            return "known", False, 0.0
        elif confidence >= self._FUZZY_THRESHOLD or high_variance:
            # 边界模糊：置信度中等，或方差大（扰动后结果不稳定）
            return "fuzzy", False, 0.08
        else:
            # 超出知识边界：低置信度 + 低方差（模型对此类输入完全陌生）
            return "unknown", True, 0.12
