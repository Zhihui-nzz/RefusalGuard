import time
from dataclasses import dataclass, field

from loguru import logger

from backend.config import settings

# ── 模型单例缓存（整个进程只加载一次）────────────────────────────────────────────
_injection_pipeline = None

def _get_injection_pipeline():
    """懒加载注入检测模型，全局只初始化一次（懒导入 torch 和 transformers）"""
    global _injection_pipeline
    if _injection_pipeline is None:
        import torch
        from transformers import pipeline
        device_str = settings.resolved_device
        device_id = 0 if device_str == "cuda" else -1
        logger.info(f"正在加载 DeBERTa-v3 检测模型（设备: {device_str}）...")
        start = time.time()
        model_kwargs = {}
        if device_str == "cuda":
            model_kwargs["torch_dtype"] = torch.float16
        _injection_pipeline = pipeline(
            "text-classification",
            model=settings.injection_model_id,
            device=device_id,
            truncation=True,
            max_length=512,
            model_kwargs=model_kwargs,
            local_files_only=True,
        )
        logger.info(f"模型加载完成，耗时 {time.time() - start:.1f}s")
    return _injection_pipeline

@dataclass
class DetectionResult:
    injection_score:  float   # 综合注入得分（0~1）
    rule_triggered:   bool    # 规则引擎是否命中
    semantic_score:   float   # DeBERTa 语义分数
    detection_path:   str     # "rule_fast" | "semantic" | "combined" | "probe_override"
    latency_ms:       float

    intent_score:     float = 0.0   # PIGuard 攻击意图得分
    benign_discount:  float = 0.0   # 正常上下文折扣
    probe_score:      float = 0.0   # 内部探针异常得分（0=不可用）
    probe_triggered:  bool  = False # 内部探针是否触发阈值
    attack_categories: list = field(default_factory=list)  # 命中的攻击类别
    judge_label:      str   = "benign"  # "benign" / "injection" / "harmful"
    judge_confidence: float = 0.0       # Safety Judge 最高类别置信度

class DualChannelDetector:
    """
    双通道检测器 v3.1：
      通道 1：规则引擎（快速）
      通道 2：DeBERTa 语义检测（精准）
      通道 3：内部状态探针（可选）
      通道 4：Safety Judge 三分类模型（v3.1 新增）
    """

    def __init__(self, device: str = "auto"):
        self.device = settings.resolved_device
        # 预热 DeBERTa 模型（避免第一次请求超慢）
        try:
            _get_injection_pipeline()
        except Exception as e:
            logger.warning(f"DeBERTa 模型预热失败（将在首次请求时重试）: {e}")

    def detect(
        self,
        text: str,
        preprocessed,  # PreprocessResult 对象
    ) -> DetectionResult:
        """
        执行四通道检测。
        Args:
            text:         原始（或清洗后的）Prompt 文本
            preprocessed: Preprocessor.process() 的输出（PreprocessResult）
        """
        start = time.time()

        # 超长截断
        if len(text) > settings.max_prompt_length:
            text = text[:settings.max_prompt_length]

        rule_flags = preprocessed.quick_flags
        intent_score = preprocessed.intent_score
        benign_discount = preprocessed.benign_discount
        attack_categories = preprocessed.attack_categories

        # ── 通道 1：规则引擎（已在预处理阶段完成）────────────────────────
        rule_triggered = len(rule_flags) > 0
        # 使用 PIGuard 意图得分替代简单的规则计数
        rule_score = intent_score if rule_triggered else 0.0

        # ── 通道 2：DeBERTa 语义检测 ──────────────────────────────────────
        semantic_score = 0.0
        try:
            pipe = _get_injection_pipeline()
            result = pipe(preprocessed.cleaned)[0]
            if result["label"] == "INJECTION":
                semantic_score = result["score"]
            else:
                semantic_score = 1.0 - result["score"]
        except Exception as e:
            logger.warning(f"DeBERTa 推理失败，使用规则得分: {e}")
            semantic_score = rule_score

        # ── 通道 3：内部状态探针（可选）──────────────────────────────────
        probe_score = 0.0
        probe_triggered = False
        if settings.internal_probe_enabled:
            try:
                from backend.modules.internal_probe import internal_monitor
                probe_result = internal_monitor.analyze(text)
                probe_score = probe_result.anomaly_score
                probe_triggered = probe_result.is_anomalous
            except Exception as e:
                logger.debug(f"内部探针调用失败: {e}")

        # ── 通道 4：Safety Judge 三分类（v3.1 新增）──────────────────────
        judge_label = "benign"
        judge_confidence = 0.0
        if settings.safety_judge_enabled:
            try:
                from backend.modules.safety_judge_detector import safety_judge
                judge_result = safety_judge.predict(text)
                if judge_result.available:
                    judge_label = judge_result.label_name
                    judge_confidence = judge_result.confidence
                    logger.debug(
                        f"[SafetyJudge] label={judge_label} "
                        f"confidence={judge_confidence:.3f}"
                    )
            except Exception as e:
                logger.debug(f"Safety Judge 调用失败（降级）: {e}")

        # ── 融合策略（v3.0 加权融合）─────────────────────────────────────
        injection_score, detection_path = self._fuse_scores(
            rule_score=rule_score,
            semantic_score=semantic_score,
            intent_score=intent_score,
            benign_discount=benign_discount,
            probe_score=probe_score,
            probe_triggered=probe_triggered,
            rule_triggered=rule_triggered,
        )

        latency = (time.time() - start) * 1000

        return DetectionResult(
            injection_score=round(injection_score, 4),
            rule_triggered=rule_triggered,
            semantic_score=round(semantic_score, 4),
            detection_path=detection_path,
            latency_ms=round(latency, 2),
            intent_score=round(intent_score, 4),
            benign_discount=round(benign_discount, 4),
            probe_score=round(probe_score, 4),
            probe_triggered=probe_triggered,
            attack_categories=attack_categories,
            judge_label=judge_label,
            judge_confidence=round(judge_confidence, 4),
        )

    def _fuse_scores(
        self,
        rule_score: float,
        semantic_score: float,
        intent_score: float,
        benign_discount: float,
        probe_score: float,
        probe_triggered: bool,
        rule_triggered: bool,
    ) -> tuple[float, str]:
        """
        多信号融合策略（v3.0）。
        优先级：内部探针 Hard Block > 双重确认 > 语义单通道 > 规则单通道
        """
        # 优先级 1：内部探针触发 → 直接 Hard Block
        if probe_triggered and probe_score >= settings.probe_anomaly_threshold:
            return min(1.0, probe_score), "probe_override"

        # 优先级 2：DeBERTa 超高置信度（>= 0.90）→ 直接返回
        if semantic_score >= settings.injection_hard_block:
            return semantic_score, "semantic_hard_block"

        # 优先级 3：双重确认（规则 + 语义都怀疑）
        if rule_triggered and semantic_score > 0.30:
            # 加权融合：语义 60% + 规则意图 30% + 探针 10%
            fused = (
                semantic_score * 0.60
                + intent_score * 0.30
                + probe_score * 0.10
            )
            # 双重确认加成
            fused = min(1.0, fused * 1.10)
            return fused, "combined"

        # 优先级 4：仅规则命中
        if rule_triggered and semantic_score <= 0.30:
            # 规则命中但语义不确认，适当降权（减少误报）
            fused = max(intent_score, semantic_score * 0.80)
            return fused, "rule_fast"

        # 优先级 5：仅语义检测
        return semantic_score, "semantic"
