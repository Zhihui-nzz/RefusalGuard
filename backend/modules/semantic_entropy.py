# 语义熵知识边界感知模块
import asyncio
import math
from dataclasses import dataclass, field
from typing import Optional

from loguru import logger

from backend.config import settings


@dataclass
class SemanticEntropyResult:
    entropy:              float   # 语义熵值，越高越不确定
    is_uncertain:         bool    # 是否超出知识边界
    sample_count:         int     # 实际采样次数
    cluster_count:        int     # 语义簇数量
    uncertainty_score:    float   # 归一化不确定度 0~1
    # v2.0 新增字段
    refusal_rate:         float = 0.0   # 采样中拒答比例（高拒答率=模型感知危险）
    high_refusal_signal:  bool  = False # 是否触发高拒答率信号
    entropy_risk_bonus:   float = 0.0   # 语义熵带来的额外风险加成


#  拒答检测关键词 
_REFUSAL_KEYWORDS = [
    "i cannot", "i can't", "i'm unable", "i am unable",
    "i won't", "i will not", "i refuse",
    "我无法", "我不能", "我不会", "我拒绝",
    "sorry, i", "对不起，我", "很抱歉",
    "as an ai", "作为一个ai", "作为ai",
    "that's not something i", "这不是我",
]


def _is_refusal(text: str) -> bool:
    """判断一个回答是否是拒答"""
    text_lower = text.lower()
    return any(kw in text_lower for kw in _REFUSAL_KEYWORDS)


class SemanticEntropyDetector:
    """
    语义熵检测器 v2.0
    通过多次异步采样 LLM 回答，计算语义熵来判断输入是否超出模型知识边界，
    并通过拒答率信号增强对危险请求的检测能力。
    """

    def __init__(self):
        if not settings.llm_enabled:
            logger.info("语义熵检测需要 llm_enabled=True，当前已禁用")

    def compute(self, prompt: str) -> SemanticEntropyResult:
        if not settings.llm_enabled or not settings.semantic_entropy_enabled:
            return SemanticEntropyResult(
                entropy=0.0,
                is_uncertain=False,
                sample_count=0,
                cluster_count=0,
                uncertainty_score=0.0,
            )

        try:
            # 在已有事件循环中运行异步采样
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    future = pool.submit(
                        asyncio.run, self._async_compute(prompt)
                    )
                    return future.result(timeout=settings.llm_timeout_sec)
            else:
                return loop.run_until_complete(self._async_compute(prompt))
        except Exception as e:
            logger.warning(f"语义熵计算失败: {e}")
            return SemanticEntropyResult(
                entropy=0.0,
                is_uncertain=False,
                sample_count=0,
                cluster_count=0,
                uncertainty_score=0.0,
            )

    async def _async_compute(self, prompt: str) -> SemanticEntropyResult:
        n = settings.semantic_entropy_samples
        samples = await self._async_sample(prompt, n)

        if not samples:
            return SemanticEntropyResult(
                entropy=0.0,
                is_uncertain=False,
                sample_count=0,
                cluster_count=0,
                uncertainty_score=0.0,
            )

        # 拒答率检测（v2.0 新增）
        refusal_count = sum(1 for s in samples if _is_refusal(s))
        refusal_rate = refusal_count / len(samples)
        high_refusal_signal = refusal_rate >= 0.6  # 60% 以上采样为拒答

        # 过滤拒答回复后计算语义熵（拒答本身不代表知识边界外）
        non_refusal_samples = [s for s in samples if not _is_refusal(s)]
        compute_samples = non_refusal_samples if len(non_refusal_samples) >= 2 else samples

        clusters = await self._cluster_by_semantics(compute_samples)
        entropy = self._calc_entropy(clusters, len(compute_samples))

        # 归一化：最大熵为 log2(N)
        max_entropy = math.log2(max(len(compute_samples), 2))
        uncertainty_score = min(1.0, entropy / max_entropy)

        # 语义熵风险加成
        entropy_risk_bonus = 0.0
        if entropy > settings.semantic_entropy_threshold:
            entropy_risk_bonus = min(0.15, (entropy - settings.semantic_entropy_threshold) * 0.05)
        if high_refusal_signal:
            entropy_risk_bonus = min(0.20, entropy_risk_bonus + 0.08)

        return SemanticEntropyResult(
            entropy=round(entropy, 4),
            is_uncertain=entropy > settings.semantic_entropy_threshold,
            sample_count=len(samples),
            cluster_count=len(clusters),
            uncertainty_score=round(uncertainty_score, 4),
            refusal_rate=round(refusal_rate, 4),
            high_refusal_signal=high_refusal_signal,
            entropy_risk_bonus=round(entropy_risk_bonus, 4),
        )

    async def _async_sample(self, prompt: str, n: int) -> list[str]:
        try:
            from openai import AsyncOpenAI
            import httpx

            client = AsyncOpenAI(
                base_url=settings.llm_base_url,
                api_key=settings.llm_api_key,
                timeout=settings.llm_timeout_sec,
                http_client=httpx.AsyncClient(timeout=settings.llm_timeout_sec),
            )

            async def _single_sample() -> str:
                resp = await client.chat.completions.create(
                    model=settings.llm_model,
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=100,
                    temperature=0.8,
                )
                return resp.choices[0].message.content.strip()

            tasks = [_single_sample() for _ in range(n)]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            return [r for r in results if isinstance(r, str) and r]

        except Exception as e:
            logger.warning(f"语义熵异步采样失败: {e}")
            return []

    async def _cluster_by_semantics(
        self, responses: list[str]
    ) -> list[list[str]]:
        if not responses:
            return []

        try:
            from sentence_transformers import SentenceTransformer
            import numpy as np

            # 使用与知识库相同的多语言嵌入模型
            model = SentenceTransformer(
                settings.kb_embed_model,
                local_files_only=True,
            )
            embeddings = model.encode(responses, normalize_embeddings=True)

            clusters: list[list[str]] = []
            assigned = [False] * len(responses)

            for i in range(len(responses)):
                if assigned[i]:
                    continue
                cluster = [responses[i]]
                assigned[i] = True
                for j in range(i + 1, len(responses)):
                    if assigned[j]:
                        continue
                    # 归一化后的余弦相似度 = 点积
                    sim = float(np.dot(embeddings[i], embeddings[j]))
                    if sim > 0.85:
                        cluster.append(responses[j])
                        assigned[j] = True
                clusters.append(cluster)

            return clusters

        except Exception as e:
            logger.warning(f"语义聚类失败，降级为单样本簇: {e}")
            return [[r] for r in responses]

    @staticmethod
    def _calc_entropy(clusters: list[list[str]], total: int) -> float:
        """
        计算语义熵：H = -Σ p(c) * log2(p(c))
        """
        if total == 0 or not clusters:
            return 0.0
        entropy = 0.0
        for cluster in clusters:
            p = len(cluster) / total
            if p > 0:
                entropy -= p * math.log2(p)
        return entropy


# 全局单例
semantic_entropy_detector = SemanticEntropyDetector()
