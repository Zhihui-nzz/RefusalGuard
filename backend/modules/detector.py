import torch
from transformers import pipeline
from dataclasses import dataclass
from loguru import logger
import time
from backend.config import settings

# ── 模型单例缓存（整个进程只加载一次）──────────────────────
_injection_pipeline = None

def _get_injection_pipeline():
    """懒加载注入检测模型，全局只初始化一次"""
    global _injection_pipeline
    if _injection_pipeline is None:
        device_str = settings.resolved_device
        device_id  = 0 if device_str == "cuda" else -1
        logger.info(f"正在加载 DeBERTa-v3 检测模型（设备: {device_str}）...")
        start = time.time()
        model_kwargs = {}
        if device_str == "cuda":
            model_kwargs["torch_dtype"] = torch.float16  # 半精度，节省约50%显存
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
    injection_score: float      # 0.0 ~ 1.0，越高越危险
    rule_triggered: bool        # 规则引擎是否命中
    semantic_score: float       # DeBERTa 语义分数
    detection_path: str         # "rule_fast" | "semantic" | "combined"
    latency_ms: float

class DualChannelDetector:
    """双通道检测器：规则引擎（快速）+ DeBERTa 语义检测（精准）"""

    def __init__(self, device: str = "auto"):
        # device 参数保留兼容性，实际由 settings.resolved_device 决定
        self.device = settings.resolved_device
        # 触发懒加载（启动时预热，避免第一次请求超慢）
        _get_injection_pipeline()
    
    def detect(self, text: str, rule_flags: list) -> DetectionResult:
        start = time.time()

        # 超长截断（防止超长输入崩溃）
        if len(text) > settings.max_prompt_length:
            text = text[:settings.max_prompt_length]

        # 通道1：规则引擎结果（已在预处理阶段完成）
        rule_triggered = len(rule_flags) > 0
        rule_score = min(0.3 * len(rule_flags), 0.9) if rule_triggered else 0.0

        # 通道2：DeBERTa 语义检测
        pipe   = _get_injection_pipeline()
        result = pipe(text)[0]
        # 模型输出标签为 "INJECTION" 或 "LEGITIMATE"
        if result["label"] == "INJECTION":
            semantic_score = result["score"]
        else:
            semantic_score = 1.0 - result["score"]

        # 融合策略：取最大值，规则命中时加权提升
        if rule_triggered and semantic_score > 0.3:
            # 双重确认：规则 + 语义都怀疑，高置信度
            injection_score = max(rule_score, semantic_score) * 1.1
            path = "combined"
        elif rule_triggered:
            injection_score = max(rule_score, semantic_score * 0.8)
            path = "rule_fast"
        else:
            injection_score = semantic_score
            path = "semantic"

        injection_score = min(injection_score, 1.0)
        latency = (time.time() - start) * 1000

        return DetectionResult(
            injection_score=injection_score,
            rule_triggered=rule_triggered,
            semantic_score=semantic_score,
            detection_path=path,
            latency_ms=latency,
        )