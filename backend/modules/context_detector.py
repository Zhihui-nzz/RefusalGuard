"""
多轮会话上下文检测器 v1.0
核心思想（来自 ACL 2024 研究）：
  - 单轮检测无法发现"煮青蛙"式渐进越狱
  - 维护每个用户的会话历史，计算累积风险分
  - 若最近 N 轮的平均风险分超过阈值，触发会话级警报

用法：
    from backend.modules.context_detector import ContextDetector
    ctx = ContextDetector()
    ctx.add_turn(user_id, prompt, turn_risk_score)
    context_risk = ctx.get_session_risk(user_id)
"""
from collections import defaultdict, deque
from dataclasses import dataclass
from backend.config import settings


@dataclass
class TurnRecord:
    prompt:     str
    risk_score: float
    timestamp:  float


class ContextDetector:
    """
    多轮会话风险累积检测器
    - 每个 user_id 维护一个固定长度的滑动窗口
    - 计算加权平均风险分（近期轮次权重更高）
    - 检测"分段注入"：将多轮消息拼接后再做规则扫描
    """

    def __init__(self):
        # user_id -> deque of TurnRecord
        self._sessions: dict[str, deque] = defaultdict(
            lambda: deque(maxlen=settings.session_history_maxlen)
        )

    def add_turn(self, user_id: str, prompt: str, risk_score: float) -> None:
        """记录一轮对话的风险分"""
        import time
        self._sessions[user_id].append(
            TurnRecord(prompt=prompt, risk_score=risk_score, timestamp=time.time())
        )

    def get_session_risk(self, user_id: str) -> float:
        """
        计算当前会话的累积风险分（加权平均，近期权重更高）
        返回值：0.0 ~ 1.0
        """
        history = list(self._sessions.get(user_id, []))
        if not history:
            return 0.0

        n = len(history)
        # 线性权重：最新轮次权重最高
        weights = [i + 1 for i in range(n)]
        total_w = sum(weights)
        weighted_risk = sum(
            w * r.risk_score for w, r in zip(weights, history)
        ) / total_w

        # 若最近3轮均为 WARN 级别（>0.4），额外加权
        recent = history[-3:]
        if len(recent) >= 2 and all(r.risk_score > 0.4 for r in recent):
            weighted_risk = min(1.0, weighted_risk * 1.3)

        return round(weighted_risk, 4)

    def detect_segmented_injection(self, user_id: str) -> float:
        """
        分段注入检测：将最近3轮消息拼接后做规则扫描
        防止攻击者将注入指令拆分到多条消息中
        """
        history = list(self._sessions.get(user_id, []))
        if len(history) < 2:
            return 0.0

        from backend.modules.preprocessor import Preprocessor
        preprocessor = Preprocessor()
        combined = " ".join(r.prompt for r in history[-3:])
        return preprocessor.detect_segmented_injection(
            [r.prompt for r in history[-3:]]
        )

    def clear_session(self, user_id: str) -> None:
        """清除用户会话历史（用于测试或用户注销）"""
        if user_id in self._sessions:
            del self._sessions[user_id]

    def get_session_length(self, user_id: str) -> int:
        """返回当前会话轮次数"""
        return len(self._sessions.get(user_id, []))
