import { useState, useRef, useEffect } from "react";
import { ATTACK_CASES, getDecisionColor, getDecisionBg, getRiskColor } from "@/lib/mockData";
import type { DetectResponse } from "@/lib/types";
import { Send, RefreshCw, AlertTriangle, CheckCircle, XCircle, Eye } from "lucide-react";

// ── 风险仪表盘 ────────────────────────────────────────────────────────────────
function RiskDial({ score }: { score: number }) {
  const circumference = 2 * Math.PI * 36;
  const offset = circumference * (1 - score);
  const color = score >= 0.7 ? "oklch(0.62 0.22 25)" : score >= 0.4 ? "oklch(0.72 0.17 80)" : "oklch(0.65 0.18 155)";

  return (
    <svg width="90" height="90" viewBox="0 0 90 90">
      <circle cx="45" cy="45" r="36" fill="none" stroke="oklch(0.22 0.015 264)" strokeWidth="7" />
      <circle
        cx="45" cy="45" r="36"
        fill="none"
        stroke={color}
        strokeWidth="7"
        strokeDasharray={circumference}
        strokeDashoffset={offset}
        strokeLinecap="round"
        transform="rotate(-90 45 45)"
        style={{ transition: "stroke-dashoffset 1s cubic-bezier(0.4,0,0.2,1), stroke 0.5s" }}
      />
      <text x="45" y="42" textAnchor="middle" fill="oklch(0.91 0.008 250)" fontSize="14" fontWeight="700" fontFamily="var(--font-mono)">
        {(score * 100).toFixed(0)}
      </text>
      <text x="45" y="55" textAnchor="middle" fill="oklch(0.45 0.015 264)" fontSize="8" fontFamily="var(--font-mono)">
        RISK
      </text>
    </svg>
  );
}

// ── 信号分解条 ────────────────────────────────────────────────────────────────
function SignalBar({ label, value, color }: { label: string; value: number; color: string }) {
  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "3px" }}>
        <span style={{ fontSize: "0.72rem", color: "oklch(0.58 0.015 264)", fontFamily: "var(--font-body)" }}>{label}</span>
        <span style={{ fontSize: "0.72rem", fontFamily: "var(--font-mono)", color: "oklch(0.72 0.01 250)" }}>
          {(value * 100).toFixed(1)}%
        </span>
      </div>
      <div className="signal-bar">
        <div
          className="signal-bar-fill"
          style={{ width: `${value * 100}%`, background: color }}
        />
      </div>
    </div>
  );
}

// ── 决策图标 ──────────────────────────────────────────────────────────────────
function DecisionIcon({ decision }: { decision: string }) {
  if (decision === "BLOCK") return <XCircle size={20} color="oklch(0.72 0.22 25)" />;
  if (decision === "WARN") return <AlertTriangle size={20} color="oklch(0.78 0.17 80)" />;
  if (decision === "PASS") return <CheckCircle size={20} color="oklch(0.72 0.18 155)" />;
  return <Eye size={20} color="oklch(0.68 0.18 290)" />;
}

const CATEGORY_COLORS: Record<string, string> = {
  "英文经典": "oklch(0.57 0.19 258)",
  "越狱攻击": "oklch(0.62 0.22 25)",
  "信息窃取": "oklch(0.72 0.17 80)",
  "模板攻击": "oklch(0.60 0.18 290)",
  "中文攻击": "oklch(0.65 0.15 200)",
  "混淆攻击": "oklch(0.68 0.18 290)",
  "隐蔽攻击": "oklch(0.72 0.17 80)",
  "正常请求": "oklch(0.65 0.18 155)",
  "RAG 攻击": "oklch(0.62 0.22 25)",
};

// ── 模拟检测结果生成 ──────────────────────────────────────────────────────────
function simulateDetection(prompt: string): DetectResponse {
  const lower = prompt.toLowerCase();
  const isAttack =
    lower.includes("ignore") ||
    lower.includes("forget") ||
    lower.includes("jailbreak") ||
    lower.includes("dan mode") ||
    lower.includes("system prompt") ||
    lower.includes("忽略") ||
    lower.includes("越狱") ||
    lower.includes("没有任何限制") ||
    lower.includes("system override") ||
    lower.includes("base64") ||
    lower.includes("swd9bb") ||
    lower.includes("ｉｇｎｏｒｅ") ||
    /[^\x00-\x7F]{5,}/.test(prompt) && lower.includes("instruction");

  const isMedium =
    lower.includes("creative writing") ||
    lower.includes("roleplay") ||
    lower.includes("imagine") ||
    lower.includes("character");

  const isBenign = !isAttack && !isMedium;

  let decision: "BLOCK" | "WARN" | "PASS" | "MONITOR";
  let risk_score: number;
  let injection_score: number;
  let judge_label: string;
  let judge_confidence: number;

  if (isAttack) {
    decision = "BLOCK";
    risk_score = 0.85 + Math.random() * 0.14;
    injection_score = 0.88 + Math.random() * 0.11;
    judge_label = "injection";
    judge_confidence = 0.87 + Math.random() * 0.12;
  } else if (isMedium) {
    decision = Math.random() > 0.5 ? "WARN" : "MONITOR";
    risk_score = 0.38 + Math.random() * 0.25;
    injection_score = 0.35 + Math.random() * 0.2;
    judge_label = "injection";
    judge_confidence = 0.55 + Math.random() * 0.2;
  } else {
    decision = "PASS";
    risk_score = 0.05 + Math.random() * 0.18;
    injection_score = 0.04 + Math.random() * 0.15;
    judge_label = "benign";
    judge_confidence = 0.82 + Math.random() * 0.15;
  }

  const latency = 80 + Math.random() * 350;

  return {
    decision,
    risk_score: Math.min(1, risk_score),
    breakdown: {
      injection_score: Math.min(1, injection_score),
      intent_score: isAttack ? 0.75 + Math.random() * 0.2 : 0.05 + Math.random() * 0.15,
      benign_discount: isBenign ? 0.3 + Math.random() * 0.4 : 0.02 + Math.random() * 0.1,
      kb_confidence: 0.5 + Math.random() * 0.4,
      boundary_state: isAttack ? "known" : "fuzzy",
      boundary_risk_bonus: isAttack ? 0.05 + Math.random() * 0.1 : 0,
      probe_score: isAttack ? 0.1 + Math.random() * 0.3 : 0.01 + Math.random() * 0.05,
      entropy_risk_bonus: 0,
      rag_injection_score: lower.includes("document") || lower.includes("summary") ? 0.3 + Math.random() * 0.4 : 0,
      drift_score: 0,
      drift_direction: "normal",
      user_trust: 0.5,
      context_risk: 0,
      zh_rule_score: /[\u4e00-\u9fff]/.test(prompt) && isAttack ? 0.6 + Math.random() * 0.3 : 0,
    },
    refusal_message: isAttack
      ? "您的请求包含可能试图覆盖系统指令的内容，已被安全网关拦截。如有合理需求，请重新描述您的问题。"
      : isMedium
      ? "您的请求包含潜在风险内容，已记录并转发，请注意合规使用。"
      : "",
    explanation: isAttack
      ? `检测到${judge_label === "injection" ? "提示注入" : "有害内容"}攻击模式，风险评分 ${(risk_score * 100).toFixed(1)}%`
      : "请求通过安全检测",
    detection_path: isAttack ? "semantic_hard_block" : isMedium ? "combined" : "semantic",
    latency_ms: Math.round(latency),
    triggered_signals: isAttack
      ? [`injection_hard_block(${injection_score.toFixed(3)})`, `safety_judge:${judge_label}(${judge_confidence.toFixed(2)})`]
      : isMedium
      ? [`role_play(${injection_score.toFixed(3)})`]
      : [],
    judge_label,
    judge_confidence,
    judge_scores: judge_label === "benign"
      ? [judge_confidence, 1 - judge_confidence - 0.02, 0.02]
      : [1 - judge_confidence - 0.02, judge_confidence, 0.02],
  };
}

interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  blocked?: boolean;
  knowledge_boundary_triggered?: boolean;
  detection?: {
    decision: string;
    risk_score: number;
    refusal_message?: string;
    llm_generated?: boolean;
  };
}

export default function ArenaTab() {
  const [selectedCase, setSelectedCase] = useState<string | null>(null);
  const [customPrompt, setCustomPrompt] = useState("");
  const [result, setResult] = useState<DetectResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [activePrompt, setActivePrompt] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // LLM 对话面板状态
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([]);
  const [chatInput, setChatInput] = useState("");
  const [chatLoading, setChatLoading] = useState(false);
  const [llmAvailable, setLlmAvailable] = useState<boolean | null>(null);
  const chatEndRef = useRef<HTMLDivElement>(null);

  // 检查 LLM 是否可用
  useEffect(() => {
    fetch("http://localhost:8000/api/v1/health", { signal: AbortSignal.timeout(3000) })
      .then((r) => r.json())
      .then((d) => setLlmAvailable(d.llm_enabled === true))
      .catch(() => setLlmAvailable(false));
  }, []);

  // 自动滚动到底部
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [chatMessages]);

  const runDetection = async (prompt: string) => {
    if (!prompt.trim()) return;
    setLoading(true);
    setActivePrompt(prompt);
    setResult(null);

    // 先尝试真实 API，失败则用模拟
    try {
      const res = await fetch("http://localhost:8000/api/v1/detect", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ prompt, user_id: "demo" }),
        signal: AbortSignal.timeout(8000),
      });
      if (res.ok) {
        const data = await res.json();
        setResult(data);
        setLoading(false);
        return;
      }
    } catch {
      // 降级到模拟
    }

    // 模拟延迟
    await new Promise((r) => setTimeout(r, 600 + Math.random() * 400));
    setResult(simulateDetection(prompt));
    setLoading(false);
  };

  const sendChatMessage = async () => {
    if (!chatInput.trim() || chatLoading) return;
    const userMsg = chatInput.trim();
    setChatInput("");
    setChatMessages((prev) => [...prev, { role: "user", content: userMsg }]);
    setChatLoading(true);

    try {
      const res = await fetch("http://localhost:8000/api/v1/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          messages: [...chatMessages, { role: "user", content: userMsg }].map((m) => ({
            role: m.role,
            content: m.content,
          })),
          user_id: "demo",
        }),
        signal: AbortSignal.timeout(30000),
      });
      if (res.ok) {
        const data = await res.json();
        setChatMessages((prev) => [
          ...prev,
          {
            role: "assistant",
            content: data.blocked
              ? (data.detection?.refusal_message || "请求已被安全网关拦截")
              : data.reply,
            blocked: data.blocked,
            knowledge_boundary_triggered: data.knowledge_boundary_triggered,
            detection: data.detection
              ? {
                  decision: data.detection.decision || (data.blocked ? "BLOCK" : "PASS"),
                  risk_score: data.detection.risk_score || 0,
                  refusal_message: data.detection.refusal_message,
                  llm_generated: data.detection.llm_generated,
                }
              : undefined,
          },
        ]);
      } else {
        setChatMessages((prev) => [
          ...prev,
          { role: "assistant", content: `服务返回错误 (${res.status})，请检查后端日志。`, blocked: false },
        ]);
      }
    } catch (e) {
      setChatMessages((prev) => [
        ...prev,
        { role: "assistant", content: "LLM 服务不可用。请在 .env 中配置 LLM_ENABLED=true 并启动 Ollama/API。", blocked: false },
      ]);
    }
    setChatLoading(false);
  };

  const handleCaseSelect = (caseId: string) => {
    const c = ATTACK_CASES.find((a) => a.id === caseId);
    if (!c) return;
    setSelectedCase(caseId);
    setCustomPrompt(c.prompt);
    runDetection(c.prompt);
    // 同时将样本填入对话输入框
    setChatInput(c.prompt);
  };

  const handleCustomRun = () => {
    runDetection(customPrompt);
  };

  return (
    <div style={{ display: "grid", gridTemplateColumns: "300px 1fr 320px", gap: "0.875rem", height: "calc(100vh - 200px)", minHeight: "600px" }}>

      {/* ── 左侧：攻击样本列表 ──────────────────────────────────────────── */}
      <div
        style={{
          background: "oklch(0.115 0.014 264)",
          border: "1px solid oklch(0.22 0.015 264)",
          borderRadius: "10px",
          display: "flex",
          flexDirection: "column",
          overflow: "hidden",
        }}
      >
        <div style={{ padding: "1rem 1.25rem", borderBottom: "1px solid oklch(0.2 0.015 264)" }}>
          <div className="section-header" style={{ marginBottom: 0 }}>
            <span style={{ fontFamily: "var(--font-display)", fontWeight: 600, fontSize: "0.9rem", color: "oklch(0.91 0.008 250)" }}>
              预置攻击样本
            </span>
          </div>
          <div style={{ fontSize: "0.72rem", color: "oklch(0.45 0.015 264)", marginTop: "4px", fontFamily: "var(--font-body)" }}>
            {ATTACK_CASES.length} 个样本 · 点击加载并检测
          </div>
        </div>
        <div style={{ flex: 1, overflowY: "auto", padding: "0.5rem" }}>
          {ATTACK_CASES.map((c) => (
            <button
              key={c.id}
              onClick={() => handleCaseSelect(c.id)}
              style={{
                width: "100%",
                textAlign: "left",
                padding: "0.7rem 0.875rem",
                borderRadius: "7px",
                border: `1px solid ${selectedCase === c.id ? "oklch(0.35 0.015 264)" : "transparent"}`,
                background: selectedCase === c.id ? "oklch(0.155 0.015 264)" : "transparent",
                cursor: "pointer",
                transition: "all 0.15s ease",
                marginBottom: "2px",
              }}
            >
              <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "3px" }}>
                <span
                  style={{
                    fontSize: "0.65rem",
                    fontFamily: "var(--font-mono)",
                    fontWeight: 600,
                    padding: "1px 6px",
                    borderRadius: "3px",
                    background: `${CATEGORY_COLORS[c.category] || "oklch(0.45 0.015 264)"}20`,
                    color: CATEGORY_COLORS[c.category] || "oklch(0.45 0.015 264)",
                    border: `1px solid ${CATEGORY_COLORS[c.category] || "oklch(0.45 0.015 264)"}40`,
                    flexShrink: 0,
                  }}
                >
                  {c.category}
                </span>
                <span style={{ fontSize: "0.82rem", fontWeight: 500, color: "oklch(0.82 0.008 250)", fontFamily: "var(--font-body)" }}>
                  {c.name}
                </span>
              </div>
              <div style={{ fontSize: "0.72rem", color: "oklch(0.45 0.015 264)", fontFamily: "var(--font-mono)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                {c.prompt.slice(0, 55)}...
              </div>
            </button>
          ))}
        </div>
      </div>

      {/* ── 右侧：输入 + 结果 ──────────────────────────────────────────── */}
      <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>

        {/* 输入区 */}
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
              自定义检测输入
            </span>
          </div>
          <textarea
            ref={textareaRef}
            value={customPrompt}
            onChange={(e) => setCustomPrompt(e.target.value)}
            placeholder="输入任意文本进行检测，或从左侧选择预置攻击样本..."
            style={{
              width: "100%",
              minHeight: "100px",
              background: "oklch(0.09 0.012 264)",
              border: "1px solid oklch(0.25 0.015 264)",
              borderRadius: "7px",
              padding: "0.75rem",
              color: "oklch(0.85 0.008 250)",
              fontFamily: "var(--font-mono)",
              fontSize: "0.82rem",
              resize: "vertical",
              outline: "none",
              lineHeight: 1.6,
            }}
            onFocus={(e) => { e.target.style.borderColor = "oklch(0.4 0.19 258)"; }}
            onBlur={(e) => { e.target.style.borderColor = "oklch(0.25 0.015 264)"; }}
          />
          <div style={{ display: "flex", gap: "0.75rem", marginTop: "0.75rem" }}>
            <button
              onClick={handleCustomRun}
              disabled={loading || !customPrompt.trim()}
              style={{
                display: "flex",
                alignItems: "center",
                gap: "6px",
                padding: "8px 20px",
                borderRadius: "7px",
                background: "oklch(0.57 0.19 258)",
                color: "white",
                fontFamily: "var(--font-body)",
                fontWeight: 600,
                fontSize: "0.875rem",
                border: "none",
                cursor: loading || !customPrompt.trim() ? "not-allowed" : "pointer",
                opacity: loading || !customPrompt.trim() ? 0.5 : 1,
                transition: "all 0.15s ease",
              }}
            >
              {loading ? (
                <RefreshCw size={14} style={{ animation: "spin 1s linear infinite" }} />
              ) : (
                <Send size={14} />
              )}
              {loading ? "检测中..." : "开始检测"}
            </button>
            <button
              onClick={() => { setCustomPrompt(""); setResult(null); setSelectedCase(null); }}
              style={{
                padding: "8px 16px",
                borderRadius: "7px",
                background: "transparent",
                color: "oklch(0.52 0.015 264)",
                fontFamily: "var(--font-body)",
                fontSize: "0.875rem",
                border: "1px solid oklch(0.28 0.015 264)",
                cursor: "pointer",
                transition: "all 0.15s ease",
              }}
            >
              清空
            </button>
          </div>
        </div>

        {/* 结果区 */}
        <div
          style={{
            flex: 1,
            background: "oklch(0.115 0.014 264)",
            border: "1px solid oklch(0.22 0.015 264)",
            borderRadius: "10px",
            padding: "1.25rem",
            overflow: "auto",
          }}
        >
          {!result && !loading && (
            <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", height: "200px", gap: "0.75rem" }}>
              <div style={{ fontSize: "2rem", opacity: 0.3 }}>⚔</div>
              <div style={{ color: "oklch(0.38 0.015 264)", fontFamily: "var(--font-body)", fontSize: "0.875rem" }}>
                选择预置样本或输入自定义文本开始检测
              </div>
            </div>
          )}

          {loading && (
            <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", height: "200px", gap: "1rem" }}>
              <div style={{ position: "relative", width: "48px", height: "48px" }}>
                <svg viewBox="0 0 48 48" style={{ animation: "spin 1.2s linear infinite" }}>
                  <circle cx="24" cy="24" r="20" fill="none" stroke="oklch(0.22 0.015 264)" strokeWidth="4" />
                  <circle cx="24" cy="24" r="20" fill="none" stroke="oklch(0.57 0.19 258)" strokeWidth="4"
                    strokeDasharray="30 96" strokeLinecap="round" />
                </svg>
              </div>
              <div style={{ color: "oklch(0.52 0.015 264)", fontFamily: "var(--font-mono)", fontSize: "0.82rem" }}>
                正在运行多通道检测...
              </div>
            </div>
          )}

          {result && !loading && (
            <div style={{ animation: "fadeIn 0.3s ease" }}>
              {/* 决策头部 */}
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "1.25rem",
                  padding: "1rem 1.25rem",
                  background: getDecisionBg(result.decision),
                  borderRadius: "8px",
                  border: `1px solid ${getDecisionColor(result.decision)}30`,
                  marginBottom: "1rem",
                }}
              >
                <RiskDial score={result.risk_score} />
                <div style={{ flex: 1 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", marginBottom: "0.5rem" }}>
                    <DecisionIcon decision={result.decision} />
                    <span
                      style={{
                        fontFamily: "var(--font-mono)",
                        fontWeight: 700,
                        fontSize: "1.5rem",
                        color: getDecisionColor(result.decision),
                        letterSpacing: "0.05em",
                      }}
                    >
                      {result.decision}
                    </span>
                    <span
                      style={{
                        fontFamily: "var(--font-mono)",
                        fontSize: "0.72rem",
                        color: "oklch(0.45 0.015 264)",
                        padding: "2px 8px",
                        background: "oklch(0.09 0.012 264)",
                        borderRadius: "4px",
                        border: "1px solid oklch(0.22 0.015 264)",
                      }}
                    >
                      {result.detection_path}
                    </span>
                    <span style={{ fontSize: "0.72rem", color: "oklch(0.45 0.015 264)", fontFamily: "var(--font-mono)", marginLeft: "auto" }}>
                      {result.latency_ms.toFixed(0)} ms
                    </span>
                  </div>
                  {result.refusal_message && (
                    <div>
                      <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "0.375rem" }}>
                        <span style={{ fontSize: "0.68rem", fontFamily: "var(--font-mono)", color: "oklch(0.45 0.015 264)" }}>拒答消息</span>
                        {result.llm_generated && (
                          <span
                            style={{
                              fontFamily: "var(--font-mono)",
                              fontSize: "0.62rem",
                              fontWeight: 600,
                              padding: "1px 6px",
                              borderRadius: "3px",
                              background: "oklch(0.65 0.18 155 / 0.12)",
                              color: "oklch(0.72 0.18 155)",
                              border: "1px solid oklch(0.65 0.18 155 / 0.3)",
                              letterSpacing: "0.05em",
                            }}
                            title="此拒答消息由 LLM 根据攻击类型生成"
                          >
                            LLM 生成
                          </span>
                        )}
                      </div>
                      <div
                        style={{
                          fontSize: "0.82rem",
                          color: "oklch(0.72 0.01 250)",
                          fontFamily: "var(--font-body)",
                          lineHeight: 1.5,
                          padding: "0.5rem 0.75rem",
                          background: "oklch(0.09 0.012 264)",
                          borderRadius: "5px",
                          borderLeft: `3px solid ${getDecisionColor(result.decision)}`,
                        }}
                      >
                        {result.refusal_message}
                      </div>
                    </div>
                  )}
                </div>
              </div>

              {/* 信号分解 */}
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1rem" }}>
                <div>
                  <div style={{ fontSize: "0.75rem", fontWeight: 600, color: "oklch(0.58 0.015 264)", fontFamily: "var(--font-body)", marginBottom: "0.75rem", textTransform: "uppercase", letterSpacing: "0.05em" }}>
                    检测信号分解
                  </div>
                  <div style={{ display: "flex", flexDirection: "column", gap: "0.6rem" }}>
                    <SignalBar label="注入得分 (Injection Score)" value={result.breakdown.injection_score} color="oklch(0.62 0.22 25)" />
                    <SignalBar label="意图得分 (Intent Score)" value={result.breakdown.intent_score} color="oklch(0.57 0.19 258)" />
                    <SignalBar label="良性折扣 (Benign Discount)" value={result.breakdown.benign_discount} color="oklch(0.65 0.18 155)" />
                    <SignalBar label="知识库置信度 (KB Confidence)" value={result.breakdown.kb_confidence} color="oklch(0.72 0.17 80)" />
                    {result.breakdown.probe_score > 0.01 && (
                      <SignalBar label="探针得分 (Probe Score)" value={result.breakdown.probe_score} color="oklch(0.60 0.18 290)" />
                    )}
                    {result.breakdown.zh_rule_score > 0.01 && (
                      <SignalBar label="中文规则得分 (ZH Rule)" value={result.breakdown.zh_rule_score} color="oklch(0.65 0.15 200)" />
                    )}
                    {result.breakdown.rag_injection_score > 0.01 && (
                      <SignalBar label="RAG 间接注入 (RAG Score)" value={result.breakdown.rag_injection_score} color="oklch(0.72 0.17 80)" />
                    )}
                    {result.breakdown.drift_score > 0.01 && (
                      <SignalBar label="意图漂移 (Drift Score)" value={result.breakdown.drift_score} color="oklch(0.57 0.19 258)" />
                    )}
                    {/* 边界状态标签 */}
                    <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginTop: "0.25rem" }}>
                      <span style={{ fontSize: "0.72rem", color: "oklch(0.58 0.015 264)", fontFamily: "var(--font-body)" }}>攻击知识库匹配</span>
                      <span
                        style={{
                          fontFamily: "var(--font-mono)",
                          fontSize: "0.68rem",
                          fontWeight: 600,
                          padding: "2px 8px",
                          borderRadius: "4px",
                          background: result.breakdown.boundary_state === "known"
                            ? "oklch(0.62 0.22 25 / 0.12)"
                            : result.breakdown.boundary_state === "fuzzy"
                            ? "oklch(0.72 0.17 80 / 0.12)"
                            : "oklch(0.65 0.18 155 / 0.12)",
                          color: result.breakdown.boundary_state === "known"
                            ? "oklch(0.72 0.22 25)"
                            : result.breakdown.boundary_state === "fuzzy"
                            ? "oklch(0.78 0.17 80)"
                            : "oklch(0.72 0.18 155)",
                          border: `1px solid ${result.breakdown.boundary_state === "known" ? "oklch(0.62 0.22 25 / 0.3)" : result.breakdown.boundary_state === "fuzzy" ? "oklch(0.72 0.17 80 / 0.3)" : "oklch(0.65 0.18 155 / 0.3)"}`,
                        }}
                      >
                        {result.breakdown.boundary_state || "unknown"}
                      </span>
                    </div>
                  </div>
                </div>

                <div>
                  {/* Safety Judge 结果 */}
                  {result.judge_label && (
                    <div style={{ marginBottom: "1rem" }}>
                      <div style={{ fontSize: "0.75rem", fontWeight: 600, color: "oklch(0.58 0.015 264)", fontFamily: "var(--font-body)", marginBottom: "0.75rem", textTransform: "uppercase", letterSpacing: "0.05em" }}>
                        Safety Judge (LLM-Judge)
                      </div>
                      <div
                        style={{
                          padding: "0.75rem",
                          background: "oklch(0.09 0.012 264)",
                          borderRadius: "7px",
                          border: "1px solid oklch(0.22 0.015 264)",
                        }}
                      >
                        <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "0.5rem" }}>
                          <span style={{ fontSize: "0.72rem", color: "oklch(0.45 0.015 264)", fontFamily: "var(--font-mono)" }}>判定类别</span>
                          <span
                            style={{
                              fontFamily: "var(--font-mono)",
                              fontWeight: 700,
                              fontSize: "0.85rem",
                              color: result.judge_label === "benign" ? "oklch(0.72 0.18 155)" : result.judge_label === "injection" ? "oklch(0.72 0.22 25)" : "oklch(0.78 0.17 80)",
                              textTransform: "uppercase",
                              letterSpacing: "0.05em",
                            }}
                          >
                            {result.judge_label}
                          </span>
                          <span style={{ marginLeft: "auto", fontFamily: "var(--font-mono)", fontSize: "0.78rem", color: "oklch(0.65 0.015 264)" }}>
                            {result.judge_confidence !== undefined ? `${(result.judge_confidence * 100).toFixed(1)}%` : "—"}
                          </span>
                        </div>
                        {result.judge_scores && (
                          <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
                            {["benign", "injection", "harmful"].map((label, i) => (
                              <div key={label} style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                                <span style={{ fontSize: "0.68rem", fontFamily: "var(--font-mono)", color: "oklch(0.45 0.015 264)", width: "60px" }}>{label}</span>
                                <div className="signal-bar" style={{ flex: 1 }}>
                                  <div
                                    className="signal-bar-fill"
                                    style={{
                                      width: `${(result.judge_scores![i] || 0) * 100}%`,
                                      background: i === 0 ? "oklch(0.65 0.18 155)" : i === 1 ? "oklch(0.62 0.22 25)" : "oklch(0.72 0.17 80)",
                                    }}
                                  />
                                </div>
                                <span style={{ fontSize: "0.68rem", fontFamily: "var(--font-mono)", color: "oklch(0.58 0.015 264)", width: "40px", textAlign: "right" }}>
                                  {((result.judge_scores![i] || 0) * 100).toFixed(1)}%
                                </span>
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    </div>
                  )}

                  {/* LLM 知识边界感知 */}
                  {result.knowledge_boundary_triggered !== undefined && (
                    <div style={{ marginBottom: "1rem" }}>
                      <div style={{ fontSize: "0.75rem", fontWeight: 600, color: "oklch(0.58 0.015 264)", fontFamily: "var(--font-body)", marginBottom: "0.5rem", textTransform: "uppercase", letterSpacing: "0.05em" }}>
                        LLM 知识边界感知
                      </div>
                      <div
                        style={{
                          padding: "0.75rem",
                          background: result.knowledge_boundary_triggered
                            ? "oklch(0.72 0.17 80 / 0.08)"
                            : "oklch(0.09 0.012 264)",
                          borderRadius: "7px",
                          border: `1px solid ${result.knowledge_boundary_triggered ? "oklch(0.72 0.17 80 / 0.3)" : "oklch(0.22 0.015 264)"}`,
                          borderLeft: `3px solid ${result.knowledge_boundary_triggered ? "oklch(0.72 0.17 80)" : "oklch(0.65 0.18 155)"}`,
                        }}
                      >
                        <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: result.llm_response ? "0.5rem" : 0 }}>
                          <span style={{ fontSize: "0.85rem" }}>
                            {result.knowledge_boundary_triggered ? "🧠" : "✅"}
                          </span>
                          <span style={{ fontSize: "0.78rem", fontFamily: "var(--font-body)", color: result.knowledge_boundary_triggered ? "oklch(0.82 0.16 80)" : "oklch(0.72 0.18 155)" }}>
                            {result.knowledge_boundary_triggered
                              ? "LLM 触发知识边界感知：诚实表达不确定性"
                              : "LLM 知识边界正常：回答在知识范围内"}
                          </span>
                        </div>
                        {result.llm_response && (
                          <div style={{ fontSize: "0.72rem", color: "oklch(0.58 0.015 264)", fontFamily: "var(--font-body)", lineHeight: 1.6, padding: "0.5rem", background: "oklch(0.07 0.010 264)", borderRadius: "4px" }}>
                            {result.llm_response.slice(0, 200)}{result.llm_response.length > 200 ? "..." : ""}
                          </div>
                        )}
                      </div>
                    </div>
                  )}

                  {/* 触发信号 */}
                  <div>
                    <div style={{ fontSize: "0.75rem", fontWeight: 600, color: "oklch(0.58 0.015 264)", fontFamily: "var(--font-body)", marginBottom: "0.5rem", textTransform: "uppercase", letterSpacing: "0.05em" }}>
                      触发信号
                    </div>
                    {result.triggered_signals.length === 0 ? (
                      <div style={{ fontSize: "0.78rem", color: "oklch(0.38 0.015 264)", fontFamily: "var(--font-mono)" }}>
                        无触发信号
                      </div>
                    ) : (
                      <div style={{ display: "flex", flexWrap: "wrap", gap: "0.4rem" }}>
                        {result.triggered_signals.map((sig, i) => (
                          <span
                            key={i}
                            style={{
                              fontFamily: "var(--font-mono)",
                              fontSize: "0.7rem",
                              padding: "3px 8px",
                              borderRadius: "4px",
                              background: "oklch(0.09 0.012 264)",
                              color: "oklch(0.65 0.015 264)",
                              border: "1px solid oklch(0.25 0.015 264)",
                            }}
                          >
                            {sig}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* ── 右侧：LLM 对话面板 ────────────────────────────────── */}
      <div
        style={{
          background: "oklch(0.115 0.014 264)",
          border: "1px solid oklch(0.22 0.015 264)",
          borderRadius: "10px",
          display: "flex",
          flexDirection: "column",
          overflow: "hidden",
        }}
      >
        {/* 头部 */}
        <div style={{ padding: "1rem 1.25rem", borderBottom: "1px solid oklch(0.2 0.015 264)" }}>
          <div className="section-header" style={{ marginBottom: "4px" }}>
            <span style={{ fontFamily: "var(--font-display)", fontWeight: 600, fontSize: "0.9rem", color: "oklch(0.91 0.008 250)" }}>
              LLM 对话测试
            </span>
          </div>
          <div style={{ fontSize: "0.72rem", color: "oklch(0.45 0.015 264)", fontFamily: "var(--font-body)" }}>
            {llmAvailable === null ? "检查中..." : llmAvailable ? "实时对话，展示知识边界感知" : "LLM 未启用"}
          </div>
        </div>

        {/* 对话历史 */}
        <div style={{ flex: 1, overflowY: "auto", padding: "0.75rem", display: "flex", flexDirection: "column", gap: "0.75rem" }}>
          {chatMessages.length === 0 && (
            <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", height: "100%", gap: "0.75rem", opacity: 0.4 }}>
              <div style={{ fontSize: "2rem" }}>🧠</div>
              <div style={{ color: "oklch(0.38 0.015 264)", fontFamily: "var(--font-body)", fontSize: "0.82rem", textAlign: "center", lineHeight: 1.6 }}>
                在下方输入框发送消息，<br />体验 LLM 知识边界感知功能
              </div>
            </div>
          )}
          {chatMessages.map((msg, i) => (
            <div
              key={i}
              style={{
                alignSelf: msg.role === "user" ? "flex-end" : "flex-start",
                maxWidth: "85%",
              }}
            >
              {msg.role === "user" ? (
                <div
                  style={{
                    padding: "0.6rem 0.875rem",
                    background: "oklch(0.57 0.19 258 / 0.12)",
                    border: "1px solid oklch(0.57 0.19 258 / 0.3)",
                    borderRadius: "8px 8px 2px 8px",
                    fontSize: "0.82rem",
                    color: "oklch(0.82 0.008 250)",
                    fontFamily: "var(--font-body)",
                    lineHeight: 1.5,
                  }}
                >
                  {msg.content}
                </div>
              ) : (
                <div>
                  {msg.blocked && msg.detection && (
                    <div
                      style={{
                        fontSize: "0.68rem",
                        fontFamily: "var(--font-mono)",
                        color: "oklch(0.72 0.22 25)",
                        marginBottom: "4px",
                        display: "flex",
                        alignItems: "center",
                        gap: "0.5rem",
                      }}
                    >
                      <XCircle size={12} />
                      <span>被拦截：{msg.detection.decision} (风险分 {(msg.detection.risk_score * 100).toFixed(1)}%)</span>
                      {msg.detection.llm_generated && (
                        <span
                          style={{
                            padding: "1px 5px",
                            borderRadius: "3px",
                            background: "oklch(0.65 0.18 155 / 0.12)",
                            color: "oklch(0.72 0.18 155)",
                            border: "1px solid oklch(0.65 0.18 155 / 0.3)",
                            fontSize: "0.6rem",
                          }}
                        >
                          LLM生成
                        </span>
                      )}
                    </div>
                  )}
                  {msg.knowledge_boundary_triggered && (
                    <div
                      style={{
                        fontSize: "0.68rem",
                        fontFamily: "var(--font-mono)",
                        color: "oklch(0.82 0.16 80)",
                        marginBottom: "4px",
                        display: "flex",
                        alignItems: "center",
                        gap: "0.5rem",
                      }}
                    >
                      <span>🧠</span>
                      <span>知识边界感知触发：LLM 诚实表达不确定性</span>
                    </div>
                  )}
                  <div
                    style={{
                      padding: "0.6rem 0.875rem",
                      background: msg.blocked
                        ? "oklch(0.62 0.22 25 / 0.08)"
                        : msg.knowledge_boundary_triggered
                        ? "oklch(0.72 0.17 80 / 0.08)"
                        : "oklch(0.09 0.012 264)",
                      border: `1px solid ${msg.blocked ? "oklch(0.62 0.22 25 / 0.3)" : "oklch(0.22 0.015 264)"}`,
                      borderRadius: "8px 8px 8px 2px",
                      fontSize: "0.82rem",
                      color: "oklch(0.82 0.008 250)",
                      fontFamily: "var(--font-body)",
                      lineHeight: 1.6,
                    }}
                  >
                    {msg.content}
                  </div>
                </div>
              )}
            </div>
          ))}
          {chatLoading && (
            <div style={{ alignSelf: "flex-start", display: "flex", alignItems: "center", gap: "0.5rem", padding: "0.5rem", color: "oklch(0.45 0.015 264)", fontSize: "0.75rem", fontFamily: "var(--font-mono)" }}>
              <div style={{ width: "12px", height: "12px", borderRadius: "50%", border: "2px solid oklch(0.57 0.19 258)", borderTopColor: "transparent", animation: "spin 0.8s linear infinite" }} />
              LLM 思考中...
            </div>
          )}
          <div ref={chatEndRef} />
        </div>

        {/* 输入框 */}
        <div style={{ padding: "0.75rem", borderTop: "1px solid oklch(0.2 0.015 264)" }}>
          <div style={{ display: "flex", gap: "0.5rem" }}>
            <input
              type="text"
              value={chatInput}
              onChange={(e) => setChatInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && sendChatMessage()}
              placeholder={llmAvailable ? "输入消息测试 LLM..." : "LLM 未启用"}
              disabled={!llmAvailable || chatLoading}
              style={{
                flex: 1,
                padding: "0.5rem 0.75rem",
                background: "oklch(0.09 0.012 264)",
                border: "1px solid oklch(0.22 0.015 264)",
                borderRadius: "6px",
                color: "oklch(0.82 0.008 250)",
                fontSize: "0.82rem",
                fontFamily: "var(--font-body)",
                outline: "none",
              }}
            />
            <button
              onClick={sendChatMessage}
              disabled={!llmAvailable || chatLoading || !chatInput.trim()}
              style={{
                padding: "0.5rem 0.875rem",
                background: llmAvailable && chatInput.trim() && !chatLoading ? "oklch(0.57 0.19 258)" : "oklch(0.22 0.015 264)",
                border: "none",
                borderRadius: "6px",
                color: "white",
                fontSize: "0.82rem",
                fontWeight: 600,
                cursor: llmAvailable && chatInput.trim() && !chatLoading ? "pointer" : "not-allowed",
                display: "flex",
                alignItems: "center",
                gap: "0.375rem",
                transition: "all 0.15s ease",
              }}
            >
              <Send size={14} />
              发送
            </button>
          </div>
          {chatMessages.length > 0 && (
            <button
              onClick={() => setChatMessages([])}
              style={{
                marginTop: "0.5rem",
                width: "100%",
                padding: "0.375rem",
                background: "transparent",
                border: "1px solid oklch(0.22 0.015 264)",
                borderRadius: "5px",
                color: "oklch(0.45 0.015 264)",
                fontSize: "0.72rem",
                fontFamily: "var(--font-mono)",
                cursor: "pointer",
                transition: "all 0.15s ease",
              }}
            >
              <RefreshCw size={11} style={{ display: "inline", marginRight: "4px", verticalAlign: "middle" }} />
              清空对话
            </button>
          )}
        </div>
      </div>

      <style>{`@keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }`}</style>
    </div>
  );
}
