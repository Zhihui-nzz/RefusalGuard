"""
RefusalGuard 系统级评测脚本 v1.0
基于 safety_judge/data/test.jsonl 对运行中的 RefusalGuard 服务进行端到端评测。

数据集标签说明：
  0 = benign（正常请求，系统应 PASS 或 MONITOR）
  1 = injection（提示注入/越狱，系统应 BLOCK 或 WARN）
  2 = harmful（有害内容，系统应 BLOCK 或 WARN）

运行方式：
  # 评测全量 1006 条（约 10~20 分钟）
  python refusalguard_eval/evaluate_testset.py

  # 快速评测（随机抽样 200 条，约 2~4 分钟）
  python refusalguard_eval/evaluate_testset.py --sample 200

  # 指定服务地址和数据集路径
  python refusalguard_eval/evaluate_testset.py \
      --url http://localhost:8000 \
      --data safety_judge/data/test.jsonl \
      --output testset_eval_report.json
"""

import argparse
import json
import random
import sys
import time
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

import requests
from loguru import logger

# ── 配置 ─────────────────────────────────────────────────────────────────────
DEFAULT_URL      = "http://localhost:8000"
DEFAULT_DATA     = "safety_judge/data/test.jsonl"
DEFAULT_OUTPUT   = "testset_eval_report.json"
REQUEST_TIMEOUT  = 30
MAX_RETRIES      = 3
RETRY_DELAY      = 2.0

# 系统决策 → 风险等级映射
DECISION_RISK = {
    "BLOCK":   "high",    # 高风险
    "WARN":    "medium",  # 中风险
    "MONITOR": "low",     # 低风险
    "PASS":    "safe",    # 安全
}

# 标签 → 预期决策集合（宽松匹配）
LABEL_EXPECTED = {
    0: {"PASS", "MONITOR"},           # benign：应放行
    1: {"BLOCK", "WARN"},             # injection：应拦截
    2: {"BLOCK", "WARN"},             # harmful：应拦截
}

LABEL_NAMES = {0: "benign", 1: "injection", 2: "harmful"}


# ── 数据结构 ──────────────────────────────────────────────────────────────────
@dataclass
class CaseResult:
    idx:               int
    text_preview:      str           # 前 80 字符
    label:             int           # 真实标签
    label_name:        str
    source:            str
    actual_decision:   str
    risk_score:        float
    injection_score:   float
    intent_score:      float
    benign_discount:   float
    detection_path:    str
    triggered_signals: list
    judge_label:       int           # -1=未触发, 0=benign, 1=injection, 2=harmful
    judge_confidence:  float
    latency_ms:        float
    passed:            bool          # 决策是否符合预期
    error:             str


@dataclass
class EvalReport:
    timestamp:          str
    service_url:        str
    data_path:          str
    total_cases:        int
    evaluated_cases:    int
    error_cases:        int

    # 混淆矩阵（行=真实标签, 列=系统决策）
    confusion:          dict         # {label_name: {decision: count}}

    # 按标签的详细指标
    per_label_metrics:  dict

    # 整体指标
    overall_metrics:    dict

    # 按数据来源的指标
    per_source_metrics: dict

    # 延迟统计
    latency_stats:      dict

    # Safety Judge 统计
    judge_stats:        dict

    # 失败案例（用于错误分析）
    false_positives:    list         # benign 被误拦截的案例
    false_negatives:    list         # injection/harmful 被漏过的案例

    # 所有案例详情（可选，用 --save_cases 开启）
    all_cases:          list = field(default_factory=list)


# ── HTTP 工具 ─────────────────────────────────────────────────────────────────
def detect_single(
    url: str,
    text: str,
    user_id: str = "eval_user",
    retries: int = MAX_RETRIES,
) -> Optional[dict]:
    """向 /api/v1/detect 发送单条请求，带重试逻辑"""
    payload = {"prompt": text, "user_id": user_id}
    for attempt in range(retries):
        try:
            resp = requests.post(
                f"{url}/api/v1/detect",
                json=payload,
                timeout=REQUEST_TIMEOUT,
            )
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.ConnectionError as e:
            if attempt < retries - 1:
                time.sleep(RETRY_DELAY)
                continue
            return None
        except requests.exceptions.HTTPError as e:
            if resp.status_code == 500 and attempt < retries - 1:
                time.sleep(RETRY_DELAY)
                continue
            return None
        except Exception:
            return None
    return None


# ── 指标计算 ──────────────────────────────────────────────────────────────────
def compute_metrics(results: list[CaseResult]) -> dict:
    """
    计算系统级分类指标：
    - 对于 injection/harmful（正类）：计算 Precision、Recall、F1
    - 对于 benign（负类）：计算误报率（FPR）和特异性（Specificity）
    """
    # 将系统决策映射为二分类：BLOCK/WARN = 1（拦截），MONITOR/PASS = 0（放行）
    tp = fp = tn = fn = 0
    for r in results:
        if r.error:
            continue
        predicted_positive = r.actual_decision in ("BLOCK", "WARN")
        actually_positive  = r.label in (1, 2)

        if predicted_positive and actually_positive:
            tp += 1
        elif predicted_positive and not actually_positive:
            fp += 1
        elif not predicted_positive and actually_positive:
            fn += 1
        else:
            tn += 1

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall    = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1        = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
    fpr       = fp / (fp + tn) if (fp + tn) > 0 else 0.0   # 误报率
    specificity = tn / (tn + fp) if (tn + fp) > 0 else 0.0  # 特异性（正常请求放行率）
    accuracy  = (tp + tn) / (tp + fp + tn + fn) if (tp + fp + tn + fn) > 0 else 0.0

    return {
        "tp": tp, "fp": fp, "tn": tn, "fn": fn,
        "precision":   round(precision, 4),
        "recall":      round(recall, 4),
        "f1":          round(f1, 4),
        "accuracy":    round(accuracy, 4),
        "false_positive_rate":  round(fpr, 4),       # 误报率（越低越好）
        "specificity":          round(specificity, 4), # 正常请求放行率（越高越好）
    }


def compute_per_label_metrics(results: list[CaseResult]) -> dict:
    """按标签计算各类别的通过率和决策分布"""
    per_label = defaultdict(lambda: defaultdict(int))
    for r in results:
        if r.error:
            continue
        per_label[r.label_name][r.actual_decision] += 1

    metrics = {}
    for label_name, decisions in per_label.items():
        total = sum(decisions.values())
        expected = LABEL_EXPECTED[
            next(k for k, v in LABEL_NAMES.items() if v == label_name)
        ]
        passed = sum(v for k, v in decisions.items() if k in expected)
        metrics[label_name] = {
            "total":          total,
            "pass_rate":      round(passed / total, 4) if total > 0 else 0.0,
            "decision_dist":  dict(decisions),
        }
    return metrics


def compute_per_source_metrics(results: list[CaseResult]) -> dict:
    """按数据来源计算准确率"""
    per_source = defaultdict(list)
    for r in results:
        if not r.error:
            per_source[r.source].append(r.passed)

    return {
        src: {
            "total":     len(vals),
            "pass_rate": round(sum(vals) / len(vals), 4) if vals else 0.0,
        }
        for src, vals in per_source.items()
    }


def compute_latency_stats(results: list[CaseResult]) -> dict:
    """计算延迟统计"""
    latencies = [r.latency_ms for r in results if not r.error and r.latency_ms > 0]
    if not latencies:
        return {}
    latencies.sort()
    n = len(latencies)
    return {
        "count":     n,
        "mean_ms":   round(sum(latencies) / n, 1),
        "median_ms": round(latencies[n // 2], 1),
        "p95_ms":    round(latencies[int(n * 0.95)], 1),
        "p99_ms":    round(latencies[int(n * 0.99)], 1),
        "min_ms":    round(latencies[0], 1),
        "max_ms":    round(latencies[-1], 1),
    }


def compute_judge_stats(results: list[CaseResult]) -> dict:
    """统计 Safety Judge 的触发情况"""
    attack_cases = [r for r in results if r.label in (1, 2) and not r.error]
    benign_cases = [r for r in results if r.label == 0 and not r.error]

    judge_fired_attack  = sum(1 for r in attack_cases if r.judge_label in (1, 2))
    judge_fired_benign  = sum(1 for r in benign_cases if r.judge_label in (1, 2))
    judge_benign_veto   = sum(1 for r in benign_cases if r.judge_label == 0 and r.judge_confidence > 0.5)

    all_confidences = [r.judge_confidence for r in results if r.judge_label != -1 and not r.error]

    return {
        "attack_cases":            len(attack_cases),
        "benign_cases":            len(benign_cases),
        "judge_fired_on_attack":   judge_fired_attack,
        "judge_fired_on_benign":   judge_fired_benign,   # 误触发（judge 认为正常请求是攻击）
        "judge_benign_veto_count": judge_benign_veto,    # judge 认为是正常请求的次数
        "judge_fire_rate_attack":  round(judge_fired_attack / len(attack_cases), 4) if attack_cases else 0.0,
        "judge_fp_rate":           round(judge_fired_benign / len(benign_cases), 4) if benign_cases else 0.0,
        "judge_avg_confidence":    round(sum(all_confidences) / len(all_confidences), 4) if all_confidences else 0.0,
    }


# ── 主评测逻辑 ────────────────────────────────────────────────────────────────
def run_evaluation(
    url: str,
    data_path: str,
    output_path: str,
    sample: Optional[int] = None,
    save_cases: bool = False,
    seed: int = 42,
) -> EvalReport:
    # 加载数据集
    data_file = Path(data_path)
    if not data_file.exists():
        logger.error(f"数据集文件不存在: {data_path}")
        sys.exit(1)

    cases = []
    with open(data_file, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                cases.append(json.loads(line))

    logger.info(f"数据集加载完成：共 {len(cases)} 条")

    # 随机抽样
    if sample and sample < len(cases):
        random.seed(seed)
        cases = random.sample(cases, sample)
        logger.info(f"随机抽样 {sample} 条进行评测")

    # 检查服务可用性
    try:
        resp = requests.get(f"{url}/api/v1/health", timeout=5)
        resp.raise_for_status()
        logger.info(f"服务健康检查通过：{url}")
    except Exception as e:
        logger.warning(f"健康检查失败（{e}），继续尝试评测……")

    # 逐条评测
    results: list[CaseResult] = []
    total = len(cases)
    error_count = 0

    logger.info(f"开始评测，共 {total} 条……")
    start_total = time.time()

    for idx, case in enumerate(cases):
        text   = case["text"]
        label  = case["label"]
        source = case.get("source", "unknown")

        # 进度提示（每 50 条打印一次）
        if idx % 50 == 0:
            elapsed = time.time() - start_total
            eta = elapsed / (idx + 1) * (total - idx - 1) if idx > 0 else 0
            logger.info(
                f"进度: {idx+1}/{total} | "
                f"已用时: {elapsed:.0f}s | "
                f"预计剩余: {eta:.0f}s"
            )

        t0 = time.time()
        resp_data = detect_single(url, text, user_id=f"eval_{idx}")
        latency_ms = (time.time() - t0) * 1000

        if resp_data is None:
            error_count += 1
            results.append(CaseResult(
                idx=idx,
                text_preview=text[:80],
                label=label,
                label_name=LABEL_NAMES.get(label, str(label)),
                source=source,
                actual_decision="ERROR",
                risk_score=0.0,
                injection_score=0.0,
                intent_score=0.0,
                benign_discount=0.0,
                detection_path="",
                triggered_signals=[],
                judge_label=-1,
                judge_confidence=0.0,
                latency_ms=latency_ms,
                passed=False,
                error="请求失败（重试后仍无响应）",
            ))
            continue

        # 解析响应
        decision        = resp_data.get("decision", "ERROR")
        risk_score      = resp_data.get("risk_score", 0.0)
        breakdown       = resp_data.get("breakdown", {})
        injection_score = breakdown.get("injection_score", 0.0)
        intent_score    = resp_data.get("intent_score", 0.0)
        benign_discount = resp_data.get("benign_discount", 0.0)
        detection_path  = resp_data.get("detection_path", "")
        signals         = resp_data.get("triggered_signals", [])

        # 解析 Safety Judge 信号
        judge_label = -1
        judge_confidence = 0.0
        for sig in signals:
            if sig.startswith("judge_injection("):
                judge_label = 1
                try:
                    judge_confidence = float(sig.split("(")[1].rstrip(")"))
                except Exception:
                    pass
            elif sig.startswith("judge_harmful("):
                judge_label = 2
                try:
                    judge_confidence = float(sig.split("(")[1].rstrip(")"))
                except Exception:
                    pass
            elif sig.startswith("judge_benign("):
                judge_label = 0
                try:
                    judge_confidence = float(sig.split("(")[1].rstrip(")"))
                except Exception:
                    pass

        # 判断是否通过
        expected = LABEL_EXPECTED.get(label, set())
        passed   = decision in expected

        results.append(CaseResult(
            idx=idx,
            text_preview=text[:80],
            label=label,
            label_name=LABEL_NAMES.get(label, str(label)),
            source=source,
            actual_decision=decision,
            risk_score=risk_score,
            injection_score=injection_score,
            intent_score=intent_score,
            benign_discount=benign_discount,
            detection_path=detection_path,
            triggered_signals=signals,
            judge_label=judge_label,
            judge_confidence=judge_confidence,
            latency_ms=round(latency_ms, 1),
            passed=passed,
            error="",
        ))

    elapsed_total = time.time() - start_total
    logger.info(f"评测完成！总耗时: {elapsed_total:.1f}s，错误: {error_count} 条")

    # ── 计算各项指标 ──────────────────────────────────────────────────────
    valid_results = [r for r in results if not r.error]

    overall_metrics    = compute_metrics(valid_results)
    per_label_metrics  = compute_per_label_metrics(valid_results)
    per_source_metrics = compute_per_source_metrics(valid_results)
    latency_stats      = compute_latency_stats(valid_results)
    judge_stats        = compute_judge_stats(valid_results)

    # 混淆矩阵
    confusion = defaultdict(lambda: defaultdict(int))
    for r in valid_results:
        confusion[r.label_name][r.actual_decision] += 1
    confusion = {k: dict(v) for k, v in confusion.items()}

    # 收集失败案例（用于错误分析）
    false_positives = [
        {
            "text":           r.text_preview,
            "source":         r.source,
            "actual_decision": r.actual_decision,
            "risk_score":     r.risk_score,
            "injection_score": r.injection_score,
            "intent_score":   r.intent_score,
            "benign_discount": r.benign_discount,
            "detection_path": r.detection_path,
            "triggered_signals": r.triggered_signals,
        }
        for r in valid_results
        if r.label == 0 and not r.passed
    ]

    false_negatives = [
        {
            "text":           r.text_preview,
            "label_name":     r.label_name,
            "source":         r.source,
            "actual_decision": r.actual_decision,
            "risk_score":     r.risk_score,
            "injection_score": r.injection_score,
            "detection_path": r.detection_path,
        }
        for r in valid_results
        if r.label in (1, 2) and not r.passed
    ]

    # 构建报告
    from datetime import datetime
    report = EvalReport(
        timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        service_url=url,
        data_path=str(data_path),
        total_cases=total,
        evaluated_cases=len(valid_results),
        error_cases=error_count,
        confusion=confusion,
        per_label_metrics=per_label_metrics,
        overall_metrics=overall_metrics,
        per_source_metrics=per_source_metrics,
        latency_stats=latency_stats,
        judge_stats=judge_stats,
        false_positives=false_positives[:30],   # 最多保存 30 条
        false_negatives=false_negatives[:30],
        all_cases=[asdict(r) for r in results] if save_cases else [],
    )

    # 保存报告
    output_file = Path(output_path)
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(asdict(report), f, ensure_ascii=False, indent=2)
    logger.info(f"报告已保存至: {output_file.resolve()}")

    return report


def print_summary(report: EvalReport):
    """在终端打印简洁的评测摘要"""
    m = report.overall_metrics
    print("\n" + "═" * 65)
    print("  RefusalGuard 系统级评测结果（基于 test.jsonl）")
    print("═" * 65)
    print(f"  评测时间:   {report.timestamp}")
    print(f"  数据集:     {report.data_path}")
    print(f"  总样本数:   {report.total_cases}  |  有效: {report.evaluated_cases}  |  错误: {report.error_cases}")
    print()
    print("  ── 整体指标 ──────────────────────────────────────────────")
    print(f"  准确率 (Accuracy):    {m['accuracy']:.4f}  ({m['accuracy']*100:.1f}%)")
    print(f"  精确率 (Precision):   {m['precision']:.4f}  （拦截的请求中真实攻击的比例）")
    print(f"  召回率 (Recall):      {m['recall']:.4f}  （攻击被成功拦截的比例）")
    print(f"  F1 分数:              {m['f1']:.4f}")
    print(f"  误报率 (FPR):         {m['false_positive_rate']:.4f}  （正常请求被误拦截的比例）")
    print(f"  特异性 (Specificity): {m['specificity']:.4f}  （正常请求被正确放行的比例）")
    print(f"  混淆矩阵:  TP={m['tp']}  FP={m['fp']}  TN={m['tn']}  FN={m['fn']}")
    print()
    print("  ── 按类别指标 ────────────────────────────────────────────")
    for label_name, lm in report.per_label_metrics.items():
        print(f"  [{label_name:10s}]  总数={lm['total']:4d}  通过率={lm['pass_rate']:.4f}  "
              f"决策分布: {lm['decision_dist']}")
    print()
    print("  ── 延迟统计 ──────────────────────────────────────────────")
    ls = report.latency_stats
    if ls:
        print(f"  均值={ls['mean_ms']}ms  中位={ls['median_ms']}ms  "
              f"P95={ls['p95_ms']}ms  P99={ls['p99_ms']}ms")
    print()
    print("  ── Safety Judge 统计 ─────────────────────────────────────")
    js = report.judge_stats
    print(f"  攻击样本中 Judge 触发率: {js['judge_fire_rate_attack']:.4f}")
    print(f"  正常样本中 Judge 误触发率: {js['judge_fp_rate']:.4f}")
    print(f"  正常样本中 Judge 识别为 benign 次数: {js['judge_benign_veto_count']}")
    print()
    print(f"  ── 误报案例（前 5 条）────────────────────────────────────")
    for fp_case in report.false_positives[:5]:
        print(f"  [{fp_case['actual_decision']}] risk={fp_case['risk_score']:.3f} "
              f"inj={fp_case['injection_score']:.3f} "
              f"path={fp_case['detection_path']}")
        print(f"       文本: {fp_case['text'][:70]}...")
    print()
    print(f"  详细报告已保存至 JSON 文件，可用 report_viewer.py 生成 Markdown 报告")
    print("═" * 65 + "\n")


# ── 入口 ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="RefusalGuard 系统级评测（基于 test.jsonl）")
    parser.add_argument("--url",        default=DEFAULT_URL,    help="服务地址")
    parser.add_argument("--data",       default=DEFAULT_DATA,   help="test.jsonl 路径")
    parser.add_argument("--output",     default=DEFAULT_OUTPUT, help="报告输出路径")
    parser.add_argument("--sample",     type=int, default=None, help="随机抽样条数（不指定则全量）")
    parser.add_argument("--save_cases", action="store_true",    help="是否在报告中保存所有案例详情")
    parser.add_argument("--seed",       type=int, default=42,   help="随机种子")
    args = parser.parse_args()

    report = run_evaluation(
        url=args.url,
        data_path=args.data,
        output_path=args.output,
        sample=args.sample,
        save_cases=args.save_cases,
        seed=args.seed,
    )
    print_summary(report)
