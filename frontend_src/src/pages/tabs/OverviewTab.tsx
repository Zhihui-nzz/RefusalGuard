import { useState, useEffect, useRef, useCallback } from "react";
import {
  AreaChart, Area, BarChart, Bar, XAxis, YAxis, Tooltip,
  ResponsiveContainer, PieChart, Pie, Cell, RadarChart,
  PolarGrid, PolarAngleAxis, Radar, CartesianGrid, Legend,
} from "recharts";
import { MODEL_PERFORMANCE, EVAL_DIMENSIONS, CHANNEL_PERFORMANCE, DATASET_STATS } from "@/lib/mockData";

// ── 动画数字组件 ──────────────────────────────────────────────────────────────
function AnimatedNumber({ value, decimals = 0, suffix = "" }: { value: number; decimals?: number; suffix?: string }) {
  const [display, setDisplay] = useState(0);
  const rafRef = useRef<number>(0);

  useEffect(() => {
    const start = 0;
    const end = value;
    const duration = 1200;
    const startTime = performance.now();

    const animate = (now: number) => {
      const elapsed = now - startTime;
      const progress = Math.min(elapsed / duration, 1);
      const eased = 1 - Math.pow(1 - progress, 3);
      setDisplay(start + (end - start) * eased);
      if (progress < 1) rafRef.current = requestAnimationFrame(animate);
    };

    rafRef.current = requestAnimationFrame(animate);
    return () => cancelAnimationFrame(rafRef.current);
  }, [value]);

  return (
    <span>
      {display.toFixed(decimals)}
      {suffix}
    </span>
  );
}

// ── 风险仪表盘 ────────────────────────────────────────────────────────────────
function RiskGauge({ value, label, color }: { value: number; label: string; color: string }) {
  const circumference = 2 * Math.PI * 40;
  const offset = circumference * (1 - value);

  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: "0.5rem" }}>
      <svg width="100" height="100" viewBox="0 0 100 100">
        <circle cx="50" cy="50" r="40" fill="none" stroke="oklch(0.22 0.015 264)" strokeWidth="8" />
        <circle
          cx="50" cy="50" r="40"
          fill="none"
          stroke={color}
          strokeWidth="8"
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          strokeLinecap="round"
          transform="rotate(-90 50 50)"
          style={{ transition: "stroke-dashoffset 1.2s cubic-bezier(0.4,0,0.2,1)" }}
        />
        <text x="50" y="46" textAnchor="middle" fill="oklch(0.91 0.008 250)" fontSize="16" fontWeight="700" fontFamily="var(--font-mono)">
          {(value * 100).toFixed(1)}
        </text>
        <text x="50" y="60" textAnchor="middle" fill="oklch(0.52 0.015 264)" fontSize="8" fontFamily="var(--font-mono)">
          %
        </text>
      </svg>
      <div style={{ fontSize: "0.78rem", color: "oklch(0.58 0.015 264)", fontFamily: "var(--font-body)" }}>
        {label}
      </div>
    </div>
  );
}

// ── 指标卡片 ──────────────────────────────────────────────────────────────────
function MetricCard({
  label, value, sub, accentColor, decimals = 0, suffix = "",
}: {
  label: string; value: number; sub?: string; accentColor: string; decimals?: number; suffix?: string;
}) {
  return (
    <div
      className="metric-card"
      style={{ "--accent-line": accentColor } as React.CSSProperties}
    >
      <div style={{ fontSize: "0.75rem", color: "oklch(0.52 0.015 264)", marginBottom: "0.5rem", fontFamily: "var(--font-body)" }}>
        {label}
      </div>
      <div
        style={{
          fontSize: "1.8rem",
          fontWeight: 700,
          fontFamily: "var(--font-mono)",
          color: "oklch(0.91 0.008 250)",
          lineHeight: 1.1,
        }}
      >
        <AnimatedNumber value={value} decimals={decimals} suffix={suffix} />
      </div>
      {sub && (
        <div style={{ fontSize: "0.72rem", color: "oklch(0.45 0.015 264)", marginTop: "0.25rem", fontFamily: "var(--font-body)" }}>
          {sub}
        </div>
      )}
    </div>
  );
}

// // ── 实时流量图（后端在线时调用 /metrics 真实数据，离线时用演示数据）────────────────────
function generateTrafficPoint(t: number) {
  const base = 12;
  const hour = new Date().getHours();
  const daytime = hour >= 9 && hour <= 22 ? 1.5 : 0.7;
  return {
    time: new Date(t).toLocaleTimeString("zh-CN", { hour12: false, hour: "2-digit", minute: "2-digit", second: "2-digit" }),
    total: Math.round((base + Math.random() * 8) * daytime),
    blocked: Math.round((2 + Math.random() * 3) * daytime),
    warned: Math.round((1 + Math.random() * 2) * daytime),
  };
}

interface MetricsSnapshot {
  total_requests: number;
  block_count: number;
  warn_count: number;
  pass_count: number;
}

function TrafficChart() {
  const [isRealData, setIsRealData] = useState(false);
  const [data, setData] = useState(() => {
    const now = Date.now();
    return Array.from({ length: 20 }, (_, i) =>
      generateTrafficPoint(now - (19 - i) * 30000)
    );
  });
  // 用于计算增量的上一次快照
  const prevSnapshot = useRef<MetricsSnapshot | null>(null);

  useEffect(() => {
    let demoInterval: ReturnType<typeof setInterval> | null = null;
    let realInterval: ReturnType<typeof setInterval> | null = null;

    const fetchRealData = async () => {
      try {
        const res = await fetch("http://localhost:8000/api/v1/metrics", {
          signal: AbortSignal.timeout(3000),
        });
        if (!res.ok) throw new Error("not ok");
        const m: MetricsSnapshot = await res.json();
        const now = new Date().toLocaleTimeString("zh-CN", { hour12: false, hour: "2-digit", minute: "2-digit", second: "2-digit" });

        if (prevSnapshot.current) {
          const prev = prevSnapshot.current;
          const deltaTotal   = Math.max(0, m.total_requests - prev.total_requests);
          const deltaBlocked = Math.max(0, m.block_count    - prev.block_count);
          const deltaWarned  = Math.max(0, m.warn_count     - prev.warn_count);
          setData((prev) => [...prev.slice(-19), { time: now, total: deltaTotal, blocked: deltaBlocked, warned: deltaWarned }]);
        } else {
          // 第一次拉取：用全量初始化图表（最后一个点显示全量）
          const now2 = Date.now();
          const initData = Array.from({ length: 19 }, (_, i) =>
            generateTrafficPoint(now2 - (18 - i) * 5000)
          );
          initData.push({ time: now, total: m.total_requests, blocked: m.block_count, warned: m.warn_count });
          setData(initData);
        }
        prevSnapshot.current = m;
        setIsRealData(true);
      } catch {
        setIsRealData(false);
      }
    };

    // 先尝试连接后端
    fetchRealData().then(() => {
      if (prevSnapshot.current !== null) {
        // 后端在线：每 5 秒轮询真实数据
        realInterval = setInterval(fetchRealData, 5000);
      } else {
        // 后端离线：每 3 秒生成演示数据
        demoInterval = setInterval(() => {
          setData((prev) => [...prev.slice(-19), generateTrafficPoint(Date.now())]);
        }, 3000);
        // 每 15 秒重试连接
        const retryInterval = setInterval(async () => {
          await fetchRealData();
          if (prevSnapshot.current !== null) {
            clearInterval(demoInterval!);
            clearInterval(retryInterval);
            realInterval = setInterval(fetchRealData, 5000);
          }
        }, 15000);
        return () => { clearInterval(demoInterval!); clearInterval(retryInterval); };
      }
    });

    return () => {
      if (demoInterval) clearInterval(demoInterval);
      if (realInterval) clearInterval(realInterval);
    };
  }, []);

  const totalBlocked = data.reduce((s, d) => s + d.blocked, 0);
  const totalRequests = data.reduce((s, d) => s + d.total, 0);

  return (
    <div
      style={{
        background: "oklch(0.115 0.014 264)",
        border: "1px solid oklch(0.22 0.015 264)",
        borderRadius: "10px",
        padding: "1.25rem",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "0.75rem" }}>
        <div className="section-header" style={{ marginBottom: 0 }}>
          <span style={{ fontFamily: "var(--font-display)", fontWeight: 600, fontSize: "0.9rem", color: "oklch(0.91 0.008 250)" }}>
            实时流量监控
            <span style={{ marginLeft: "0.5rem", fontSize: "0.7rem", padding: "2px 7px", borderRadius: "4px", fontFamily: "var(--font-mono)", background: isRealData ? "oklch(0.65 0.18 155 / 0.15)" : "oklch(0.62 0.22 25 / 0.12)", color: isRealData ? "oklch(0.65 0.18 155)" : "oklch(0.62 0.22 25)" }}>
              {isRealData ? "• 真实数据" : "○ 演示数据"}
            </span>
          </span>
        </div>
        <div style={{ display: "flex", gap: "1.5rem" }}>
          {[
            { label: "请求总量", value: totalRequests, color: "oklch(0.57 0.19 258)" },
            { label: "已拦截", value: totalBlocked, color: "oklch(0.62 0.22 25)" },
            { label: "拦截率", value: `${totalRequests > 0 ? ((totalBlocked / totalRequests) * 100).toFixed(1) : 0}%`, color: "oklch(0.72 0.17 80)" },
          ].map((s) => (
            <div key={s.label} style={{ textAlign: "right" }}>
              <div style={{ fontSize: "1rem", fontWeight: 700, fontFamily: "var(--font-mono)", color: s.color }}>{s.value}</div>
              <div style={{ fontSize: "0.65rem", color: "oklch(0.42 0.015 264)", fontFamily: "var(--font-body)" }}>{s.label}</div>
            </div>
          ))}
        </div>
      </div>
      <ResponsiveContainer width="100%" height={140}>
        <AreaChart data={data} margin={{ top: 5, right: 5, left: -20, bottom: 0 }}>
          <defs>
            <linearGradient id="gradTotal" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="oklch(0.57 0.19 258)" stopOpacity={0.3} />
              <stop offset="95%" stopColor="oklch(0.57 0.19 258)" stopOpacity={0} />
            </linearGradient>
            <linearGradient id="gradBlocked" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="oklch(0.62 0.22 25)" stopOpacity={0.4} />
              <stop offset="95%" stopColor="oklch(0.62 0.22 25)" stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid stroke="oklch(0.18 0.015 264)" strokeDasharray="3 3" />
          <XAxis dataKey="time" tick={{ fill: "oklch(0.38 0.015 264)", fontSize: 9, fontFamily: "var(--font-mono)" }} interval={4} />
          <YAxis tick={{ fill: "oklch(0.38 0.015 264)", fontSize: 9, fontFamily: "var(--font-mono)" }} />
          <Tooltip contentStyle={CUSTOM_TOOLTIP_STYLE} />
          <Area type="monotone" dataKey="total" stroke="oklch(0.57 0.19 258)" fill="url(#gradTotal)" strokeWidth={1.5} name="总请求" />
          <Area type="monotone" dataKey="blocked" stroke="oklch(0.62 0.22 25)" fill="url(#gradBlocked)" strokeWidth={1.5} name="已拦截" />
          <Area type="monotone" dataKey="warned" stroke="oklch(0.72 0.17 80)" fill="none" strokeWidth={1} strokeDasharray="4 2" name="警告" />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

const RADAR_DATA = [
  { subject: "攻击检出率", value: 100 },
  { subject: "误报控制", value: 96.3 },
  { subject: "漂移检测", value: 80 },
  { subject: "RAG 防护", value: 87.5 },
  { subject: "响应速度", value: 95 },
  { subject: "Judge 精度", value: 91.6 },
];

const PIE_DATA = [
  { name: "benign", value: 6802, color: "oklch(0.65 0.18 155)" },
  { name: "injection", value: 2986, color: "oklch(0.62 0.22 25)" },
  { name: "harmful", value: 276, color: "oklch(0.72 0.17 80)" },
];

const SOURCE_DATA = Object.entries(DATASET_STATS.source_distribution).map(([k, v]) => ({
  name: k.split("/").pop() || k,
  value: v,
}));

const CUSTOM_TOOLTIP_STYLE = {
  background: "oklch(0.115 0.014 264)",
  border: "1px solid oklch(0.25 0.015 264)",
  borderRadius: "6px",
  padding: "8px 12px",
  fontFamily: "var(--font-mono)",
  fontSize: "0.78rem",
  color: "oklch(0.91 0.008 250)",
};

export default function OverviewTab() {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1.5rem" }}>

      {/* ── 核心指标行 ─────────────────────────────────────────────────── */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: "1rem" }}>
        <MetricCard
          label="Safety Judge F1 分数"
          value={MODEL_PERFORMANCE.f1 * 100}
          decimals={1}
          suffix="%"
          sub="DeBERTa-v3-base 三分类"
          accentColor="oklch(0.57 0.19 258)"
        />
        <MetricCard
          label="测试集准确率"
          value={MODEL_PERFORMANCE.accuracy * 100}
          decimals={1}
          suffix="%"
          sub="200 条混合测试集"
          accentColor="oklch(0.65 0.18 155)"
        />
        <MetricCard
          label="误报率 (FPR)"
          value={MODEL_PERFORMANCE.false_positive_rate * 100}
          decimals={2}
          suffix="%"
          sub="正常请求被误拦截率"
          accentColor="oklch(0.72 0.17 80)"
        />
        <MetricCard
          label="训练数据总量"
          value={DATASET_STATS.total}
          sub="4 个公开数据集"
          accentColor="oklch(0.60 0.18 290)"
        />
      </div>

      {/* ── 实时流量监控 ────────────────────────────────────────────────────── */}
      <TrafficChart />

      {/* ── 第二行：仪表盘 + 雷达图 ────────────────────────────────────────────── */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1rem" }}>

        {/* 精确率/召回率/F1 仪表盘 */}
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
              Safety Judge 核心指标
            </span>
          </div>
          <div style={{ display: "flex", justifyContent: "space-around", alignItems: "center", padding: "0.5rem 0" }}>
            <RiskGauge value={MODEL_PERFORMANCE.precision} label="精确率" color="oklch(0.57 0.19 258)" />
            <RiskGauge value={MODEL_PERFORMANCE.recall} label="召回率" color="oklch(0.65 0.18 155)" />
            <RiskGauge value={MODEL_PERFORMANCE.f1} label="F1 分数" color="oklch(0.72 0.17 80)" />
            <RiskGauge value={MODEL_PERFORMANCE.specificity} label="特异性" color="oklch(0.60 0.18 290)" />
          </div>
          <div
            style={{
              marginTop: "1rem",
              padding: "0.75rem",
              background: "oklch(0.09 0.012 264)",
              borderRadius: "6px",
              display: "grid",
              gridTemplateColumns: "repeat(4, 1fr)",
              gap: "0.5rem",
              textAlign: "center",
            }}
          >
            {[
              { label: "TP", value: MODEL_PERFORMANCE.tp, color: "oklch(0.65 0.18 155)" },
              { label: "FP", value: MODEL_PERFORMANCE.fp, color: "oklch(0.62 0.22 25)" },
              { label: "TN", value: MODEL_PERFORMANCE.tn, color: "oklch(0.65 0.18 155)" },
              { label: "FN", value: MODEL_PERFORMANCE.fn, color: "oklch(0.72 0.17 80)" },
            ].map((item) => (
              <div key={item.label}>
                <div style={{ fontSize: "0.68rem", color: "oklch(0.45 0.015 264)", fontFamily: "var(--font-mono)" }}>
                  {item.label}
                </div>
                <div style={{ fontSize: "1.2rem", fontWeight: 700, fontFamily: "var(--font-mono)", color: item.color }}>
                  {item.value}
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* 系统能力雷达图 */}
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
              系统综合能力评估
            </span>
          </div>
          <ResponsiveContainer width="100%" height={200}>
            <RadarChart data={RADAR_DATA}>
              <PolarGrid stroke="oklch(0.22 0.015 264)" />
              <PolarAngleAxis
                dataKey="subject"
                tick={{ fill: "oklch(0.52 0.015 264)", fontSize: 11, fontFamily: "var(--font-body)" }}
              />
              <Radar
                name="能力"
                dataKey="value"
                stroke="oklch(0.57 0.19 258)"
                fill="oklch(0.57 0.19 258)"
                fillOpacity={0.2}
                strokeWidth={2}
              />
            </RadarChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* ── 第三行：通道性能 + 数据集分布 ─────────────────────────────── */}
      <div style={{ display: "grid", gridTemplateColumns: "3fr 2fr", gap: "1rem" }}>

        {/* 检测通道性能对比 */}
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
              检测通道性能对比
            </span>
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem", marginTop: "0.5rem" }}>
            {CHANNEL_PERFORMANCE.map((ch) => (
              <div key={ch.channel}>
                <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "4px" }}>
                  <span style={{ fontSize: "0.82rem", color: "oklch(0.78 0.01 250)", fontFamily: "var(--font-body)" }}>
                    {ch.channel}
                  </span>
                  <div style={{ display: "flex", gap: "1rem" }}>
                    {[
                      { label: "P", value: ch.precision, color: "oklch(0.57 0.19 258)" },
                      { label: "R", value: ch.recall, color: "oklch(0.65 0.18 155)" },
                      { label: "F1", value: ch.f1, color: "oklch(0.72 0.17 80)" },
                      { label: `${ch.latency}ms`, value: null, color: "oklch(0.45 0.015 264)" },
                    ].map((m) => (
                      <span key={m.label} style={{ fontSize: "0.72rem", fontFamily: "var(--font-mono)", color: m.color }}>
                        {m.value !== null ? `${m.label}=${(m.value * 100).toFixed(1)}%` : m.label}
                      </span>
                    ))}
                  </div>
                </div>
                <div className="signal-bar">
                  <div
                    className="signal-bar-fill"
                    style={{
                      width: `${ch.f1 * 100}%`,
                      background: `linear-gradient(90deg, oklch(0.57 0.19 258), oklch(0.65 0.18 155))`,
                    }}
                  />
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* 数据集分布 */}
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
              训练数据集分布
            </span>
          </div>
          <div style={{ display: "flex", justifyContent: "center" }}>
            <PieChart width={160} height={160}>
              <Pie
                data={PIE_DATA}
                cx={80} cy={80}
                innerRadius={45}
                outerRadius={70}
                paddingAngle={3}
                dataKey="value"
              >
                {PIE_DATA.map((entry, index) => (
                  <Cell key={index} fill={entry.color} />
                ))}
              </Pie>
              <Tooltip
                contentStyle={CUSTOM_TOOLTIP_STYLE}
                formatter={(v: number) => [v.toLocaleString(), ""]}
              />
            </PieChart>
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: "0.4rem" }}>
            {PIE_DATA.map((item) => (
              <div key={item.name} style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                <div style={{ width: "10px", height: "10px", borderRadius: "2px", background: item.color, flexShrink: 0 }} />
                <span style={{ fontSize: "0.78rem", color: "oklch(0.65 0.015 264)", fontFamily: "var(--font-body)", flex: 1 }}>
                  {item.name}
                </span>
                <span style={{ fontSize: "0.75rem", fontFamily: "var(--font-mono)", color: "oklch(0.78 0.01 250)" }}>
                  {item.value.toLocaleString()}
                </span>
              </div>
            ))}
          </div>
          <div
            style={{
              marginTop: "0.75rem",
              padding: "0.5rem",
              background: "oklch(0.09 0.012 264)",
              borderRadius: "5px",
              display: "flex",
              justifyContent: "space-between",
            }}
          >
            {[
              { label: "训练", value: DATASET_STATS.train },
              { label: "验证", value: DATASET_STATS.val },
              { label: "测试", value: DATASET_STATS.test },
            ].map((s) => (
              <div key={s.label} style={{ textAlign: "center" }}>
                <div style={{ fontSize: "0.68rem", color: "oklch(0.45 0.015 264)", fontFamily: "var(--font-mono)" }}>{s.label}</div>
                <div style={{ fontSize: "0.9rem", fontWeight: 600, fontFamily: "var(--font-mono)", color: "oklch(0.78 0.01 250)" }}>
                  {s.value.toLocaleString()}
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* ── 第四行：评估维度 ────────────────────────────────────────────── */}
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
            系统评估维度（6D 综合测试）
          </span>
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(6, 1fr)", gap: "0.75rem" }}>
          {EVAL_DIMENSIONS.map((dim) => (
            <div
              key={dim.name}
              style={{
                padding: "0.75rem",
                background: "oklch(0.09 0.012 264)",
                borderRadius: "8px",
                border: "1px solid oklch(0.2 0.015 264)",
                textAlign: "center",
              }}
            >
              <div
                style={{
                  fontSize: "1.4rem",
                  fontWeight: 700,
                  fontFamily: "var(--font-mono)",
                  color: dim.rate >= 0.9 ? "oklch(0.72 0.18 155)" : dim.rate >= 0.8 ? "oklch(0.78 0.17 80)" : "oklch(0.72 0.22 25)",
                  lineHeight: 1.1,
                }}
              >
                {(dim.rate * 100).toFixed(0)}%
              </div>
              <div style={{ fontSize: "0.65rem", color: "oklch(0.45 0.015 264)", fontFamily: "var(--font-mono)", marginTop: "2px" }}>
                {dim.passed}/{dim.total}
              </div>
              <div style={{ fontSize: "0.7rem", color: "oklch(0.58 0.015 264)", fontFamily: "var(--font-body)", marginTop: "4px", lineHeight: 1.3 }}>
                {dim.name}
              </div>
              <div style={{ marginTop: "6px" }} className="signal-bar">
                <div
                  className="signal-bar-fill"
                  style={{
                    width: `${dim.rate * 100}%`,
                    background: dim.rate >= 0.9
                      ? "oklch(0.65 0.18 155)"
                      : dim.rate >= 0.8
                      ? "oklch(0.72 0.17 80)"
                      : "oklch(0.62 0.22 25)",
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
