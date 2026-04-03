# RefusalGuard Safety Judge — 推理集成模块


from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from loguru import logger

# 默认模型路径
_DEFAULT_MODEL_PATH = os.environ.get(
    "SAFETY_JUDGE_MODEL_PATH",
    "./safety_judge/model"
)

LABEL_NAMES = {0: "benign", 1: "injection", 2: "harmful"}


@dataclass
class JudgeResult:
    label:      int                    # 0=benign, 1=injection, 2=harmful
    label_name: str                    # 对应的标签名称
    confidence: float                  # 最高类别置信度 (0~1)
    scores:     list[float] = field(default_factory=list)  # [benign, injection, harmful]
    available:  bool = True            # 模型是否可用


class SafetyJudge:

    def __init__(self, model_path: str = _DEFAULT_MODEL_PATH):
        self._model_path = Path(model_path)
        self._model      = None
        self._tokenizer  = None
        self._device     = None
        self._loaded     = False
        self._available  = False

    def _load(self):
        if self._loaded:
            return

        self._loaded = True  # 防止重复尝试

        if not self._model_path.exists():
            logger.warning(
                f"[SafetyJudge] 模型路径不存在: {self._model_path}，"
                "请先完成训练。Safety Judge 将降级为不可用。"
            )
            return

        try:
            import torch
            from transformers import (
                AutoTokenizer,
                AutoModelForSequenceClassification,
            )

            self._device = "cuda" if torch.cuda.is_available() else "cpu"
            logger.info(f"[SafetyJudge] 正在加载模型: {self._model_path} (device={self._device})")

            self._tokenizer = AutoTokenizer.from_pretrained(
                str(self._model_path), local_files_only=True
            )
            self._model = AutoModelForSequenceClassification.from_pretrained(
                str(self._model_path), local_files_only=True
            ).to(self._device)
            self._model.eval()

            self._available = True
            logger.info("[SafetyJudge] 模型加载完成")

        except Exception as e:
            logger.warning(f"[SafetyJudge] 模型加载失败: {e}")
            self._available = False

    def predict(self, text: str, max_length: int = 256) -> JudgeResult:
        if not self._loaded:
            self._load()

        if not self._available:
            return JudgeResult(
                label=0, label_name="benign",
                confidence=0.0, scores=[],
                available=False,
            )

        try:
            import torch

            enc = self._tokenizer(
                text,
                max_length=max_length,
                padding="max_length",
                truncation=True,
                return_tensors="pt",
            )
            enc = {k: v.to(self._device) for k, v in enc.items()}

            with torch.no_grad():
                logits = self._model(**enc).logits
                probs  = torch.softmax(logits, dim=-1)[0].cpu().tolist()

            label      = int(torch.argmax(torch.tensor(probs)).item())
            confidence = round(probs[label], 4)
            scores     = [round(p, 4) for p in probs]

            return JudgeResult(
                label=label,
                label_name=LABEL_NAMES[label],
                confidence=confidence,
                scores=scores,
                available=True,
            )

        except Exception as e:
            logger.warning(f"[SafetyJudge] 推理失败: {e}")
            return JudgeResult(
                label=0, label_name="benign",
                confidence=0.0, scores=[],
                available=False,
            )

    def predict_batch(self, texts: list[str], max_length: int = 256) -> list[JudgeResult]:
        """批量推理（适合离线评估）"""
        return [self.predict(t, max_length) for t in texts]

    @property
    def available(self) -> bool:
        if not self._loaded:
            self._load()
        return self._available


# 全局单例
safety_judge = SafetyJudge()
