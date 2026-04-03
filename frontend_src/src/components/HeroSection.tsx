// Design: Dark Cybersecurity Terminal — deep blue-black background, electric blue accents
// Hero section with animated background and key metrics

interface HeroSectionProps {
  onEnterDashboard: () => void;
}

export default function HeroSection({ onEnterDashboard }: HeroSectionProps) {
  return (
    <div
      style={{
        position: "relative",
        minHeight: "100vh",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        overflow: "hidden",
        background: "oklch(0.085 0.012 264)",
      }}
    >
      {/* Background image */}
      <div
        style={{
          position: "absolute",
          inset: 0,
          backgroundImage: `url(https://d2xsxph8kpxj0f.cloudfront.net/310419663026815100/fr2LxNAETyX9wVtPpFkWyC/hero_bg-2TssdPydGVG92hMH5RXCNB.webp)`,
          backgroundSize: "cover",
          backgroundPosition: "center",
          opacity: 0.25,
        }}
      />

      {/* Gradient overlay */}
      <div
        style={{
          position: "absolute",
          inset: 0,
          background: "linear-gradient(to bottom, oklch(0.085 0.012 264 / 0.4) 0%, oklch(0.085 0.012 264 / 0.7) 60%, oklch(0.085 0.012 264) 100%)",
        }}
      />

      {/* Grid pattern overlay */}
      <div
        style={{
          position: "absolute",
          inset: 0,
          backgroundImage: `
            linear-gradient(oklch(0.57 0.19 258 / 0.04) 1px, transparent 1px),
            linear-gradient(90deg, oklch(0.57 0.19 258 / 0.04) 1px, transparent 1px)
          `,
          backgroundSize: "40px 40px",
        }}
      />

      {/* Content */}
      <div
        style={{
          position: "relative",
          zIndex: 1,
          textAlign: "center",
          maxWidth: "900px",
          padding: "0 2rem",
          animation: "fadeIn 0.8s ease",
        }}
      >
        {/* Badge */}
        <div
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: "8px",
            padding: "6px 16px",
            borderRadius: "20px",
            border: "1px solid oklch(0.57 0.19 258 / 0.4)",
            background: "oklch(0.57 0.19 258 / 0.1)",
            marginBottom: "1.5rem",
          }}
        >
          <span
            style={{
              width: "7px",
              height: "7px",
              borderRadius: "50%",
              background: "oklch(0.65 0.18 155)",
              boxShadow: "0 0 8px oklch(0.65 0.18 155)",
              animation: "pulse-dot 2s infinite",
            }}
          />
          <span
            style={{
              fontFamily: "var(--font-mono)",
              fontSize: "0.75rem",
              fontWeight: 600,
              color: "oklch(0.72 0.18 155)",
              letterSpacing: "0.08em",
            }}
          >
            网络技术挑战赛 · AI 安全赛道
          </span>
        </div>

        {/* Title */}
        <h1
          style={{
            fontFamily: "var(--font-display)",
            fontSize: "clamp(2.5rem, 6vw, 4.5rem)",
            fontWeight: 700,
            lineHeight: 1.1,
            marginBottom: "1rem",
            letterSpacing: "-0.02em",
          }}
        >
          <span style={{ color: "oklch(0.91 0.008 250)" }}>Refusal</span>
          <span
            style={{
              color: "oklch(0.57 0.19 258)",
              textShadow: "0 0 40px oklch(0.57 0.19 258 / 0.4)",
            }}
          >
            Guard
          </span>
        </h1>

        {/* Subtitle */}
        <p
          style={{
            fontFamily: "var(--font-body)",
            fontSize: "clamp(1rem, 2vw, 1.25rem)",
            color: "oklch(0.65 0.01 250)",
            lineHeight: 1.6,
            marginBottom: "0.75rem",
            maxWidth: "600px",
            margin: "0 auto 0.75rem",
          }}
        >
          基于 LLM-Judge 的智能提示注入防御网关
        </p>
        <p
          style={{
            fontFamily: "var(--font-mono)",
            fontSize: "0.85rem",
            color: "oklch(0.45 0.015 264)",
            marginBottom: "2.5rem",
          }}
        >
          DeBERTa-v3 · Safety Judge · PIGuard MOF · 共形预测阈值 · RAG 沙箱隔离
        </p>

        {/* Key metrics */}
        <div
          style={{
            display: "flex",
            gap: "1.5rem",
            justifyContent: "center",
            marginBottom: "2.5rem",
            flexWrap: "wrap",
          }}
        >
          {[
            { value: "91.6%", label: "F1 分数", color: "oklch(0.57 0.19 258)" },
            { value: "3.73%", label: "误报率", color: "oklch(0.65 0.18 155)" },
            { value: "10,064", label: "训练样本", color: "oklch(0.72 0.17 80)" },
            { value: "< 300ms", label: "检测延迟", color: "oklch(0.60 0.18 290)" },
          ].map((m) => (
            <div
              key={m.label}
              style={{
                padding: "0.875rem 1.5rem",
                borderRadius: "10px",
                border: `1px solid ${m.color}30`,
                background: `${m.color}08`,
                textAlign: "center",
                minWidth: "110px",
              }}
            >
              <div
                style={{
                  fontFamily: "var(--font-mono)",
                  fontSize: "1.5rem",
                  fontWeight: 700,
                  color: m.color,
                  lineHeight: 1.1,
                  marginBottom: "4px",
                }}
              >
                {m.value}
              </div>
              <div style={{ fontSize: "0.72rem", color: "oklch(0.45 0.015 264)", fontFamily: "var(--font-body)" }}>
                {m.label}
              </div>
            </div>
          ))}
        </div>

        {/* CTA Button */}
        <button
          onClick={onEnterDashboard}
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: "10px",
            padding: "14px 36px",
            borderRadius: "10px",
            background: "oklch(0.57 0.19 258)",
            color: "white",
            fontFamily: "var(--font-display)",
            fontWeight: 600,
            fontSize: "1rem",
            border: "none",
            cursor: "pointer",
            boxShadow: "0 0 30px oklch(0.57 0.19 258 / 0.3)",
            transition: "all 0.2s ease",
            letterSpacing: "0.01em",
          }}
          onMouseEnter={(e) => {
            (e.target as HTMLButtonElement).style.transform = "translateY(-2px)";
            (e.target as HTMLButtonElement).style.boxShadow = "0 0 40px oklch(0.57 0.19 258 / 0.5)";
          }}
          onMouseLeave={(e) => {
            (e.target as HTMLButtonElement).style.transform = "translateY(0)";
            (e.target as HTMLButtonElement).style.boxShadow = "0 0 30px oklch(0.57 0.19 258 / 0.3)";
          }}
        >
          <span>进入控制台</span>
          <span style={{ fontSize: "1.1rem" }}>→</span>
        </button>

        <div style={{ marginTop: "1rem", fontSize: "0.72rem", color: "oklch(0.32 0.015 264)", fontFamily: "var(--font-mono)" }}>
          或向下滚动了解更多
        </div>
      </div>

      {/* Attack flow image */}
      <div
        style={{
          position: "absolute",
          bottom: 0,
          left: 0,
          right: 0,
          height: "220px",
          backgroundImage: `url(https://d2xsxph8kpxj0f.cloudfront.net/310419663026815100/fr2LxNAETyX9wVtPpFkWyC/attack_flow-WU6ZG3CuwX2NjJehT9Ru7R.webp)`,
          backgroundSize: "cover",
          backgroundPosition: "center top",
          opacity: 0.15,
          maskImage: "linear-gradient(to bottom, transparent, oklch(0 0 0 / 0.8))",
          WebkitMaskImage: "linear-gradient(to bottom, transparent, oklch(0 0 0 / 0.8))",
        }}
      />
    </div>
  );
}
