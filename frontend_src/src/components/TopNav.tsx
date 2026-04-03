import { useState, useEffect } from "react";
import { Shield, Activity, Cpu, Brain, BookOpen } from "lucide-react";

interface SystemStatus {
  online: boolean;
  gpu: string;
  llm_enabled: boolean;
  llm_model: string;
  llm_knowledge_boundary: boolean;
  safety_judge_enabled: boolean;
  version: string;
  thresholds: {
    block: number;
    warn: number;
    monitor: number;
    method: string;
  };
  weights: {
    injection: number;
    safety_judge: number;
    intent: number;
    kb: number;
    temporal: number;
  };
}

interface TopNavProps {
  activeTab: string;
  onTabChange: (tab: string) => void;
}

const TABS = [
  { id: "overview", label: "总览", icon: "◈" },
  { id: "arena", label: "攻防靶场", icon: "⚔" },
  { id: "model", label: "模型与架构", icon: "◉" },
  { id: "logs", label: "实时日志", icon: "≡" },
];

export default function TopNav({ activeTab, onTabChange }: TopNavProps) {
  const [status, setStatus] = useState<SystemStatus>({
    online: false,
    gpu: "—",
    llm_enabled: false,
    llm_model: "—",
    llm_knowledge_boundary: false,
    safety_judge_enabled: false,
    version: "v3.2",
    thresholds: { block: 0.68, warn: 0.40, monitor: 0.20, method: "fallback" },
    weights: { injection: 0.35, safety_judge: 0.40, intent: 0.10, kb: 0.10, temporal: 0.08 },
  });
  const [currentTime, setCurrentTime] = useState(new Date());
  const [showDetails, setShowDetails] = useState(false);

  useEffect(() => {
    const checkHealth = async () => {
      try {
        const res = await fetch("http://localhost:8000/api/v1/health", {
          signal: AbortSignal.timeout(3000),
        });
        if (res.ok) {
          const data = await res.json();
          setStatus({
            online: true,
            gpu: data.gpu || "cpu",
            llm_enabled: data.llm_enabled || false,
            llm_model: data.llm_model || "—",
            llm_knowledge_boundary: data.llm_knowledge_boundary || false,
            safety_judge_enabled: data.safety_judge_enabled || false,
            version: `v${data.version || "3.2.0"}`,
            thresholds: data.thresholds || { block: 0.68, warn: 0.40, monitor: 0.20, method: "fallback" },
            weights: data.weights || { injection: 0.35, safety_judge: 0.40, intent: 0.10, kb: 0.10, temporal: 0.08 },
          });
        }
      } catch {
        setStatus((prev) => ({ ...prev, online: false }));
      }
    };
    checkHealth();
    const interval = setInterval(checkHealth, 30000);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    const timer = setInterval(() => setCurrentTime(new Date()), 1000);
    return () => clearInterval(timer);
  }, []);

  return (
    <header
      style={{
        background: "oklch(0.095 0.013 264)",
        borderBottom: "1px solid oklch(0.22 0.015 264)",
        position: "sticky",
        top: 0,
        zIndex: 100,
        backdropFilter: "blur(12px)",
      }}
    >
      {/* Top bar */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: "1rem",
          padding: "0 1.5rem",
          height: "54px",
          borderBottom: "1px solid oklch(0.18 0.015 264)",
        }}
      >
        {/* Logo */}
        <div style={{ display: "flex", alignItems: "center", gap: "0.625rem", flexShrink: 0 }}>
          <div
            style={{
              width: "32px",
              height: "32px",
              background: "linear-gradient(135deg, oklch(0.57 0.19 258), oklch(0.65 0.18 155))",
              borderRadius: "8px",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              boxShadow: "0 0 16px oklch(0.57 0.19 258 / 0.3)",
              flexShrink: 0,
            }}
          >
            <Shield size={16} color="white" strokeWidth={2.5} />
          </div>
          <div>
            <div
              style={{
                fontFamily: "var(--font-display)",
                fontWeight: 700,
                fontSize: "1rem",
                color: "oklch(0.91 0.008 250)",
                letterSpacing: "0.02em",
                lineHeight: 1.2,
              }}
            >
              Refusal<span style={{ color: "oklch(0.57 0.19 258)" }}>Guard</span>
            </div>
            <div
              style={{
                fontFamily: "var(--font-mono)",
                fontSize: "0.62rem",
                color: "oklch(0.45 0.015 264)",
                letterSpacing: "0.05em",
              }}
            >
              PROMPT INJECTION DEFENSE GATEWAY
            </div>
          </div>
        </div>

        {/* Version badge */}
        <div
          style={{
            fontFamily: "var(--font-mono)",
            fontSize: "0.68rem",
            fontWeight: 600,
            padding: "2px 8px",
            borderRadius: "4px",
            border: "1px solid oklch(0.57 0.19 258 / 0.4)",
            color: "oklch(0.57 0.19 258)",
            letterSpacing: "0.05em",
            flexShrink: 0,
          }}
        >
          {status.version}
        </div>

        <div style={{ flex: 1 }} />

        {/* Status indicators */}
        <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
          {/* GPU info */}
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: "4px",
              fontFamily: "var(--font-mono)",
              fontSize: "0.7rem",
              color: "oklch(0.45 0.015 264)",
            }}
          >
            <Cpu size={12} />
            <span>{status.gpu}</span>
          </div>

          {/* Safety Judge badge */}
          <div
            style={{
              fontFamily: "var(--font-mono)",
              fontSize: "0.68rem",
              fontWeight: 600,
              padding: "2px 8px",
              borderRadius: "4px",
              border: `1px solid ${status.safety_judge_enabled ? "oklch(0.57 0.19 258 / 0.5)" : "oklch(0.35 0.015 264)"}`,
              color: status.safety_judge_enabled ? "oklch(0.72 0.18 258)" : "oklch(0.42 0.015 264)",
              letterSpacing: "0.04em",
              display: "flex",
              alignItems: "center",
              gap: "4px",
            }}
          >
            <Brain size={10} />
            {status.safety_judge_enabled ? "JUDGE ON" : "JUDGE OFF"}
          </div>

          {/* LLM badge — shows model name when enabled */}
          <div
            style={{
              fontFamily: "var(--font-mono)",
              fontSize: "0.68rem",
              fontWeight: 600,
              padding: "2px 8px",
              borderRadius: "4px",
              border: `1px solid ${status.llm_enabled ? "oklch(0.65 0.18 155 / 0.5)" : "oklch(0.35 0.015 264)"}`,
              color: status.llm_enabled ? "oklch(0.72 0.18 155)" : "oklch(0.42 0.015 264)",
              letterSpacing: "0.04em",
              display: "flex",
              alignItems: "center",
              gap: "4px",
              maxWidth: "180px",
              overflow: "hidden",
              whiteSpace: "nowrap",
              textOverflow: "ellipsis",
            }}
          >
            <span
              style={{
                width: "6px",
                height: "6px",
                borderRadius: "50%",
                background: status.llm_enabled ? "oklch(0.65 0.18 155)" : "oklch(0.42 0.015 264)",
                flexShrink: 0,
                boxShadow: status.llm_enabled ? "0 0 5px oklch(0.65 0.18 155)" : "none",
              }}
            />
            {status.llm_enabled ? `LLM: ${status.llm_model}` : "LLM: 未启用"}
          </div>

          {/* Knowledge Boundary badge — only when LLM enabled */}
          {status.llm_enabled && (
            <div
              style={{
                fontFamily: "var(--font-mono)",
                fontSize: "0.68rem",
                fontWeight: 600,
                padding: "2px 8px",
                borderRadius: "4px",
                border: `1px solid ${status.llm_knowledge_boundary ? "oklch(0.75 0.18 60 / 0.5)" : "oklch(0.35 0.015 264)"}`,
                color: status.llm_knowledge_boundary ? "oklch(0.82 0.16 60)" : "oklch(0.42 0.015 264)",
                letterSpacing: "0.04em",
                display: "flex",
                alignItems: "center",
                gap: "4px",
              }}
              title="LLM 知识边界感知：当 LLM 对问题不确定时，引导其诚实说不知道"
            >
              <BookOpen size={10} />
              {status.llm_knowledge_boundary ? "边界感知 ON" : "边界感知 OFF"}
            </div>
          )}

          {/* Online status */}
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: "6px",
              fontFamily: "var(--font-mono)",
              fontSize: "0.72rem",
              fontWeight: 500,
              padding: "4px 10px",
              borderRadius: "20px",
              border: `1px solid ${status.online ? "oklch(0.65 0.18 155 / 0.4)" : "oklch(0.62 0.22 25 / 0.4)"}`,
              color: status.online ? "oklch(0.72 0.18 155)" : "oklch(0.72 0.22 25)",
              cursor: "pointer",
            }}
            onClick={() => setShowDetails(!showDetails)}
            title="点击查看阈值和权重详情"
          >
            <span
              style={{
                width: "7px",
                height: "7px",
                borderRadius: "50%",
                background: status.online ? "oklch(0.65 0.18 155)" : "oklch(0.62 0.22 25)",
                boxShadow: status.online ? "0 0 6px oklch(0.65 0.18 155)" : "none",
                animation: status.online ? "pulse-dot 2s infinite" : "none",
                flexShrink: 0,
              }}
            />
            {status.online ? "服务在线" : "服务离线"}
          </div>

          {/* Clock */}
          <div
            style={{
              fontFamily: "var(--font-mono)",
              fontSize: "0.72rem",
              color: "oklch(0.45 0.015 264)",
              letterSpacing: "0.05em",
            }}
          >
            <Activity size={11} style={{ display: "inline", marginRight: "4px", verticalAlign: "middle" }} />
            {currentTime.toLocaleTimeString("zh-CN", { hour12: false })}
          </div>
        </div>
      </div>

      {/* Expandable details panel */}
      {showDetails && status.online && (
        <div
          style={{
            padding: "0.5rem 1.5rem",
            borderBottom: "1px solid oklch(0.18 0.015 264)",
            background: "oklch(0.085 0.010 264)",
            display: "flex",
            gap: "2rem",
            flexWrap: "wrap",
            fontSize: "0.7rem",
            fontFamily: "var(--font-mono)",
            color: "oklch(0.52 0.015 264)",
          }}
        >
          <div>
            <span style={{ color: "oklch(0.42 0.015 264)" }}>阈值 — </span>
            <span style={{ color: "oklch(0.72 0.22 25)" }}>BLOCK: {status.thresholds.block}</span>
            <span style={{ margin: "0 0.5rem" }}>|</span>
            <span style={{ color: "oklch(0.82 0.16 60)" }}>WARN: {status.thresholds.warn}</span>
            <span style={{ margin: "0 0.5rem" }}>|</span>
            <span style={{ color: "oklch(0.72 0.18 258)" }}>MONITOR: {status.thresholds.monitor}</span>
            <span style={{ marginLeft: "0.5rem", color: "oklch(0.38 0.015 264)" }}>({status.thresholds.method})</span>
          </div>
          <div>
            <span style={{ color: "oklch(0.42 0.015 264)" }}>权重 — </span>
            <span>注入: {status.weights.injection}</span>
            <span style={{ margin: "0 0.5rem" }}>|</span>
            <span style={{ color: "oklch(0.72 0.18 258)" }}>Judge: {status.weights.safety_judge}</span>
            <span style={{ margin: "0 0.5rem" }}>|</span>
            <span>意图: {status.weights.intent}</span>
            <span style={{ margin: "0 0.5rem" }}>|</span>
            <span>知识库: {status.weights.kb}</span>
            <span style={{ margin: "0 0.5rem" }}>|</span>
            <span>时序: {status.weights.temporal}</span>
          </div>
        </div>
      )}

      {/* Tab navigation */}
      <nav
        style={{
          display: "flex",
          alignItems: "center",
          gap: "2px",
          padding: "0 1.5rem",
          height: "42px",
          overflowX: "auto",
        }}
      >
        {TABS.map((tab) => (
          <button
            key={tab.id}
            onClick={() => onTabChange(tab.id)}
            style={{
              display: "flex",
              alignItems: "center",
              gap: "6px",
              padding: "4px 14px",
              borderRadius: "5px",
              fontSize: "0.85rem",
              fontWeight: 500,
              fontFamily: "var(--font-body)",
              color: activeTab === tab.id ? "oklch(0.91 0.008 250)" : "oklch(0.52 0.015 264)",
              background: activeTab === tab.id ? "oklch(0.155 0.015 264)" : "transparent",
              border: activeTab === tab.id ? "1px solid oklch(0.28 0.015 264)" : "1px solid transparent",
              cursor: "pointer",
              transition: "all 0.15s ease",
              whiteSpace: "nowrap",
              height: "30px",
            }}
          >
            <span style={{ fontSize: "0.8rem", opacity: 0.8 }}>{tab.icon}</span>
            {tab.label}
          </button>
        ))}
      </nav>
    </header>
  );
}
