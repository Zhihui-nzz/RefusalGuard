// Design: Dark Cybersecurity Terminal
// Main Dashboard page — orchestrates Hero + Tab navigation + all sub-tabs
// v3.2: 删除提升方案页面，合并架构页面到模型页面，去除模拟数据
import { useState } from "react";
import TopNav from "@/components/TopNav";
import HeroSection from "@/components/HeroSection";
import OverviewTab from "./tabs/OverviewTab";
import ArenaTab from "./tabs/ArenaTab";
import ModelTab from "./tabs/ModelTab";
import LogsTab from "./tabs/LogsTab";

export default function Dashboard() {
  const [showDashboard, setShowDashboard] = useState(false);
  const [activeTab, setActiveTab] = useState("overview");

  if (!showDashboard) {
    return <HeroSection onEnterDashboard={() => setShowDashboard(true)} />;
  }

  return (
    <div
      style={{
        minHeight: "100vh",
        background: "oklch(0.085 0.012 264)",
        display: "flex",
        flexDirection: "column",
      }}
    >
      <TopNav activeTab={activeTab} onTabChange={setActiveTab} />

      <main
        style={{
          flex: 1,
          padding: "1.25rem 1.5rem",
          maxWidth: "1400px",
          width: "100%",
          margin: "0 auto",
          boxSizing: "border-box",
        }}
      >
        {activeTab === "overview" && <OverviewTab />}
        {activeTab === "arena" && <ArenaTab />}
        {activeTab === "model" && <ModelTab />}
        {activeTab === "logs" && <LogsTab />}
      </main>

      {/* Footer */}
      <footer
        style={{
          borderTop: "1px solid oklch(0.18 0.015 264)",
          padding: "0.75rem 1.5rem",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          fontSize: "0.68rem",
          fontFamily: "var(--font-mono)",
          color: "oklch(0.32 0.015 264)",
        }}
      >
        <span>RefusalGuard v3.2 · 智能提示注入防御网关</span>
        <span>DeBERTa-v3-base · Safety Judge (weight=0.40) · PIGuard · Conformal Prediction</span>
        <span>网络技术挑战赛 2025</span>
      </footer>
    </div>
  );
}
