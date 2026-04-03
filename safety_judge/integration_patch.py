"""
RefusalGuard detector.py 集成补丁
===================================
将此文件中的代码片段合并到 RefusalGuard 项目的
backend/modules/detector.py 中，即可启用 Safety Judge。

步骤：
1. 将 safety_judge_detector.py 复制到 backend/modules/ 目录
2. 在 detector.py 顶部添加以下 import
3. 在 detect() 方法中添加 Safety Judge 信号
4. 在 config.py 中添加 safety_judge_enabled 配置项
"""

# ── 步骤 1：在 detector.py 顶部添加 ──────────────────────────────────────
IMPORT_PATCH = """
# Safety Judge 集成
from backend.modules.safety_judge_detector import safety_judge, JudgeResult
"""

# ── 步骤 2：在 detect() 方法中，于 DeBERTa 检测之后添加以下代码 ───────────
DETECT_PATCH = """
# ── Safety Judge（微调三分类模型）──────────────────────────────────────
judge_result = JudgeResult(label=0, label_name="benign", confidence=0.0, available=False)
if settings.safety_judge_enabled and safety_judge.available:
    judge_result = safety_judge.predict(prompt)
    logger.debug(
        f"Safety Judge: label={judge_result.label_name}, "
        f"confidence={judge_result.confidence:.3f}, "
        f"scores={judge_result.scores}"
    )
"""

# ── 步骤 3：在 DecisionEngine.decide() 的信号融合部分添加 ────────────────
DECISION_PATCH = """
# Safety Judge 信号融合
if judge_result.available:
    if judge_result.label == 1:   # injection
        risk_score += settings.w_safety_judge * judge_result.confidence
        triggered_signals.append(
            f"safety_judge:injection({judge_result.confidence:.2f})"
        )
    elif judge_result.label == 2:  # harmful
        risk_score += settings.w_safety_judge * 0.7 * judge_result.confidence
        triggered_signals.append(
            f"safety_judge:harmful({judge_result.confidence:.2f})"
        )
"""

# ── 步骤 4：在 config.py 的 Settings 类中添加 ────────────────────────────
CONFIG_PATCH = """
# Safety Judge 配置
safety_judge_enabled: bool = Field(True, env="SAFETY_JUDGE_ENABLED")
safety_judge_model_path: str = Field(
    "./safety_judge/model", env="SAFETY_JUDGE_MODEL_PATH"
)
w_safety_judge: float = Field(0.35, env="W_SAFETY_JUDGE")
"""

# ── 步骤 5：在 .env 文件中添加 ───────────────────────────────────────────
ENV_PATCH = """
# Safety Judge
SAFETY_JUDGE_ENABLED=true
SAFETY_JUDGE_MODEL_PATH=./safety_judge/model
W_SAFETY_JUDGE=0.35
"""

if __name__ == "__main__":
    print("=" * 60)
    print("RefusalGuard Safety Judge 集成补丁")
    print("=" * 60)
    print("\n[1] 在 detector.py 顶部添加：")
    print(IMPORT_PATCH)
    print("\n[2] 在 detect() 方法中添加（DeBERTa 检测之后）：")
    print(DETECT_PATCH)
    print("\n[3] 在 DecisionEngine.decide() 中添加：")
    print(DECISION_PATCH)
    print("\n[4] 在 config.py Settings 类中添加：")
    print(CONFIG_PATCH)
    print("\n[5] 在 .env 文件中添加：")
    print(ENV_PATCH)
