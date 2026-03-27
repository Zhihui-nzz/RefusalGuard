"""
语义熵知识边界感知模块 v1.0
基于：Kuhn et al., "Semantic Uncertainty: Linguistic Invariances for Uncertainty
       Estimation in Natural Language Generation", Nature 2024 (cited 1271 times)

核心思想：
  - 对同一输入进行多次采样（temperature > 0），得到 N 个回答
  - 将语义相似的回答聚类（同义回答算同一类）
  - 计算语义熵 H = -Σ p(c) * log p(c)，c 为语义簇
  - 高语义熵 → 模型"不确定"→ 输入可能超出知识边界
  - 低语义熵 → 模型"确定" → 输入在知识边界内

在 RefusalGuard 中的应用：
  - 高语义熵的请求更可能是"知识边界外"的攻击或未知威胁
  - 将语义熵作为第四维信号输入决策引擎

注意：需要 llm_enabled=True 且 Ollama 已启动
"""
import math
from dataclasses import dataclass
from loguru import logger
from backend.config import settings


@dataclass
class SemanticEntropyResult:
    entropy:            float   # 语义熵值，越高越不确定
    is_uncertain:       bool    # 是否超出知识边界
    sample_count:       int     # 实际采样次数
    cluster_count:      int     # 语义簇数量
    uncertainty_score:  float   # 归一化不确定度 0~1


class SemanticEntropyDetector:
    """
    语义熵检测器
    通过多次采样 LLM 回答，计算语义熵来判断输入是否超出模型知识边界
    """

    # 语义熵阈值（超过此值认为"不确定"）
    ENTROPY_THRESHOLD = 1.5

    def __init__(self):
        if not settings.llm_enabled:
            logger.warning("语义熵检测需要 llm_enabled=True，当前已禁用")

    def compute(self, prompt: str) -> SemanticEntropyResult:
        """
        计算给定 prompt 的语义熵
        步骤：
          1. 多次采样 LLM 回答（temperature=0.8）
          2. 用嵌入模型计算回答间相似度
          3. 聚类（相似度 > 0.85 归为同一簇）
          4. 计算语义熵
        """
        if not settings.llm_enabled:
            return SemanticEntropyResult(
                entropy=0.0,
                is_uncertain=False,
                sample_count=0,
                cluster_count=0,
                uncertainty_score=0.0,
            )

        samples = self._sample_responses(prompt, n=settings.semantic_entropy_samples)
        if not samples:
            return SemanticEntropyResult(
                entropy=0.0,
                is_uncertain=False,
                sample_count=0,
                cluster_count=0,
                uncertainty_score=0.0,
            )

        clusters = self._cluster_by_semantics(samples)
        entropy   = self._calc_entropy(clusters, len(samples))

        # 归一化：最大熵为 log2(N)
        max_entropy = math.log2(max(len(samples), 2))
        uncertainty_score = min(1.0, entropy / max_entropy)

        return SemanticEntropyResult(
            entropy=round(entropy, 4),
            is_uncertain=entropy > self.ENTROPY_THRESHOLD,
            sample_count=len(samples),
            cluster_count=len(clusters),
            uncertainty_score=round(uncertainty_score, 4),
        )

    def _sample_responses(self, prompt: str, n: int) -> list[str]:
        """多次采样 LLM 回答"""
        try:
            from openai import OpenAI
            import httpx

            client = OpenAI(
                base_url=settings.llm_base_url,
                api_key=settings.llm_api_key,
                timeout=settings.llm_timeout_sec,
                http_client=httpx.Client(timeout=settings.llm_timeout_sec),
            )
            responses = []
            for _ in range(n):
                resp = client.chat.completions.create(
                    model=settings.llm_model,
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=100,
                    temperature=0.8,   # 高温度，增加多样性
                )
                responses.append(resp.choices[0].message.content.strip())
            return responses

        except Exception as e:
            logger.warning(f"语义熵采样失败: {e}")
            return []

    def _cluster_by_semantics(self, responses: list[str]) -> list[list[str]]:
        """
        基于嵌入相似度聚类
        相似度 > 0.85 的回答归为同一语义簇
        """
        if not responses:
            return []

        try:
            from sentence_transformers import SentenceTransformer
            import numpy as np

            model = SentenceTransformer(
                "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
            )
            embeddings = model.encode(responses)

            clusters: list[list[str]] = []
            assigned = [False] * len(responses)

            for i, resp in enumerate(responses):
                if assigned[i]:
                    continue
                cluster = [resp]
                assigned[i] = True
                for j in range(i + 1, len(responses)):
                    if assigned[j]:
                        continue
                    # 余弦相似度
                    sim = float(
                        np.dot(embeddings[i], embeddings[j])
                        / (np.linalg.norm(embeddings[i]) * np.linalg.norm(embeddings[j]) + 1e-8)
                    )
                    if sim > 0.85:
                        cluster.append(responses[j])
                        assigned[j] = True
                clusters.append(cluster)

            return clusters

        except Exception as e:
            logger.warning(f"语义聚类失败: {e}")
            # 降级：每个回答单独一簇
            return [[r] for r in responses]

    @staticmethod
    def _calc_entropy(clusters: list[list[str]], total: int) -> float:
        """
        计算语义熵
        H = -Σ p(c) * log2(p(c))
        p(c) = |cluster_c| / total
        """
        if total == 0 or not clusters:
            return 0.0
        entropy = 0.0
        for cluster in clusters:
            p = len(cluster) / total
            if p > 0:
                entropy -= p * math.log2(p)
        return entropy
