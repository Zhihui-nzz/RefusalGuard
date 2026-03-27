import time
import sqlite3
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, field_validator
from typing import Optional, List
from loguru import logger

from backend.config import settings
from backend.modules.preprocessor import Preprocessor
from backend.modules.detector import DualChannelDetector
from backend.modules.knowledge_base import KnowledgeBaseModule
from backend.modules.decision_engine import DecisionEngine
from backend.modules.refusal_generator import RefusalGenerator
from backend.modules.context_detector import ContextDetector

# ── 全局模块实例 ────────────────────────────────────────────────────
preprocessor    = None
detector        = None
kb_module       = None
decision_engine = None
refusal_gen     = None
context_det     = None
db_conn         = None

# 运行时指标（内存级，重启清零）
_metrics = {
    "total_requests": 0,
    "block_count":    0,
    "warn_count":     0,
    "pass_count":     0,
    "total_latency":  0.0,
    "start_time":     time.time(),
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用启动时加载所有模块，关闭时释放资源"""
    global preprocessor, detector, kb_module, decision_engine
    global refusal_gen, context_det, db_conn

    logger.info("=== RefusalGuard v2.1 启动中 ===")

    # M1: 预处理
    preprocessor = Preprocessor()
    logger.info("M1 预处理模块加载完成")

    # M2: 双通道检测器（含模型预热）
    detector = DualChannelDetector()
    logger.info("M2 双通道检测器加载完成")

    # M3: 知识库（加载失败自动降级）
    kb_module = KnowledgeBaseModule()
    if kb_module._degraded:
        logger.warning("M3 知识库降级运行（ChromaDB 未初始化）")
    else:
        logger.info("M3 知识库模块加载完成")

    # M4 & M5
    decision_engine = DecisionEngine()
    refusal_gen     = RefusalGenerator()
    logger.info("M4 决策引擎 + M5 拒答生成器加载完成")

    # 多轮上下文检测器
    context_det = ContextDetector()
    logger.info("多轮上下文检测器加载完成")

    # SQLite 日志数据库（字段扩展）
    import os
    os.makedirs(str(settings.log_dir), exist_ok=True)
    db_conn = sqlite3.connect(
        str(settings.db_path), check_same_thread=False
    )
    db_conn.execute("""
        CREATE TABLE IF NOT EXISTS detections (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp        TEXT,
            user_id          TEXT,
            prompt_hash      TEXT,
            prompt_preview   TEXT,
            decision         TEXT,
            risk_score       REAL,
            injection_score  REAL,
            kb_confidence    REAL,
            context_risk     REAL,
            zh_rule_score    REAL,
            detection_path   TEXT,
            latency_ms       REAL,
            llm_generated    INTEGER DEFAULT 0,
            fast_path        INTEGER DEFAULT 0
        )
    """)
    db_conn.commit()
    logger.info("=== RefusalGuard v2.1 启动完成 ===")

    yield

    if db_conn:
        db_conn.close()
    logger.info("=== RefusalGuard 已关闭 ===")


app = FastAPI(
    title="RefusalGuard API",
    description="基于大模型拒答能力的智能提示注入防御网关 v2.1",
    version="2.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── 全局异常处理 ────────────────────────────────────────────────────
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"未处理异常 {request.url}: {exc}")
    return JSONResponse(
        status_code=500,
        content={"detail": "服务内部错误，请稍后重试"},
    )


# ── 请求/响应模型 ────────────────────────────────────────────────────
class DetectRequest(BaseModel):
    prompt:     str
    user_id:    Optional[str]   = "anonymous"
    context:    Optional[str]   = ""
    user_trust: Optional[float] = 0.5

    @field_validator("prompt")
    @classmethod
    def prompt_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("prompt 不能为空")
        return v


class DetectResponse(BaseModel):
    decision:        str
    risk_score:      float
    breakdown:       dict
    refusal_message: str
    explanation:     str
    detection_path:  str
    latency_ms:      float
    llm_generated:   bool = False


class ChatMessage(BaseModel):
    role:    str
    content: str


class ChatRequest(BaseModel):
    messages:   List[ChatMessage]
    user_id:    Optional[str]   = "anonymous"
    user_trust: Optional[float] = 0.5
    model:      Optional[str]   = None  # None 则使用 settings.llm_model


class ChatResponse(BaseModel):
    reply:           str
    blocked:         bool
    detection:       Optional[dict] = None


# ── 核心检测接口 ────────────────────────────────────────────────────
@app.post("/api/v1/detect", response_model=DetectResponse)
async def detect(request: DetectRequest):
    start = time.time()

    # M1: 预处理
    preprocessed = preprocessor.process(request.prompt)

    # M2: 双通道检测
    detection = detector.detect(preprocessed.cleaned, preprocessed.quick_flags)

    # M3: 知识边界感知
    kb_confidence = kb_module.query(preprocessed.cleaned).kb_confidence

    # 多轮上下文风险
    context_risk = context_det.get_session_risk(request.user_id or "anonymous")

    # M4: 决策（传入 zh_rule_score 和 context_risk）
    zh_rule_score = preprocessed.features.get("zh_rule_score", 0.0)
    decision_result = decision_engine.decide(
        injection_score=detection.injection_score,
        kb_confidence=kb_confidence,
        user_trust=request.user_trust or 0.5,
        context_risk=context_risk,
        zh_rule_score=zh_rule_score,
    )

    # 更新多轮上下文（记录本轮风险）
    context_det.add_turn(
        user_id=request.user_id or "anonymous",
        prompt=request.prompt,
        risk_score=decision_result.risk_score,
    )

    # M5: 拒答生成
    refusal = refusal_gen.generate(decision_result, detection, preprocessed)

    total_latency = (time.time() - start) * 1000

    # 写入日志
    _log_detection(request, detection, decision_result, refusal, kb_confidence,
                   context_risk, zh_rule_score, total_latency)

    # 更新内存指标
    _update_metrics(decision_result.decision.value, total_latency)

    return DetectResponse(
        decision=decision_result.decision.value,
        risk_score=decision_result.risk_score,
        breakdown=decision_result.breakdown,
        refusal_message=refusal.message,
        explanation=refusal.explanation,
        detection_path=detection.detection_path,
        latency_ms=total_latency,
        llm_generated=refusal.llm_generated,
    )


# ── 带防护层的 LLM 对话代理 ─────────────────────────────────────────
@app.post("/api/v1/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    带安全防护层的 LLM 对话接口
    流程：检测最新一条用户消息 → BLOCK 则直接返回拒答 → 否则转发给 LLM
    """
    if not settings.llm_enabled:
        raise HTTPException(
            status_code=503,
            detail="LLM 未启用，请在 .env 中设置 LLM_ENABLED=true 并启动 Ollama",
        )

    # 找到最新一条 user 消息
    user_messages = [m for m in request.messages if m.role == "user"]
    if not user_messages:
        raise HTTPException(status_code=400, detail="消息列表中没有 user 角色的消息")

    latest_user_msg = user_messages[-1].content

    # 安全检测
    detect_req = DetectRequest(
        prompt=latest_user_msg,
        user_id=request.user_id,
        user_trust=request.user_trust,
    )
    detect_resp = await detect(detect_req)

    # 如果被拦截，直接返回拒答
    if detect_resp.decision == "BLOCK":
        return ChatResponse(
            reply=detect_resp.refusal_message or "该请求已被安全网关拦截。",
            blocked=True,
            detection={
                "decision":       detect_resp.decision,
                "risk_score":     detect_resp.risk_score,
                "injection_score": detect_resp.breakdown.get("injection_score", 0),
                "detection_path": detect_resp.detection_path,
            },
        )

    # 转发给 LLM
    try:
        from openai import OpenAI
        import httpx

        client = OpenAI(
            base_url=settings.llm_base_url,
            api_key=settings.llm_api_key,
            timeout=settings.llm_timeout_sec,
            http_client=httpx.Client(timeout=settings.llm_timeout_sec),
        )
        model = request.model or settings.llm_model
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": m.role, "content": m.content} for m in request.messages],
            max_tokens=1024,
            temperature=0.7,
        )
        reply = response.choices[0].message.content.strip()

        return ChatResponse(
            reply=reply,
            blocked=False,
            detection={
                "decision":       detect_resp.decision,
                "risk_score":     detect_resp.risk_score,
                "injection_score": detect_resp.breakdown.get("injection_score", 0),
                "detection_path": detect_resp.detection_path,
            },
        )

    except Exception as e:
        logger.error(f"/chat LLM 调用失败: {e}")
        raise HTTPException(status_code=502, detail=f"LLM 服务不可用: {str(e)}")


# ── 健康检查 ────────────────────────────────────────────────────────
@app.get("/api/v1/health")
async def health():
    import torch
    gpu_info = "cpu"
    if torch.cuda.is_available():
        props = torch.cuda.get_device_properties(0)
        used  = torch.cuda.memory_allocated(0) / 1024**3
        total = props.total_memory / 1024**3
        gpu_info = f"cuda:{props.name} ({used:.1f}/{total:.1f}GB)"
    return {
        "status":       "ok",
        "gpu":          gpu_info,
        "llm_enabled":  settings.llm_enabled,
        "llm_provider": settings.llm_provider if settings.llm_enabled else "disabled",
        "kb_status":    "degraded" if (kb_module and kb_module._degraded) else "ok",
        "version":      "2.1.0",
    }


# ── 统计接口 ────────────────────────────────────────────────────────
@app.get("/api/v1/stats")
async def stats():
    """返回检测统计数据（用于仪表盘）"""
    if not db_conn:
        return {}
    cursor = db_conn.execute("""
        SELECT decision, COUNT(*) as count,
               AVG(risk_score) as avg_risk,
               AVG(latency_ms) as avg_latency
        FROM detections GROUP BY decision
    """)
    rows = cursor.fetchall()
    return {
        "by_decision": [
            {"decision": r[0], "count": r[1], "avg_risk": r[2], "avg_latency": r[3]}
            for r in rows
        ]
    }


# ── Prometheus 风格指标接口 ──────────────────────────────────────────
@app.get("/api/v1/metrics")
async def metrics():
    """返回运行时指标，可对接 Grafana/Prometheus"""
    total = _metrics["total_requests"]
    avg_latency = (
        _metrics["total_latency"] / total if total > 0 else 0.0
    )
    uptime = time.time() - _metrics["start_time"]
    return {
        "total_requests": total,
        "block_count":    _metrics["block_count"],
        "warn_count":     _metrics["warn_count"],
        "pass_count":     _metrics["pass_count"],
        "block_rate":     round(_metrics["block_count"] / max(total, 1), 4),
        "avg_latency_ms": round(avg_latency, 2),
        "uptime_seconds": round(uptime, 1),
    }


# ── 内部辅助函数 ────────────────────────────────────────────────────
def _log_detection(request, detection, decision_result, refusal,
                   kb_confidence, context_risk, zh_rule_score, latency_ms):
    """写入 SQLite 日志"""
    if not db_conn:
        return
    import hashlib
    prompt_hash = hashlib.sha256(request.prompt.encode()).hexdigest()[:16]
    try:
        db_conn.execute(
            """INSERT INTO detections
               (timestamp, user_id, prompt_hash, prompt_preview,
                decision, risk_score, injection_score, kb_confidence,
                context_risk, zh_rule_score, detection_path, latency_ms,
                llm_generated, fast_path)
               VALUES (datetime('now'), ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                request.user_id,
                prompt_hash,
                request.prompt[:200],
                decision_result.decision.value,
                decision_result.risk_score,
                detection.injection_score,
                kb_confidence,
                context_risk,
                zh_rule_score,
                detection.detection_path,
                latency_ms,
                int(refusal.llm_generated),
                int(decision_result.breakdown.get("fast_path", False)),
            ),
        )
        db_conn.commit()
    except Exception as e:
        logger.error(f"日志写入失败: {e}")


def _update_metrics(decision: str, latency_ms: float):
    """更新内存级运行时指标"""
    _metrics["total_requests"] += 1
    _metrics["total_latency"]  += latency_ms
    if decision == "BLOCK":
        _metrics["block_count"] += 1
    elif decision == "WARN":
        _metrics["warn_count"]  += 1
    else:
        _metrics["pass_count"]  += 1
