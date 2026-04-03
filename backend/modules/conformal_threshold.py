import json
import math
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from loguru import logger

from backend.config import settings

@dataclass
class ThresholdResult:
    """自适应阈值计算结果"""
    block_threshold:   float   # 自适应 BLOCK 阈值
    warn_threshold:    float   # 自适应 WARN 阈值
    confidence_level:  float   # 置信度
    calibration_size:  int     # 校准集大小
    method:            str     # "conformal" | "fallback"
    # 统计信息
    quantile_value:    float = 0.0   # 分位数值
    coverage_estimate: float = 0.0   # 估计覆盖率

class ConformalThresholdCalibrator:
    # 共形预测自适应阈值校准器。
    # 最小校准集大小
    _MIN_CALIBRATION_SIZE = 50

    def __init__(self):
        self._calibration_scores: list[float] = []  # 正常样本的风险分列表
        self._attack_scores: list[float] = []        # 攻击样本的风险分列表
        self._current_thresholds: Optional[ThresholdResult] = None
        self._is_calibrated = False

        self._load_calibration_data()

    def _load_calibration_data(self):
        """从 JSON 文件加载校准数据集"""
        data_path = Path(settings.conformal_calibration_data_path)
        if not data_path.exists():
            logger.info(
                f"共形预测校准数据文件不存在: {data_path}，"
                "将使用内置示例数据进行初始化"
            )
            self._init_with_example_data()
            return

        try:
            with open(data_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            self._calibration_scores = data.get("normal_scores", [])
            self._attack_scores = data.get("attack_scores", [])

            if len(self._calibration_scores) >= self._MIN_CALIBRATION_SIZE:
                self._is_calibrated = True
                logger.info(
                    f"共形预测校准数据加载完成：正常样本 {len(self._calibration_scores)} 个，"
                    f"攻击样本 {len(self._attack_scores)} 个"
                )
            else:
                logger.warning(
                    f"校准数据不足（{len(self._calibration_scores)} < {self._MIN_CALIBRATION_SIZE}），"
                    "将使用内置示例数据补充"
                )
                self._init_with_example_data()

        except Exception as e:
            logger.warning(f"校准数据加载失败: {e}，使用内置示例数据")
            self._init_with_example_data()

    def _init_with_example_data(self):
        # 使用内置示例数据初始化校准集
        import random
        random.seed(42)
        normal_scores = []
        for _ in range(200):
            score = max(0.0, min(0.5, random.gauss(0.15, 0.08)))
            normal_scores.append(round(score, 4))

        # 攻击请求的风险分分布
        attack_scores = []
        for _ in range(200):
            score = max(0.3, min(1.0, random.gauss(0.78, 0.12)))
            attack_scores.append(round(score, 4))

        self._calibration_scores = normal_scores
        self._attack_scores = attack_scores
        self._is_calibrated = True

        logger.info(
            f"使用内置示例数据初始化共形预测校准集：{len(normal_scores)} 个正常样本"
        )

    def compute_thresholds(self) -> ThresholdResult:

        # 使用分割共形预测计算自适应阈值。

        if not settings.conformal_prediction_enabled:
            return self._fallback_thresholds()

        if not self._is_calibrated or len(self._calibration_scores) < self._MIN_CALIBRATION_SIZE:
            logger.warning("共形预测校准数据不足，使用硬编码阈值")
            return self._fallback_thresholds()

        try:
            alpha = 1.0 - settings.conformal_confidence_level  # 如 0.05
            n = len(self._calibration_scores)

            # 分割共形预测：计算第 ⌈(n+1)(1-α)⌉/n 分位数
            sorted_scores = sorted(self._calibration_scores)
            quantile_idx = math.ceil((n + 1) * (1 - alpha)) - 1
            quantile_idx = max(0, min(quantile_idx, n - 1))
            quantile_value = sorted_scores[quantile_idx]

            # BLOCK 阈值：以正常样本的 (1-α) 分位数为基础
            # 确保不低于配置文件中的最低安全阈值
            block_threshold = max(
                settings.threshold_block,
                min(quantile_value * 1.2, 0.90)  # 适当提高以减少误报
            )

            # WARN 阈值：BLOCK 阈值的 65%
            warn_threshold = max(
                settings.threshold_warn,
                block_threshold * 0.65,
            )

            # 估计覆盖率
            coverage = sum(
                1 for s in self._calibration_scores if s < block_threshold
            ) / n

            result = ThresholdResult(
                block_threshold=round(block_threshold, 4),
                warn_threshold=round(warn_threshold, 4),
                confidence_level=settings.conformal_confidence_level,
                calibration_size=n,
                method="conformal",
                quantile_value=round(quantile_value, 4),
                coverage_estimate=round(coverage, 4),
            )

            self._current_thresholds = result
            logger.info(
                f"共形预测阈值计算完成：BLOCK={block_threshold:.4f}, "
                f"WARN={warn_threshold:.4f}, 覆盖率={coverage:.4f}"
            )
            return result

        except Exception as e:
            logger.warning(f"共形预测阈值计算失败: {e}，使用硬编码阈值")
            return self._fallback_thresholds()

    def _fallback_thresholds(self) -> ThresholdResult:
        """降级：使用配置文件中的硬编码阈值"""
        return ThresholdResult(
            block_threshold=settings.threshold_block,
            warn_threshold=settings.threshold_warn,
            confidence_level=settings.conformal_confidence_level,
            calibration_size=len(self._calibration_scores),
            method="fallback",
        )

    def update_online(self, risk_score: float, is_attack: bool) -> None:
        if is_attack:
            self._attack_scores.append(risk_score)
            if len(self._attack_scores) > 5000:
                self._attack_scores = self._attack_scores[-5000:]
        else:
            self._calibration_scores.append(risk_score)
            if len(self._calibration_scores) > 5000:
                self._calibration_scores = self._calibration_scores[-5000:]

        # 每积累 50 个新样本重新计算阈值
        total = len(self._calibration_scores) + len(self._attack_scores)
        if total % 50 == 0 and settings.conformal_prediction_enabled:
            self.compute_thresholds()

    def save_calibration_data(self) -> None:
        try:
            data_path = Path(settings.conformal_calibration_data_path)
            data_path.parent.mkdir(parents=True, exist_ok=True)
            with open(data_path, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "normal_scores": self._calibration_scores,
                        "attack_scores": self._attack_scores,
                    },
                    f,
                    ensure_ascii=False,
                    indent=2,
                )
            logger.info(f"校准数据已保存: {data_path}")
        except Exception as e:
            logger.warning(f"校准数据保存失败: {e}")

    @property
    def current_thresholds(self) -> ThresholdResult:
        if self._current_thresholds is None:
            self._current_thresholds = self.compute_thresholds()
        return self._current_thresholds

# 全局单例
conformal_calibrator = ConformalThresholdCalibrator()
