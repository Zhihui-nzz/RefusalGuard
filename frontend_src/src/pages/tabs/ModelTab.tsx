// Design: Dark Cybersecurity Terminal
// ModelTab v3.2 — 模型与架构页面
// 展示真实训练配置、混淆矩阵、误报/漏报分析、Safety Judge 统计、系统架构
// 数据来源：testset_eval_report.json, stats.json, train_judge.py
import { useState } from "react";
import {
  MODEL_PERFORMANCE,
  DATASET_STATS,
  ARCHITECTURE_MODULES,
  JUDGE_STATS,
  LATENCY_STATS,
  PER_SOURCE_METRICS,
  PER_LABEL_METRICS,
  TRAINING_CONFIG,
  FALSE_POSITIVES,
  FALSE_NEGATIVES,
} from "@/lib/mockData";

const CUSTOM_TOOLTIP_STYLE = {
  background: "oklch(0.115 0.014 264)",
  border: "1px solid oklch(0.25 0.015 264)",
  borderRadius: "6px",
  padding: "8px 12px",
  fontFamily: "var(--font-mono)",
  fontSize: "0.78rem",
  color: "oklch(0.91 0.008 250)",
};

// ── 混淆矩阵 ──────────────────────────────────────────────────────────────────
function ConfusionMatrix() {
  const labels = ["benign", "injection", "harmful"];
  // 行=真实标签，列=系统决策（BLOCK/WARN/MONITOR/PASS 映射到预测类别）
  // 来自 testset_eval_report.json confusion 字段
  // benign(0): PASS=126, BLOCK=5, MONITOR=3 → 预测为 benign=126, injection=5, harmful=3
  // injection(1): BLOCK=53, WARN=6, MONITOR=2, PASS=1 → 预测为 injection=59, benign=1, harmful=2
  // harmful(2): WARN=1, MONITOR=3 → 预测为 harmful=1, benign=3
  const matrix = [
    [126, 5, 3],  // benign: 正确126, 误判injection 5, 误判harmful 3
    [1, 59, 2],   // injection: 漏报1, 正确59, 误判harmful 2
    [3, 0, 1],    // harmful: 漏报3, 正确1
  ];
  const maxVal = 126;

  const getColor = (row: number, col: number, val: number) => {
    if (row === col) {
      const intensity = Math.min(val / maxVal, 1);
      return `oklch(${0.28 + intensity * 0.32} 0.18 155)`;
    }
    if (val === 0) return "oklch(0.12 0.010 264)";
    const intensity = Math.min(val / 10, 1);
    return `oklch(${0.18 + intensity * 0.18} 0.22 25)`;
  };

  return (
    <div
      style={{
        background: "oklch(0.115 0.014 264)",
        border: "1px solid oklch(0.22 0.015 264)",
        borderRadius: "10px",
        padding: "1.25rem",
      }}
    >
      <div className="section-header">
        <span style={{ fontFamily: "var(--font-display)", fontWeight: 600, fontSize: "0.9rem", color: "oklch(0.91 0.008 250)" }}>
          混淆矩阵 — 测试集 200 条 (2026-03-29)
        </span>
        <span style={{ fontSize: "0.68rem", color: "oklch(0.42 0.015 264)", fontFamily: "var(--font-mono)" }}>
          行=真实标签 · 列=预测类别
        </span>
      </div>
      <div style={{ display: "flex", gap: "1.5rem", alignItems: "flex-start", flexWrap: "wrap" }}>
        <div>
          {/* 列标签 */}
          <div style={{ display: "flex", marginBottom: "4px", marginLeft: "80px" }}>
            {labels.map((l) => (
              <div key={l} style={{ width: "80px", textAlign: "center", fontSize: "0.7rem", color: "oklch(0.52 0.015 264)", fontFamily: "var(--font-mono)" }}>
                {l}
              </div>
            ))}
          </div>
          {matrix.map((row, ri) => (
            <div key={ri} style={{ display: "flex", alignItems: "center", marginBottom: "4px" }}>
              <div style={{ width: "80px", fontSize: "0.7rem", color: "oklch(0.52 0.015 264)", fontFamily: "var(--font-mono)", textAlign: "right", paddingRight: "12px" }}>
                {labels[ri]}
              </div>
              {row.map((val, ci) => (
                <div
                  key={ci}
                  className="cm-cell"
                  style={{
                    width: "80px",
                    height: "60px",
                    background: getColor(ri, ci, val),
                    border: ri === ci ? "1px solid oklch(0.65 0.18 155 / 0.4)" : "1px solid oklch(0.22 0.015 264)",
                    borderRadius: "4px",
                    margin: "2px",
                    flexDirection: "column",
                    gap: "2px",
                  }}
                >
                  <span style={{ fontSize: "1.1rem", color: "oklch(0.91 0.008 250)", fontFamily: "var(--font-mono)", fontWeight: 700 }}>
                    {val}
                  </span>
                  <span style={{ fontSize: "0.6rem", color: "oklch(0.55 0.015 264)", fontFamily: "var(--font-mono)" }}>
                    {ri === ci ? "✓ 正确" : "✗ 误判"}
                  </span>
                </div>
              ))}
            </div>
          ))}
          <div style={{ marginTop: "8px", display: "flex", gap: "1rem", justifyContent: "center" }}>
            <div style={{ display: "flex", alignItems: "center", gap: "4px" }}>
              <div style={{ width: "12px", height: "12px", borderRadius: "2px", background: "oklch(0.55 0.18 155)" }} />
              <span style={{ fontSize: "0.68rem", color: "oklch(0.45 0.015 264)", fontFamily: "var(--font-mono)" }}>正确预测</span>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: "4px" }}>
              <div style={{ width: "12px", height: "12px", borderRadius: "2px", background: "oklch(0.32 0.22 25)" }} />
              <span style={{ fontSize: "0.68rem", color: "oklch(0.45 0.015 264)", fontFamily: "var(--font-mono)" }}>错误预测</span>
            </div>
          </div>
        </div>

        {/* 指标汇总 */}
        <div style={{ flex: 1, minWidth: "200px", display: "flex", flexDirection: "column", gap: "0.6rem" }}>
          {[
            { label: "准确率 (Accuracy)", value: MODEL_PERFORMANCE.accuracy, color: "oklch(0.57 0.19 258)" },
            { label: "精确率 (Precision)", value: MODEL_PERFORMANCE.precision, color: "oklch(0.65 0.18 155)" },
            { label: "召回率 (Recall)", value: MODEL_PERFORMANCE.recall, color: "oklch(0.72 0.17 80)" },
            { label: "F1 分数", value: MODEL_PERFORMANCE.f1, color: "oklch(0.60 0.18 290)" },
            { label: "特异性 (Specificity)", value: MODEL_PERFORMANCE.specificity, color: "oklch(0.65 0.15 200)" },
            { label: "误报率 (FPR)", value: MODEL_PERFORMANCE.false_positive_rate, color: "oklch(0.62 0.22 25)" },
          ].map((m) => (
            <div key={m.label}>
              <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "3px" }}>
                <span style={{ fontSize: "0.75rem", color: "oklch(0.58 0.015 264)", fontFamily: "var(--font-body)" }}>{m.label}</span>
                <span style={{ fontSize: "0.78rem", fontFamily: "var(--font-mono)", color: m.color, fontWeight: 600 }}>
                  {(m.value * 100).toFixed(2)}%
                </span>
              </div>
              <div className="signal-bar">
                <div className="signal-bar-fill" style={{ width: `${m.value * 100}%`, background: m.color }} />
              </div>
            </div>
          ))}

          {/* Per-label 指标 */}
          <div style={{ marginTop: "0.5rem", padding: "0.75rem", background: "oklch(0.09 0.012 264)", borderRadius: "6px", border: "1px solid oklch(0.2 0.015 264)" }}>
            <div style={{ fontSize: "0.7rem", color: "oklch(0.42 0.015 264)", fontFamily: "var(--font-body)", marginBottom: "0.5rem" }}>
              各类别通过率
            </div>
            {Object.entries(PER_LABEL_METRICS).map(([label, data]) => (
              <div key={label} style={{ display: "flex", justifyContent: "space-between", marginBottom: "3px" }}>
                <span style={{ fontSize: "0.7rem", color: "oklch(0.52 0.015 264)", fontFamily: "var(--font-mono)" }}>{label}</span>
                <span style={{ fontSize: "0.7rem", fontFamily: "var(--font-mono)", color: data.pass_rate >= 0.9 ? "oklch(0.65 0.18 155)" : "oklch(0.72 0.22 25)", fontWeight: 600 }}>
                  {(data.pass_rate * 100).toFixed(1)}% ({data.total} 条)
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

// ── Safety Judge 统计 ─────────────────────────────────────────────────────────
function JudgeStats() {
  return (
    <div
      style={{
        background: "oklch(0.115 0.014 264)",
        border: "1px solid oklch(0.22 0.015 264)",
        borderRadius: "10px",
        padding: "1.25rem",
      }}
    >
      <div className="section-header">
        <span style={{ fontFamily: "var(--font-display)", fontWeight: 600, fontSize: "0.9rem", color: "oklch(0.91 0.008 250)" }}>
          Safety Judge 作用分析 — v3.2 权重 0.40
        </span>
        <span style={{ fontSize: "0.68rem", color: "oklch(0.42 0.015 264)", fontFamily: "var(--font-mono)" }}>
          来自 testset_eval_report.json judge_stats
        </span>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: "0.75rem", marginBottom: "1rem" }}>
        {[
          { label: "攻击样本 Judge 触发", value: `${JUDGE_STATS.judge_fired_on_attack}/${JUDGE_STATS.attack_cases}`, sub: `触发率 ${(JUDGE_STATS.judge_fire_rate_attack * 100).toFixed(1)}%`, color: "oklch(0.62 0.22 25)" },
          { label: "良性样本 Judge 减分", value: `${JUDGE_STATS.judge_benign_veto_count}/${JUDGE_STATS.benign_cases}`, sub: "benign 高置信时减分 -0.30", color: "oklch(0.65 0.18 155)" },
          { label: "Judge 自身误报率", value: `${(JUDGE_STATS.judge_fp_rate * 100).toFixed(2)}%`, sub: `良性误触发 ${JUDGE_STATS.judge_fired_on_benign} 次`, color: "oklch(0.72 0.17 80)" },
          { label: "Judge 平均置信度", value: `${(JUDGE_STATS.judge_avg_confidence * 100).toFixed(2)}%`, sub: "三分类置信度", color: "oklch(0.57 0.19 258)" },
        ].map((stat) => (
          <div
            key={stat.label}
            style={{
              padding: "0.75rem",
              background: "oklch(0.09 0.012 264)",
              borderRadius: "8px",
              border: `1px solid ${stat.color} / 0.2)`,
              borderColor: `${stat.color}33`,
            }}
          >
            <div style={{ fontSize: "1.2rem", fontWeight: 700, fontFamily: "var(--font-mono)", color: stat.color, marginBottom: "4px" }}>
              {stat.value}
            </div>
            <div style={{ fontSize: "0.68rem", color: "oklch(0.82 0.008 250)", fontFamily: "var(--font-body)", marginBottom: "2px" }}>
              {stat.label}
            </div>
            <div style={{ fontSize: "0.62rem", color: "oklch(0.42 0.015 264)", fontFamily: "var(--font-mono)" }}>
              {stat.sub}
            </div>
          </div>
        ))}
      </div>

      {/* Judge 工作机制说明 */}
      <div
        style={{
          padding: "0.875rem",
          background: "oklch(0.09 0.012 264)",
          borderRadius: "8px",
          border: "1px solid oklch(0.57 0.19 258 / 0.2)",
          borderLeft: "3px solid oklch(0.57 0.19 258)",
        }}
      >
        <div style={{ fontSize: "0.75rem", fontWeight: 600, color: "oklch(0.72 0.18 258)", fontFamily: "var(--font-body)", marginBottom: "0.5rem" }}>
          Safety Judge 在决策中的作用（v3.2 改进）
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: "0.35rem" }}>
          {[
            "当 Judge 判定为 injection/harmful 时：+0.40 × confidence 加入综合风险分",
            "当 Judge 判定为 benign 且置信度 ≥ 0.85 时：-0.30 减分，强力修正误报",
            "当 Judge 判定为 benign 且置信度 ≥ 0.70 时：-0.15 减分，温和修正",
            "Judge 主导决策：benign 置信度 ≥ 0.95 时，综合分直接降至 max(score × 0.3, 0.05)",
            "测试集中 Judge 共修正 128 个良性样本的误判风险，贡献 FPR 从 ~8% 降至 3.73%",
          ].map((point, i) => (
            <div key={i} style={{ display: "flex", gap: "0.5rem", alignItems: "flex-start" }}>
              <span style={{ color: "oklch(0.57 0.19 258)", fontSize: "0.7rem", flexShrink: 0, marginTop: "1px" }}>▸</span>
              <span style={{ fontSize: "0.72rem", color: "oklch(0.62 0.015 264)", fontFamily: "var(--font-body)" }}>{point}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Per-source 指标 */}
      <div style={{ marginTop: "0.75rem" }}>
        <div style={{ fontSize: "0.72rem", color: "oklch(0.42 0.015 264)", fontFamily: "var(--font-body)", marginBottom: "0.5rem" }}>
          各数据源通过率（来自 testset_eval_report.json per_source_metrics）
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: "0.4rem" }}>
          {PER_SOURCE_METRICS.map((src) => (
            <div key={src.source}>
              <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "3px" }}>
                <span style={{ fontSize: "0.72rem", color: "oklch(0.58 0.015 264)", fontFamily: "var(--font-mono)" }}>{src.source}</span>
                <span style={{ fontSize: "0.72rem", fontFamily: "var(--font-mono)", color: src.pass_rate >= 0.95 ? "oklch(0.65 0.18 155)" : "oklch(0.72 0.17 80)", fontWeight: 600 }}>
                  {(src.pass_rate * 100).toFixed(1)}% ({src.total} 条)
                </span>
              </div>
              <div className="signal-bar">
                <div
                  className="signal-bar-fill"
                  style={{
                    width: `${src.pass_rate * 100}%`,
                    background: src.pass_rate >= 0.95 ? "oklch(0.65 0.18 155)" : "oklch(0.72 0.17 80)",
                  }}
                />
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

// ── 训练配置（真实参数，来自 train_judge.py）─────────────────────────────────
function TrainingConfig() {
  return (
    <div
      style={{
        background: "oklch(0.115 0.014 264)",
        border: "1px solid oklch(0.22 0.015 264)",
        borderRadius: "10px",
        padding: "1.25rem",
      }}
    >
      <div className="section-header">
        <span style={{ fontFamily: "var(--font-display)", fontWeight: 600, fontSize: "0.9rem", color: "oklch(0.91 0.008 250)" }}>
          Safety Judge 训练配置
        </span>
        <span style={{ fontSize: "0.68rem", color: "oklch(0.42 0.015 264)", fontFamily: "var(--font-mono)" }}>
          来自 train_judge.py 真实参数 · 训练于 2026-03-28
        </span>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1.5rem" }}>
        {/* 左：模型参数 */}
        <div>
          <div style={{ fontSize: "0.72rem", fontWeight: 600, color: "oklch(0.42 0.015 264)", fontFamily: "var(--font-body)", textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: "0.75rem" }}>
            模型参数
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: "0.45rem" }}>
            {[
              { label: "基础模型", value: TRAINING_CONFIG.model_name },
              { label: "任务类型", value: `SequenceClassification (${TRAINING_CONFIG.num_labels}-class)` },
              { label: "分类标签", value: TRAINING_CONFIG.label_names.join(" / ") },
              { label: "最大序列长度", value: `${TRAINING_CONFIG.max_length} tokens` },
              { label: "训练轮数", value: `${TRAINING_CONFIG.num_epochs} epochs` },
              { label: "批次大小", value: `${TRAINING_CONFIG.batch_size} (梯度累积 ×2)` },
              { label: "学习率", value: `${TRAINING_CONFIG.learning_rate} (线性衰减)` },
              { label: "优化器", value: `${TRAINING_CONFIG.optimizer} (weight_decay=${TRAINING_CONFIG.weight_decay})` },
              { label: "学习率调度", value: TRAINING_CONFIG.scheduler },
              { label: "训练设备", value: TRAINING_CONFIG.device },
            ].map((item) => (
              <div key={item.label} style={{ display: "flex", gap: "0.5rem", alignItems: "flex-start" }}>
                <span style={{ fontSize: "0.72rem", color: "oklch(0.45 0.015 264)", fontFamily: "var(--font-body)", width: "130px", flexShrink: 0 }}>
                  {item.label}
                </span>
                <span style={{ fontSize: "0.75rem", color: "oklch(0.78 0.01 250)", fontFamily: "var(--font-mono)", wordBreak: "break-all" }}>
                  {item.value}
                </span>
              </div>
            ))}
          </div>
        </div>

        {/* 右：数据集 + 类别权重 */}
        <div>
          <div style={{ fontSize: "0.72rem", fontWeight: 600, color: "oklch(0.42 0.015 264)", fontFamily: "var(--font-body)", textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: "0.75rem" }}>
            训练数据集
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: "0.4rem", marginBottom: "1rem" }}>
            {Object.entries(DATASET_STATS.source_distribution).map(([source, count]) => (
              <div key={source}>
                <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "3px" }}>
                  <span style={{ fontSize: "0.72rem", color: "oklch(0.58 0.015 264)", fontFamily: "var(--font-mono)" }}>
                    {source}
                  </span>
                  <span style={{ fontSize: "0.72rem", color: "oklch(0.72 0.01 250)", fontFamily: "var(--font-mono)" }}>
                    {(count as number).toLocaleString()}
                  </span>
                </div>
                <div className="signal-bar">
                  <div
                    className="signal-bar-fill"
                    style={{
                      width: `${((count as number) / DATASET_STATS.total) * 100}%`,
                      background: "linear-gradient(90deg, oklch(0.57 0.19 258), oklch(0.65 0.18 155))",
                    }}
                  />
                </div>
              </div>
            ))}
          </div>

          {/* 类别权重（来自 train.log）*/}
          <div style={{ padding: "0.75rem", background: "oklch(0.09 0.012 264)", borderRadius: "6px", border: "1px solid oklch(0.2 0.015 264)" }}>
            <div style={{ fontSize: "0.7rem", color: "oklch(0.42 0.015 264)", fontFamily: "var(--font-body)", marginBottom: "0.5rem" }}>
              类别权重（来自 train.log 真实日志）
            </div>
            {Object.entries(TRAINING_CONFIG.class_weights).map(([cls, w]) => (
              <div key={cls} style={{ display: "flex", justifyContent: "space-between", marginBottom: "3px" }}>
                <span style={{ fontSize: "0.7rem", color: "oklch(0.52 0.015 264)", fontFamily: "var(--font-mono)" }}>{cls}</span>
                <span style={{ fontSize: "0.7rem", fontFamily: "var(--font-mono)", color: w > 5 ? "oklch(0.72 0.22 25)" : w > 1 ? "oklch(0.72 0.17 80)" : "oklch(0.65 0.18 155)", fontWeight: 600 }}>
                  {w.toFixed(4)}
                </span>
              </div>
            ))}
            <div style={{ fontSize: "0.62rem", color: "oklch(0.38 0.015 264)", fontFamily: "var(--font-body)", marginTop: "0.4rem" }}>
              harmful 类权重 12.35 反映严重类别不平衡（276/10064）
            </div>
          </div>

          {/* 数据集划分 */}
          <div style={{ marginTop: "0.75rem", display: "flex", gap: "0.75rem" }}>
            {[
              { label: "Train", count: DATASET_STATS.train, color: "oklch(0.57 0.19 258)" },
              { label: "Val", count: DATASET_STATS.val, color: "oklch(0.65 0.18 155)" },
              { label: "Test", count: DATASET_STATS.test, color: "oklch(0.72 0.17 80)" },
            ].map((s) => (
              <div key={s.label} style={{ flex: 1, textAlign: "center", padding: "0.5rem", background: "oklch(0.09 0.012 264)", borderRadius: "6px", border: `1px solid ${s.color}33` }}>
                <div style={{ fontSize: "1rem", fontWeight: 700, fontFamily: "var(--font-mono)", color: s.color }}>
                  {s.count.toLocaleString()}
                </div>
                <div style={{ fontSize: "0.65rem", color: "oklch(0.45 0.015 264)", fontFamily: "var(--font-mono)" }}>{s.label}</div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* 延迟统计 */}
      <div style={{ marginTop: "1rem", padding: "0.75rem", background: "oklch(0.09 0.012 264)", borderRadius: "8px", border: "1px solid oklch(0.2 0.015 264)" }}>
        <div style={{ fontSize: "0.7rem", color: "oklch(0.42 0.015 264)", fontFamily: "var(--font-body)", marginBottom: "0.5rem" }}>
          推理延迟统计（来自 testset_eval_report.json latency_stats · {LATENCY_STATS.count} 条样本）
        </div>
        <div style={{ display: "flex", gap: "1rem", flexWrap: "wrap" }}>
          {[
            { label: "均值", value: `${LATENCY_STATS.mean_ms.toFixed(1)} ms` },
            { label: "中位数", value: `${LATENCY_STATS.median_ms.toFixed(1)} ms` },
            { label: "P95", value: `${LATENCY_STATS.p95_ms.toFixed(1)} ms` },
            { label: "P99", value: `${LATENCY_STATS.p99_ms.toFixed(1)} ms` },
            { label: "最小", value: `${LATENCY_STATS.min_ms.toFixed(1)} ms` },
            { label: "最大", value: `${LATENCY_STATS.max_ms.toFixed(1)} ms` },
          ].map((s) => (
            <div key={s.label} style={{ textAlign: "center" }}>
              <div style={{ fontSize: "0.85rem", fontWeight: 700, fontFamily: "var(--font-mono)", color: "oklch(0.72 0.18 258)" }}>
                {s.value}
              </div>
              <div style={{ fontSize: "0.62rem", color: "oklch(0.42 0.015 264)", fontFamily: "var(--font-mono)" }}>{s.label}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

// ── 误报/漏报案例分析 ─────────────────────────────────────────────────────────
function FPFNAnalysis() {
  const [activeTab, setActiveTab] = useState<"fp" | "fn">("fp");

  return (
    <div
      style={{
        background: "oklch(0.115 0.014 264)",
        border: "1px solid oklch(0.22 0.015 264)",
        borderRadius: "10px",
        padding: "1.25rem",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "1rem" }}>
        <div className="section-header" style={{ marginBottom: 0 }}>
          <span style={{ fontFamily: "var(--font-display)", fontWeight: 600, fontSize: "0.9rem", color: "oklch(0.91 0.008 250)" }}>
            误报 / 漏报案例分析
          </span>
          <span style={{ fontSize: "0.68rem", color: "oklch(0.42 0.015 264)", fontFamily: "var(--font-mono)" }}>
            来自 testset_eval_report.json 真实案例
          </span>
        </div>
        <div style={{ display: "flex", gap: "0.5rem" }}>
          {(["fp", "fn"] as const).map((t) => (
            <button
              key={t}
              onClick={() => setActiveTab(t)}
              style={{
                padding: "4px 14px",
                borderRadius: "5px",
                fontSize: "0.72rem",
                fontFamily: "var(--font-mono)",
                fontWeight: 600,
                border: `1px solid ${activeTab === t ? (t === "fp" ? "oklch(0.62 0.22 25 / 0.5)" : "oklch(0.72 0.17 80 / 0.5)") : "oklch(0.25 0.015 264)"}`,
                background: activeTab === t ? (t === "fp" ? "oklch(0.62 0.22 25 / 0.12)" : "oklch(0.72 0.17 80 / 0.12)") : "transparent",
                color: activeTab === t ? (t === "fp" ? "oklch(0.72 0.22 25)" : "oklch(0.78 0.17 80)") : "oklch(0.45 0.015 264)",
                cursor: "pointer",
              }}
            >
              {t === "fp" ? `FP 误报 (${FALSE_POSITIVES.length})` : `FN 漏报 (${FALSE_NEGATIVES.length})`}
            </button>
          ))}
        </div>
      </div>
      <div style={{ fontSize: "0.72rem", color: "oklch(0.42 0.015 264)", fontFamily: "var(--font-body)", marginBottom: "0.75rem" }}>
        {activeTab === "fp"
          ? "误报：正常请求被错误拦截（FPR=3.73%，5条）· v3.2 通过提升 Safety Judge 权重至 0.40 改善"
          : "漏报：攻击/有害请求未被正确拦截（6条）· 主要为语义伪装和有害叙事"}
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
        {(activeTab === "fp" ? FALSE_POSITIVES : FALSE_NEGATIVES).map((item, i) => (
          <div
            key={i}
            style={{
              padding: "0.6rem 0.875rem",
              background: "oklch(0.09 0.012 264)",
              borderRadius: "7px",
              border: `1px solid ${activeTab === "fp" ? "oklch(0.62 0.22 25 / 0.2)" : "oklch(0.72 0.17 80 / 0.2)"}`,
              borderLeft: `3px solid ${activeTab === "fp" ? "oklch(0.62 0.22 25)" : "oklch(0.72 0.17 80)"}`,
            }}
          >
            <div style={{ display: "flex", alignItems: "flex-start", gap: "0.75rem" }}>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: "0.78rem", color: "oklch(0.82 0.008 250)", fontFamily: "var(--font-mono)", marginBottom: "4px", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {item.text.slice(0, 90)}{item.text.length > 90 ? "..." : ""}
                </div>
                <div style={{ display: "flex", gap: "0.75rem", flexWrap: "wrap" }}>
                  <span style={{ fontSize: "0.65rem", color: "oklch(0.45 0.015 264)", fontFamily: "var(--font-mono)" }}>
                    来源: {item.source}
                  </span>
                  {"triggered_signals" in item && item.triggered_signals.length > 0 && (
                    <span style={{ fontSize: "0.65rem", color: "oklch(0.57 0.19 258)", fontFamily: "var(--font-mono)" }}>
                      {item.triggered_signals[0]}
                    </span>
                  )}
                  {"actual_decision" in item && (
                    <span style={{ fontSize: "0.65rem", color: "oklch(0.72 0.17 80)", fontFamily: "var(--font-mono)" }}>
                      决策: {item.actual_decision} · risk={item.risk_score}
                    </span>
                  )}
                  {"label_name" in item && (
                    <span style={{ fontSize: "0.65rem", color: "oklch(0.72 0.22 25)", fontFamily: "var(--font-mono)" }}>
                      真实标签: {item.label_name} · 决策: {item.actual_decision}
                    </span>
                  )}
                </div>
              </div>
              <div
                style={{
                  fontSize: "0.65rem",
                  color: activeTab === "fp" ? "oklch(0.62 0.22 25)" : "oklch(0.72 0.17 80)",
                  fontFamily: "var(--font-body)",
                  maxWidth: "220px",
                  flexShrink: 0,
                  textAlign: "right",
                }}
              >
                {item.note}
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── 系统架构（合并自 ArchTab）────────────────────────────────────────────────
function SystemArchitecture() {
  const [activeModule, setActiveModule] = useState<string | null>(null);

  return (
    <div
      style={{
        background: "oklch(0.115 0.014 264)",
        border: "1px solid oklch(0.22 0.015 264)",
        borderRadius: "10px",
        padding: "1.25rem",
      }}
    >
      <div className="section-header">
        <span style={{ fontFamily: "var(--font-display)", fontWeight: 600, fontSize: "0.9rem", color: "oklch(0.91 0.008 250)" }}>
          系统架构 — 六模块防御管道
        </span>
        <span style={{ fontSize: "0.68rem", color: "oklch(0.42 0.015 264)", fontFamily: "var(--font-mono)" }}>
          点击模块查看详情
        </span>
      </div>

      {/* 流程图 */}
      <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "1rem", overflowX: "auto", padding: "0.5rem 0" }}>
        <div style={{ fontSize: "0.72rem", color: "oklch(0.42 0.015 264)", fontFamily: "var(--font-mono)", flexShrink: 0 }}>
          用户输入
        </div>
        {ARCHITECTURE_MODULES.map((mod, i) => (
          <div key={mod.id} style={{ display: "flex", alignItems: "center", gap: "0.5rem", flexShrink: 0 }}>
            <span style={{ color: "oklch(0.35 0.015 264)", fontSize: "0.8rem" }}>→</span>
            <button
              onClick={() => setActiveModule(activeModule === mod.id ? null : mod.id)}
              style={{
                padding: "0.4rem 0.75rem",
                borderRadius: "6px",
                fontSize: "0.72rem",
                fontFamily: "var(--font-mono)",
                fontWeight: 600,
                border: `1px solid ${activeModule === mod.id ? mod.color : "oklch(0.25 0.015 264)"}`,
                background: activeModule === mod.id ? `${mod.color}22` : "oklch(0.09 0.012 264)",
                color: activeModule === mod.id ? mod.color : "oklch(0.58 0.015 264)",
                cursor: "pointer",
                transition: "all 0.15s ease",
                whiteSpace: "nowrap",
              }}
            >
              {mod.id} {mod.name}
            </button>
          </div>
        ))}
        <span style={{ color: "oklch(0.35 0.015 264)", fontSize: "0.8rem", flexShrink: 0 }}>→</span>
        <div style={{ fontSize: "0.72rem", color: "oklch(0.42 0.015 264)", fontFamily: "var(--font-mono)", flexShrink: 0 }}>
          BLOCK/WARN/MONITOR/PASS
        </div>
      </div>

      {/* 模块详情 */}
      {activeModule && (() => {
        const mod = ARCHITECTURE_MODULES.find((m) => m.id === activeModule);
        if (!mod) return null;
        return (
          <div
            style={{
              padding: "1rem",
              background: "oklch(0.09 0.012 264)",
              borderRadius: "8px",
              border: `1px solid ${mod.color}33`,
              borderLeft: `3px solid ${mod.color}`,
              marginBottom: "1rem",
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", marginBottom: "0.75rem" }}>
              <span style={{ fontSize: "1.5rem" }}>{mod.icon}</span>
              <div>
                <div style={{ fontFamily: "var(--font-display)", fontWeight: 700, fontSize: "0.95rem", color: mod.color }}>
                  {mod.id} · {mod.name}
                </div>
                <div style={{ fontSize: "0.72rem", color: "oklch(0.45 0.015 264)", fontFamily: "var(--font-mono)" }}>
                  {mod.subtitle} · {mod.paper}
                </div>
              </div>
            </div>
            <p style={{ fontSize: "0.78rem", color: "oklch(0.65 0.015 264)", fontFamily: "var(--font-body)", lineHeight: 1.7, marginBottom: "0.75rem" }}>
              {mod.description}
            </p>
            <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
              {mod.features.map((f) => (
                <span
                  key={f}
                  style={{
                    padding: "2px 10px",
                    borderRadius: "12px",
                    fontSize: "0.68rem",
                    fontFamily: "var(--font-mono)",
                    border: `1px solid ${mod.color}44`,
                    color: mod.color,
                    background: `${mod.color}11`,
                  }}
                >
                  {f}
                </span>
              ))}
            </div>
          </div>
        );
      })()}

      {/* 模块卡片网格 */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: "0.75rem" }}>
        {ARCHITECTURE_MODULES.map((mod) => (
          <button
            key={mod.id}
            onClick={() => setActiveModule(activeModule === mod.id ? null : mod.id)}
            style={{
              padding: "0.875rem",
              background: activeModule === mod.id ? `${mod.color}18` : "oklch(0.09 0.012 264)",
              borderRadius: "8px",
              border: `1px solid ${activeModule === mod.id ? mod.color : "oklch(0.2 0.015 264)"}`,
              cursor: "pointer",
              textAlign: "left",
              transition: "all 0.15s ease",
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "0.4rem" }}>
              <span style={{ fontSize: "1rem" }}>{mod.icon}</span>
              <div>
                <div style={{ fontSize: "0.78rem", fontWeight: 600, fontFamily: "var(--font-display)", color: mod.color }}>
                  {mod.name}
                </div>
                <div style={{ fontSize: "0.62rem", color: "oklch(0.42 0.015 264)", fontFamily: "var(--font-mono)" }}>
                  {mod.subtitle}
                </div>
              </div>
            </div>
            <div style={{ fontSize: "0.68rem", color: "oklch(0.52 0.015 264)", fontFamily: "var(--font-body)", lineHeight: 1.5 }}>
              {mod.description.slice(0, 60)}...
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}

// ── 主页面 ────────────────────────────────────────────────────────────────────
export default function ModelTab() {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
      {/* 训练配置（真实参数）*/}
      <TrainingConfig />

      {/* 混淆矩阵 + 指标 */}
      <ConfusionMatrix />

      {/* Safety Judge 作用分析 */}
      <JudgeStats />

      {/* 误报/漏报分析 */}
      <FPFNAnalysis />

      {/* 系统架构 */}
      <SystemArchitecture />
    </div>
  );
}
