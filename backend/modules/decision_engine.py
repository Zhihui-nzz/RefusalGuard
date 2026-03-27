"""
M4: 决策引擎 v2.1
修复：
  1. 注入分 >= hard_block_threshold 时直接 BLOCK（快速路径），不走加权公式
  2. 重新设计权重：injection 权重提升至 0.65，确保高注入分能触发 BLOCK
  3. 引入 context_risk（多轮会话风险）作为第三维度
  4. 所有阈值从 settings 读取，.env 可随时调整，无需改代码重启
"""
from dataclasses import dataclass
from enum import Enum
from backend.config import settings


class Decision(str, Enum):
    BLOCK   = "BLOCK"    # 高风险：直接拦截，返回拒答
    WARN    = "WARN"     # 中风险：带警告通过，记录日志
    MONITOR = "MONITOR"  # 低风险：静默监控，正常转发
    PASS    = "PASS"     # 安全：直接转发


@dataclass
class DecisionResult:
    decision:        Decision
    risk_score:      float
    breakdown:       dict
    threshold_used:  float
    reason:          str


class DecisionEngine:

    def decide(
        self,
        injection_score:     float,
        kb_confidence:       float,
        user_trust:          float = 0.5,
        temporal_risk:       float = 0.0,
        context_sensitivity: float = 0.5,
        context_risk:        float = 0.0,   # 多轮会话累积风险
        zh_rule_score:       float = 0.0,   # 中文规则命中分
    ) -> DecisionResult:

        # ── 快速路径：注入分超过硬阈值，直接 BLOCK ──────────────
        if injection_score >= settings.injection_hard_block:
            return DecisionResult(
                decision=Decision.BLOCK,
                risk_score=1.0,
                breakdown={
                    "injection_score":    injection_score,
                    "kb_confidence":      kb_confidence,
                    "user_trust":         user_trust,
                    "temporal_risk":      temporal_risk,
                    "context_sensitivity": context_sensitivity,
                    "context_risk":       context_risk,
                    "zh_rule_score":      zh_rule_score,
                    "fast_path":          True,
                },
                threshold_used=settings.injection_hard_block,
                reason=(
                    f"注入分 {injection_score:.3f} 超过硬阈值 "
                    f"{settings.injection_hard_block}，快速路径直接拦截"
                ),
            )

        # ── 中文规则快速路径 ──────────────────────────────────────
        if zh_rule_score >= 0.45 and injection_score >= 0.5:
            return DecisionResult(
                decision=Decision.BLOCK,
                risk_score=max(injection_score, zh_rule_score),
                breakdown={
                    "injection_score":    injection_score,
                    "kb_confidence":      kb_confidence,
                    "user_trust":         user_trust,
                    "temporal_risk":      temporal_risk,
                    "context_sensitivity": context_sensitivity,
                    "context_risk":       context_risk,
                    "zh_rule_score":      zh_rule_score,
                    "fast_path":          True,
                },
                threshold_used=0.45,
                reason=(
                    f"中文越狱规则命中（zh_rule={zh_rule_score:.2f}）"
                    f"且注入分 {injection_score:.2f} 超过 0.5"
                ),
            )

        # ── 常规加权公式 ──────────────────────────────────────────
        # R = 0.65*inj + 0.20*(1-kb) + 0.10*ctx - 0.05*trust
        risk_score = (
            settings.weight_injection * injection_score
            + settings.weight_kb       * (1.0 - kb_confidence)
            + settings.weight_temporal * context_risk
            - settings.weight_trust    * user_trust
        )
        risk_score = max(0.0, min(1.0, risk_score))

        # 上下文敏感度动态调整阈值
        sensitivity_factor = 0.9 + 0.2 * context_sensitivity
        adj = {
            Decision.BLOCK:   settings.threshold_block   / sensitivity_factor,
            Decision.WARN:    settings.threshold_warn    / sensitivity_factor,
            Decision.MONITOR: settings.threshold_monitor / sensitivity_factor,
        }

        if risk_score >= adj[Decision.BLOCK]:
            decision = Decision.BLOCK
            reason = (
                f"高风险注入（注入分={injection_score:.3f}，"
                f"综合风险={risk_score:.3f}，阈值={adj[Decision.BLOCK]:.3f}）"
            )
        elif risk_score >= adj[Decision.WARN]:
            decision = Decision.WARN
            reason = (
                f"中风险，建议人工审核"
                f"（综合风险={risk_score:.3f}，阈值={adj[Decision.WARN]:.3f}）"
            )
        elif risk_score >= adj[Decision.MONITOR]:
            decision = Decision.MONITOR
            reason = (
                f"低风险，静默监控"
                f"（综合风险={risk_score:.3f}，阈值={adj[Decision.MONITOR]:.3f}）"
            )
        else:
            decision = Decision.PASS
            reason = "未检测到威胁"

        return DecisionResult(
            decision=decision,
            risk_score=risk_score,
            breakdown={
                "injection_score":    injection_score,
                "kb_confidence":      kb_confidence,
                "user_trust":         user_trust,
                "temporal_risk":      temporal_risk,
                "context_sensitivity": context_sensitivity,
                "context_risk":       context_risk,
                "zh_rule_score":      zh_rule_score,
                "fast_path":          False,
            },
            threshold_used=adj.get(decision, 0.0),
            reason=reason,
        )
