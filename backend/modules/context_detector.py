import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Optional

from loguru import logger

from backend.config import settings

@dataclass
class TurnRecord:
    prompt:       str
    risk_score:   float
    timestamp:    float
    intent_vec:   Optional[list] = None  # 语义向量

@dataclass
class DriftAnalysis:
    drift_score:       float   # 漂移得分（0~1）
    is_drifting:       bool    # 是否检测到显著漂移
    drift_direction:   str     # "normal" | "suspicious" | "attack"
    consecutive_drifts: int    # 连续漂移轮次数
    drift_details:     list = field(default_factory=list)

class ContextDetector:

    # 意图漂移相关阈值
    _DRIFT_THRESHOLD        = 0.35   # 单次漂移阈值
    _CONSECUTIVE_DRIFT_WARN = 2      # 连续漂移次数触发警告
    _CONSECUTIVE_DRIFT_BLOCK = 3     # 连续漂移次数触发阻断

    def __init__(self):
        # user_id -> deque of TurnRecord
        self._sessions: dict[str, deque] = defaultdict(
            lambda: deque(maxlen=settings.session_history_maxlen)
        )
        self._embedder = None

    def _get_embedder(self):
        """懒加载语义嵌入模型"""
        if self._embedder is None:
            try:
                from sentence_transformers import SentenceTransformer
                self._embedder = SentenceTransformer(
                    settings.kb_embed_model,
                    local_files_only=True,
                )
                logger.info("意图漂移检测嵌入模型加载完成")
            except Exception as e:
                logger.warning(f"嵌入模型加载失败，意图漂移检测将降级: {e}")
        return self._embedder

    def add_turn(
        self,
        user_id: str,
        prompt: str,
        risk_score: float,
    ) -> None:
        """记录一轮对话，并计算语义向量（用于后续漂移检测）"""
        intent_vec = None
        if settings.intent_drift_enabled:
            embedder = self._get_embedder()
            if embedder is not None:
                try:
                    vec = embedder.encode([prompt], normalize_embeddings=True)
                    intent_vec = vec[0].tolist()
                except Exception as e:
                    logger.debug(f"意图向量计算失败: {e}")

        self._sessions[user_id].append(
            TurnRecord(
                prompt=prompt,
                risk_score=risk_score,
                timestamp=time.time(),
                intent_vec=intent_vec,
            )
        )

    def get_session_risk(self, user_id: str) -> float:
        history = list(self._sessions.get(user_id, []))
        if not history:
            return 0.0

        now = time.time()
        n = len(history)

        weights = []
        for i, record in enumerate(history):
            position_weight = i + 1  # 越新权重越高
            time_decay = max(0.1, 1.0 - (now - record.timestamp) / 3600)  # 1小时内线性衰减
            weights.append(position_weight * time_decay)

        total_w = sum(weights)
        weighted_risk = sum(
            w * r.risk_score for w, r in zip(weights, history)
        ) / total_w

        # 若最近 3 轮均为 WARN 级别（>0.4），额外加权
        recent = history[-3:]
        if len(recent) >= 2 and all(r.risk_score > 0.4 for r in recent):
            weighted_risk = min(1.0, weighted_risk * 1.3)

        return round(weighted_risk, 4)

    def analyze_intent_drift(self, user_id: str) -> DriftAnalysis:
        if not settings.intent_drift_enabled:
            return DriftAnalysis(
                drift_score=0.0,
                is_drifting=False,
                drift_direction="normal",
                consecutive_drifts=0,
            )

        history = list(self._sessions.get(user_id, []))
        if len(history) < 2:
            return DriftAnalysis(
                drift_score=0.0,
                is_drifting=False,
                drift_direction="normal",
                consecutive_drifts=0,
            )

        # 过滤出有语义向量的轮次
        vec_records = [r for r in history if r.intent_vec is not None]
        if len(vec_records) < 2:
            return DriftAnalysis(
                drift_score=0.0,
                is_drifting=False,
                drift_direction="normal",
                consecutive_drifts=0,
            )

        try:
            import numpy as np

            drift_scores = []
            drift_details = []
            consecutive_drifts = 0
            max_consecutive = 0

            for i in range(1, len(vec_records)):
                prev_vec = np.array(vec_records[i - 1].intent_vec)
                curr_vec = np.array(vec_records[i].intent_vec)

                # 余弦距离 = 1 - 余弦相似度
                cosine_sim = float(np.dot(prev_vec, curr_vec))
                cosine_dist = 1.0 - cosine_sim

                drift_scores.append(cosine_dist)
                drift_details.append({
                    "turn": i,
                    "cosine_distance": round(cosine_dist, 4),
                    "is_drift": cosine_dist > settings.intent_drift_threshold,
                })

                if cosine_dist > settings.intent_drift_threshold:
                    consecutive_drifts += 1
                    max_consecutive = max(max_consecutive, consecutive_drifts)
                else:
                    consecutive_drifts = 0

            # 综合漂移得分：近期漂移权重更高
            if drift_scores:
                n = len(drift_scores)
                weights = [i + 1 for i in range(n)]
                total_w = sum(weights)
                drift_score = sum(
                    w * s for w, s in zip(weights, drift_scores)
                ) / total_w
            else:
                drift_score = 0.0

            # 判断漂移方向
            if max_consecutive >= self._CONSECUTIVE_DRIFT_BLOCK:
                drift_direction = "attack"
                is_drifting = True
            elif max_consecutive >= self._CONSECUTIVE_DRIFT_WARN or drift_score > 0.4:
                drift_direction = "suspicious"
                is_drifting = True
            else:
                drift_direction = "normal"
                is_drifting = False

            if is_drifting:
                logger.warning(
                    f"意图漂移检测：user={user_id}, "
                    f"drift_score={drift_score:.3f}, "
                    f"direction={drift_direction}, "
                    f"consecutive={max_consecutive}"
                )

            return DriftAnalysis(
                drift_score=round(drift_score, 4),
                is_drifting=is_drifting,
                drift_direction=drift_direction,
                consecutive_drifts=max_consecutive,
                drift_details=drift_details,
            )

        except Exception as e:
            logger.warning(f"意图漂移分析失败: {e}")
            return DriftAnalysis(
                drift_score=0.0,
                is_drifting=False,
                drift_direction="normal",
                consecutive_drifts=0,
            )

    def detect_segmented_injection(self, user_id: str) -> float:
        history = list(self._sessions.get(user_id, []))
        if len(history) < 2:
            return 0.0

        from backend.modules.preprocessor import Preprocessor
        preprocessor = Preprocessor()
        combined_prompts = [r.prompt for r in history[-3:]]
        return preprocessor.detect_segmented_injection(combined_prompts)

    def get_combined_context_risk(self, user_id: str) -> dict:
        session_risk = self.get_session_risk(user_id)
        drift_analysis = self.analyze_intent_drift(user_id)
        segmented_score = self.detect_segmented_injection(user_id)

        # 综合上下文风险
        combined_risk = max(
            session_risk,
            drift_analysis.drift_score * 0.8,
            segmented_score * 0.9,
        )

        # 攻击级漂移直接提升风险
        if drift_analysis.drift_direction == "attack":
            combined_risk = min(1.0, combined_risk + 0.20)
        elif drift_analysis.drift_direction == "suspicious":
            combined_risk = min(1.0, combined_risk + 0.10)

        return {
            "session_risk":              round(session_risk, 4),
            "drift_score":               drift_analysis.drift_score,
            "drift_direction":           drift_analysis.drift_direction,
            "consecutive_drifts":        drift_analysis.consecutive_drifts,
            "segmented_injection_score": round(segmented_score, 4),
            "combined_risk":             round(combined_risk, 4),
        }

    def clear_session(self, user_id: str) -> None:
        """清除用户会话历史"""
        if user_id in self._sessions:
            del self._sessions[user_id]

    def get_session_length(self, user_id: str) -> int:
        """返回当前会话轮次数"""
        return len(self._sessions.get(user_id, []))
