// RefusalGuard Dashboard 数据类型定义

export type Decision = "BLOCK" | "WARN" | "PASS" | "MONITOR";

export interface DetectionBreakdown {
  injection_score: number;
  intent_score: number;
  benign_discount: number;
  kb_confidence: number;
  boundary_state: string;
  boundary_risk_bonus: number;
  probe_score: number;
  entropy_risk_bonus: number;
  rag_injection_score: number;
  drift_score: number;
  drift_direction: string;
  user_trust: number;
  context_risk: number;
  zh_rule_score: number;
}

export interface DetectResponse {
  decision: Decision;
  risk_score: number;
  breakdown: DetectionBreakdown;
  refusal_message: string;
  explanation: string;
  detection_path: string;
  latency_ms: number;
  triggered_signals: string[];
  llm_generated?: boolean;  // v3.2: 拒答消息是否由 LLM 生成
  judge_label?: string;
  judge_confidence?: number;
  judge_scores?: number[];
  knowledge_boundary_triggered?: boolean;
  llm_response?: string;
}

export interface MetricsData {
  total_requests: number;
  block_count: number;
  warn_count: number;
  pass_count: number;
  block_rate: number;
  avg_latency_ms: number;
  uptime_seconds: number;
  probe_triggers: number;
  drift_triggers: number;
  rag_contaminations: number;
}

export interface LogEntry {
  id: string;
  timestamp: string;
  decision: Decision;
  risk_score: number;
  prompt_preview: string;
  detection_path: string;
  latency_ms: number;
  triggered_signals: string[];
}

export interface AttackCase {
  id: string;
  name: string;
  category: string;
  prompt: string;
  description: string;
  expected: Decision;
}

// ── 模型性能数据（来自 testset_eval_report.json）────────────────────────────
export interface ModelPerformance {
  accuracy: number;
  precision: number;
  recall: number;
  f1: number;
  false_positive_rate: number;
  specificity: number;
  tp: number;
  fp: number;
  tn: number;
  fn: number;
}

export interface ConfusionData {
  injection: { BLOCK: number; WARN: number; MONITOR: number; PASS: number };
  benign: { PASS: number; BLOCK: number; MONITOR: number };
  harmful: { WARN: number; MONITOR: number };
}

export interface DatasetStats {
  total: number;
  train: number;
  val: number;
  test: number;
  label_distribution: { "0": number; "1": number; "2": number };
  source_distribution: Record<string, number>;
}
