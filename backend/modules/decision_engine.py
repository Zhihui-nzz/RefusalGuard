from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from backend.config import settings

class Decision(str, Enum):
    BLOCK   = "BLOCK"
    WARN    = "WARN"
    MONITOR = "MONITOR"
    PASS    = "PASS"

@dataclass
class DecisionResult:
    decision:          Decision
    risk_score:        float
    breakdown:         dict
    triggered_signals: list  = field(default_factory=list)
    threshold_method:  str   = "fallback"

class DecisionEngine:
    def decide(
        self,
        injection_score:     float,
        kb_confidence:       float,
        intent_score:        float = 0.0,
        benign_discount:     float = 0.0,
        boundary_state:      str   = "known",
        boundary_risk_bonus: float = 0.0,
        probe_score:         float = 0.0,
        probe_triggered:     bool  = False,
        entropy_risk_bonus:  float = 0.0,
        rag_injection_score: float = 0.0,
        drift_score:         float = 0.0,
        drift_direction:     str   = "normal",
        user_trust:          float = 0.5,
        context_sensitivity: float = 0.5,
        context_risk:        float = 0.0,
        zh_rule_score:       float = 0.0,
        judge_label:         str   = "benign",
        judge_confidence:    float = 0.0,
    ) -> DecisionResult:

        triggered_signals: list[str] = []

        #  path 1：内部探针 Hard Block 
        if probe_triggered and probe_score >= settings.probe_anomaly_threshold:
            triggered_signals.append(f"probe_hard_block({probe_score:.3f})")
            return DecisionResult(
                decision=Decision.BLOCK,
                risk_score=1.0,
                breakdown=self._make_breakdown(
                    injection_score, intent_score, benign_discount, kb_confidence,
                    boundary_state, boundary_risk_bonus, probe_score,
                    entropy_risk_bonus, rag_injection_score, drift_score,
                    drift_direction, user_trust, context_risk, zh_rule_score,
                    judge_label, judge_confidence, 0.0,
                ),
                triggered_signals=triggered_signals,
                threshold_method="probe_hard_block",
            )

        # path 2：DeBERTa 高置信度注入 
        if injection_score >= settings.injection_hard_block:
            if benign_discount >= 0.30:
                triggered_signals.append(
                    f"injection_high_benign_ctx({injection_score:.3f})"
                )
            else:
                triggered_signals.append(
                    f"injection_hard_block({injection_score:.3f})"
                )
                return DecisionResult(
                    decision=Decision.BLOCK,
                    risk_score=1.0,
                    breakdown=self._make_breakdown(
                        injection_score, intent_score, benign_discount, kb_confidence,
                        boundary_state, boundary_risk_bonus, probe_score,
                        entropy_risk_bonus, rag_injection_score, drift_score,
                        drift_direction, user_trust, context_risk, zh_rule_score,
                        judge_label, judge_confidence, 0.0,
                    ),
                    triggered_signals=triggered_signals,
                    threshold_method="semantic_hard_block",
                )

        # path 3：中文越狱规则高置信度命中 
        if zh_rule_score >= 0.80:
            if benign_discount >= 0.25:
                triggered_signals.append(
                    f"zh_rule_high_benign_ctx({zh_rule_score:.3f})"
                )
            else:
                triggered_signals.append(
                    f"zh_rule_hard_block({zh_rule_score:.3f})"
                )
                return DecisionResult(
                    decision=Decision.BLOCK,
                    risk_score=1.0,
                    breakdown=self._make_breakdown(
                        injection_score, intent_score, benign_discount, kb_confidence,
                        boundary_state, boundary_risk_bonus, probe_score,
                        entropy_risk_bonus, rag_injection_score, drift_score,
                        drift_direction, user_trust, context_risk, zh_rule_score,
                        judge_label, judge_confidence, 0.0,
                    ),
                    triggered_signals=triggered_signals,
                    threshold_method="zh_rule_hard_block",
                )

        #  加权公式 
        rag_injection_bonus = min(0.15, rag_injection_score * 0.20)

        drift_bonus = 0.0
        if drift_direction == "suspicious":
            drift_bonus = min(0.10, drift_score * 0.25)
            triggered_signals.append(f"intent_drift_suspicious({drift_score:.3f})")
        elif drift_direction == "attack":
            drift_bonus = min(0.12, drift_score * 0.30)
            triggered_signals.append(f"intent_drift_attack({drift_score:.3f})")

        # Safety Judge 加成：injection/harmful 加分，benign 按梯度减分
        judge_bonus = 0.0
        if judge_label == "injection" and judge_confidence > 0.0:
            judge_bonus = settings.weight_safety_judge * judge_confidence
            triggered_signals.append(f"judge_injection({judge_confidence:.3f})")
        elif judge_label == "harmful" and judge_confidence > 0.0:
            judge_bonus = settings.weight_safety_judge * judge_confidence * 0.70
            triggered_signals.append(f"judge_harmful({judge_confidence:.3f})")
        elif judge_label == "benign":
            if judge_confidence >= 0.80:
                judge_bonus = -settings.weight_safety_judge * judge_confidence * 0.75
                triggered_signals.append(f"judge_benign_strong({judge_confidence:.3f})")
            elif judge_confidence >= 0.60:
                judge_bonus = -settings.weight_safety_judge * judge_confidence * 0.50
                triggered_signals.append(f"judge_benign({judge_confidence:.3f})")
            elif judge_confidence >= 0.40:
                judge_bonus = -settings.weight_safety_judge * judge_confidence * 0.25
                triggered_signals.append(f"judge_benign_weak({judge_confidence:.3f})")

        # Safety Judge 主导：极高置信度 benign 时设置风险上限
        judge_benign_cap = 1.0
        if judge_label == "benign" and judge_confidence >= 0.85:
            judge_benign_cap = settings.threshold_warn - 0.05
            triggered_signals.append(
                f"judge_benign_cap_applied({judge_confidence:.3f})"
            )

        temporal_risk = max(context_risk, drift_score * 0.5)
        risk_score = (
            settings.weight_injection * injection_score
            + settings.weight_intent  * intent_score
            + settings.weight_kb      * (1.0 - kb_confidence)
            + boundary_risk_bonus
            + settings.weight_temporal * temporal_risk
            + entropy_risk_bonus
            + rag_injection_bonus
            + drift_bonus
            + judge_bonus
            - settings.weight_trust * user_trust
            - benign_discount * 0.15
        )
        risk_score = max(0.0, min(judge_benign_cap, risk_score))

        #  阈值判断 
        block_threshold   = settings.threshold_block
        warn_threshold    = settings.threshold_warn
        monitor_threshold = settings.threshold_monitor
        threshold_method  = "fallback"

        if settings.conformal_prediction_enabled:
            try:
                from backend.modules.conformal_threshold import ConformalThresholdCalibrator
                calib = ConformalThresholdCalibrator()
                thresholds = calib.current_thresholds
                block_threshold   = thresholds.block_threshold
                warn_threshold    = thresholds.warn_threshold
                monitor_threshold = thresholds.monitor_threshold
                threshold_method  = thresholds.method
            except Exception:
                pass

        if risk_score >= block_threshold:
            decision = Decision.BLOCK
        elif risk_score >= warn_threshold:
            decision = Decision.WARN
        elif risk_score >= monitor_threshold:
            decision = Decision.MONITOR
        else:
            decision = Decision.PASS

        return DecisionResult(
            decision=decision,
            risk_score=round(risk_score, 4),
            breakdown=self._make_breakdown(
                injection_score, intent_score, benign_discount, kb_confidence,
                boundary_state, boundary_risk_bonus, probe_score,
                entropy_risk_bonus, rag_injection_score, drift_score,
                drift_direction, user_trust, context_risk, zh_rule_score,
                judge_label, judge_confidence, judge_bonus,
            ),
            triggered_signals=triggered_signals,
            threshold_method=threshold_method,
        )

    @staticmethod
    def _make_breakdown(
        injection_score, intent_score, benign_discount, kb_confidence,
        boundary_state, boundary_risk_bonus, probe_score,
        entropy_risk_bonus, rag_injection_score, drift_score,
        drift_direction, user_trust, context_risk, zh_rule_score,
        judge_label, judge_confidence, judge_bonus,
    ) -> dict:
        return {
            "injection_score":     round(injection_score, 4),
            "intent_score":        round(intent_score, 4),
            "benign_discount":     round(benign_discount, 4),
            "kb_confidence":       round(kb_confidence, 4),
            "boundary_state":      boundary_state,
            "boundary_risk_bonus": round(boundary_risk_bonus, 4),
            "probe_score":         round(probe_score, 4),
            "entropy_risk_bonus":  round(entropy_risk_bonus, 4),
            "rag_injection_score": round(rag_injection_score, 4),
            "drift_score":         round(drift_score, 4),
            "drift_direction":     drift_direction,
            "user_trust":          round(user_trust, 4),
            "context_risk":        round(context_risk, 4),
            "zh_rule_score":       round(zh_rule_score, 4),
            "judge_label":         judge_label,
            "judge_confidence":    round(judge_confidence, 4),
            "judge_bonus":         round(judge_bonus, 4),
        }
