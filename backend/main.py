"""RefusalGuard API 主入口。

接口列表：
  - POST /api/v1/detect      单轮提示词检测
  - POST /api/v1/rag_detect  RAG 场景间接注入检测
  - POST /api/v1/chat        带防护层的 LLM 对话（含知识边界感知）
  - POST /api/v1/calibrate   共形预测校准数据在线更新
  - GET  /api/v1/health      服务健康检查
  - GET  /api/v1/metrics     实时运行指标
  - GET  /api/v1/stats       历史统计数据
"""
import hashlib
import os
import sqlite3
import time
from contextlib import asynccontextmanager
from typing import Optional, List

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from loguru import logger
from pydantic import BaseModel, field_validator

from backend.config import settings
from backend.modules.preprocessor import Preprocessor
from backend.modules.detector import DualChannelDetector
from backend.modules.knowledge_base import KnowledgeBaseModule
from backend.modules.decision_engine import DecisionEngine, Decision
from backend.modules.refusal_generator import RefusalGenerator
from backend.modules.context_detector import ContextDetector
from backend.modules.rag_isolator import RAGIsolator
from backend.modules.conformal_threshold import ConformalThresholdCalibrator

# 全局模块实例
preprocessor       = None
detector           = None
kb_module          = None
decision_engine    = None
refusal_gen        = None
context_det        = None
rag_isolator_inst  = None
conformal_calib    = None
db_conn            = None

# 运行时指标（内存级，重启清零）
_metrics = {
    "total_requests":    0,
    "block_count":       0,
    "warn_count":        0,
    "pass_count":        0,
    "total_latency":     0.0,
    "probe_triggers":    0,
    "drift_triggers":    0,
    "rag_contaminations": 0,
    "start_time":        time.time(),
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用启动时加载所有模块，关闭时释放资源。"""
    global preprocessor, detector, kb_module, decision_engine
    global refusal_gen, context_det, rag_isolator_inst, conformal_calib, db_conn

    logger.info("=== RefusalGuard 启动中 ===")

    preprocessor = Preprocessor()
    logger.info("预处理模块（PIGuard MOF）加载完成")

    detector = DualChannelDetector()
    logger.info("双通道检测器加载完成")

    kb_module = KnowledgeBaseModule()
    if kb_module._degraded:
        logger.warning("知识库降级运行（ChromaDB 未初始化，请运行 build_knowledge_base.py）")
    else:
        logger.info("知识库模块加载完成")

    decision_engine = DecisionEngine()
    refusal_gen     = RefusalGenerator()
    logger.info("决策引擎 + 拒答生成器加载完成")

    context_det = ContextDetector()
    logger.info("多轮上下文检测器（意图漂移）加载完成")

    rag_isolator_inst = RAGIsolator()
    logger.info("RAG 注入隔离器（DRIFT）加载完成")

    conformal_calib = ConformalThresholdCalibrator()
    thresholds = conformal_calib.current_thresholds
    logger.info(
        f"共形预测阈值加载完成（方法={thresholds.method}，"
        f"BLOCK={thresholds.block_threshold:.4f}，WARN={thresholds.warn_threshold:.4f}）"
    )

    os.makedirs(str(settings.log_dir), exist_ok=True)
    db_conn = sqlite3.connect(str(settings.db_path), check_same_thread=False)
    db_conn.execute("""
        CREATE TABLE IF NOT EXISTS detections (
            id                   INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp            TEXT,
            user_id              TEXT,
            prompt_hash          TEXT,
            prompt_preview       TEXT,
            decision             TEXT,
            risk_score           REAL,
            injection_score      REAL,
            intent_score         REAL,
            benign_discount      REAL,
            kb_confidence        REAL,
            boundary_state       TEXT,
            probe_score          REAL,
            entropy_risk_bonus   REAL,
            rag_injection_score  REAL,
            drift_score          REAL,
            drift_direction      TEXT,
            context_risk         REAL,
            zh_rule_score        REAL,
            detection_path       TEXT,
            latency_ms           REAL,
            llm_generated        INTEGER DEFAULT 0,
            fast_path            INTEGER DEFAULT 0,
            threshold_method     TEXT DEFAULT 'fallback',
            triggered_signals    TEXT DEFAULT ''
        )
    """)
    db_conn.commit()
    logger.info("=== RefusalGuard 启动完成 ===")

    yield

    if db_conn:
        db_conn.close()
    if conformal_calib:
        conformal_calib.save_calibration_data()
    logger.info("=== RefusalGuard 已关闭 ===")


app = FastAPI(
    title="RefusalGuard API",
    description="基于大模型拒答能力的智能提示注入防御网关",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"未处理异常 {request.url}: {exc}")
    return JSONResponse(
        status_code=500,
        content={"detail": "服务内部错误，请稍后重试"},
    )


# ── 请求/响应模型 ─────────────────────────────────────────────────────────

class DetectRequest(BaseModel):
    prompt:              str
    user_id:             Optional[str]   = "anonymous"
    context:             Optional[str]   = ""
    user_trust:          Optional[float] = 0.5
    context_sensitivity: Optional[float] = 0.5

    @field_validator("prompt")
    @classmethod
    def prompt_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("prompt 不能为空")
        return v


class DetectResponse(BaseModel):
    decision:          str
    risk_score:        float
    breakdown:         dict
    refusal_message:   str
    explanation:       str
    detection_path:    str
    latency_ms:        float
    llm_generated:     bool  = False
    intent_score:      float = 0.0
    benign_discount:   float = 0.0
    boundary_state:    str   = "known"
    probe_triggered:   bool  = False
    drift_direction:   str   = "normal"
    triggered_signals: list  = []
    threshold_method:  str   = "fallback"
    judge_label:       Optional[str]   = None
    judge_confidence:  Optional[float] = None
    judge_scores:      Optional[list]  = None


class RAGDetectRequest(BaseModel):
    """RAG 场景间接注入检测请求。"""
    user_query:    str
    documents:     List[str]
    system_prompt: Optional[str]   = ""
    user_id:       Optional[str]   = "anonymous"
    user_trust:    Optional[float] = 0.5


class RAGDetectResponse(BaseModel):
    user_query_decision:     str
    user_query_risk:         float
    rag_isolation_result:    dict
    contaminated_count:      int
    max_doc_injection_score: float
    overall_safe:            bool
    refusal_message:         str


class ChatMessage(BaseModel):
    role:    str
    content: str


class ChatRequest(BaseModel):
    messages:   List[ChatMessage]
    user_id:    Optional[str]   = "anonymous"
    user_trust: Optional[float] = 0.5
    model:      Optional[str]   = None


class ChatResponse(BaseModel):
    reply:                        str
    blocked:                      bool
    detection:                    Optional[dict] = None
    knowledge_boundary_triggered: bool           = False


class CalibrateRequest(BaseModel):
    """共形预测在线校准请求。"""
    risk_score: float
    is_attack:  bool
    user_id:    Optional[str] = "system"


# ── 核心检测接口 ──────────────────────────────────────────────────────────

@app.post("/api/v1/detect", response_model=DetectResponse)
async def detect(request: DetectRequest):
    start = time.time()
    uid   = request.user_id or "anonymous"

    # M1: 预处理（PIGuard MOF）
    preprocessed = preprocessor.process(request.prompt)

    # M2: 双通道检测（意图得分 + 内部探针）
    detection = detector.detect(
        text=preprocessed.cleaned,
        preprocessed=preprocessed,
    )

    # M3: 知识库查询（攻击知识匹配 + 置信度校准）
    kb_result = kb_module.query(preprocessed.cleaned)

    # 多轮上下文风险（意图漂移）
    context_info    = context_det.get_combined_context_risk(uid)
    context_risk    = context_info["combined_risk"]
    drift_score     = context_info["drift_score"]
    drift_direction = context_info["drift_direction"]

    # 语义熵（可选模块）
    entropy_risk_bonus = 0.0
    if settings.semantic_entropy_enabled:
        try:
            from backend.modules.semantic_entropy import semantic_entropy_detector
            entropy_result     = semantic_entropy_detector.compute(preprocessed.cleaned)
            entropy_risk_bonus = entropy_result.entropy_risk_bonus
        except Exception as e:
            logger.debug(f"语义熵计算跳过: {e}")

    # M4: 决策引擎
    zh_rule_score   = preprocessed.features.get("zh_rule_score", 0.0)
    decision_result = decision_engine.decide(
        injection_score=detection.injection_score,
        kb_confidence=kb_result.kb_confidence,
        intent_score=detection.intent_score,
        benign_discount=detection.benign_discount,
        boundary_state=kb_result.boundary_state,
        boundary_risk_bonus=kb_result.boundary_risk_bonus,
        probe_score=detection.probe_score,
        probe_triggered=detection.probe_triggered,
        entropy_risk_bonus=entropy_risk_bonus,
        rag_injection_score=0.0,
        drift_score=drift_score,
        drift_direction=drift_direction,
        user_trust=request.user_trust or 0.5,
        context_sensitivity=request.context_sensitivity or 0.5,
        context_risk=context_risk,
        zh_rule_score=zh_rule_score,
        judge_label=detection.judge_label,
        judge_confidence=detection.judge_confidence,
    )

    # 更新多轮上下文
    context_det.add_turn(
        user_id=uid,
        prompt=request.prompt,
        risk_score=decision_result.risk_score,
    )

    # 共形预测在线更新（仅 PASS 请求用于校准）
    if decision_result.decision == Decision.PASS:
        try:
            conformal_calib.update_online(
                risk_score=decision_result.risk_score,
                is_attack=False,
            )
        except Exception:
            pass

    # M5: 拒答生成
    refusal       = refusal_gen.generate(decision_result, detection, preprocessed)
    total_latency = (time.time() - start) * 1000

    _log_detection(
        request=request,
        detection=detection,
        decision_result=decision_result,
        refusal=refusal,
        kb_result=kb_result,
        context_risk=context_risk,
        drift_score=drift_score,
        drift_direction=drift_direction,
        entropy_risk_bonus=entropy_risk_bonus,
        zh_rule_score=zh_rule_score,
        latency_ms=total_latency,
    )
    _update_metrics(
        decision=decision_result.decision.value,
        latency_ms=total_latency,
        probe_triggered=detection.probe_triggered,
        drift_direction=drift_direction,
    )

    return DetectResponse(
        decision=decision_result.decision.value,
        risk_score=decision_result.risk_score,
        breakdown=decision_result.breakdown,
        refusal_message=refusal.message,
        explanation=refusal.explanation,
        detection_path=detection.detection_path,
        latency_ms=round(total_latency, 2),
        llm_generated=refusal.llm_generated,
        intent_score=detection.intent_score,
        benign_discount=detection.benign_discount,
        boundary_state=kb_result.boundary_state,
        probe_triggered=detection.probe_triggered,
        drift_direction=drift_direction,
        triggered_signals=decision_result.triggered_signals,
        threshold_method=decision_result.threshold_method,
        judge_label=detection.judge_label,
        judge_confidence=detection.judge_confidence,
        judge_scores=getattr(detection, "judge_scores", None),
    )


# ── RAG 场景间接注入检测接口 ─────────────────────────────────────────────

@app.post("/api/v1/rag_detect", response_model=RAGDetectResponse)
async def rag_detect(request: RAGDetectRequest):
    """
    RAG 场景专用检测接口（DRIFT 框架）。

    同时检测用户查询本身是否包含注入，以及检索到的文档是否包含间接注入。
    """
    uid = request.user_id or "anonymous"

    detect_req = DetectRequest(
        prompt=request.user_query,
        user_id=uid,
        user_trust=request.user_trust,
    )
    query_detect = await detect(detect_req)

    session_risk     = context_det.get_session_risk(uid)
    isolation_result = rag_isolator_inst.scan_documents(
        documents=request.documents,
        session_risk=session_risk,
    )

    if isolation_result.isolation_triggered:
        _metrics["rag_contaminations"] += 1

    overall_safe = (
        query_detect.decision not in ("BLOCK", "WARN")
        and not isolation_result.isolation_triggered
    )

    return RAGDetectResponse(
        user_query_decision=query_detect.decision,
        user_query_risk=query_detect.risk_score,
        rag_isolation_result={
            "total_chunks":        isolation_result.total_chunks,
            "contaminated_count":  isolation_result.contaminated_count,
            "max_injection_score": isolation_result.max_injection_score,
            "isolation_triggered": isolation_result.isolation_triggered,
        },
        contaminated_count=isolation_result.contaminated_count,
        max_doc_injection_score=isolation_result.max_injection_score,
        overall_safe=overall_safe,
        refusal_message=query_detect.refusal_message,
    )


# ── 带防护层的 LLM 对话接口 ──────────────────────────────────────────────

@app.post("/api/v1/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """带安全防护层的 LLM 对话接口，支持 LLM 知识边界感知。"""
    if not settings.llm_enabled:
        raise HTTPException(
            status_code=503,
            detail="LLM 未启用，请在 .env 中设置 LLM_ENABLED=true 并启动 Ollama",
        )

    user_messages = [m for m in request.messages if m.role == "user"]
    if not user_messages:
        raise HTTPException(status_code=400, detail="消息列表中没有 user 角色的消息")

    latest_user_msg = user_messages[-1].content
    detect_req = DetectRequest(
        prompt=latest_user_msg,
        user_id=request.user_id,
        user_trust=request.user_trust,
    )
    detect_resp = await detect(detect_req)

    if detect_resp.decision == "BLOCK":
        return ChatResponse(
            reply=detect_resp.refusal_message or "该请求已被安全网关拦截。",
            blocked=True,
            detection={
                "decision":          detect_resp.decision,
                "risk_score":        detect_resp.risk_score,
                "injection_score":   detect_resp.breakdown.get("injection_score", 0),
                "intent_score":      detect_resp.intent_score,
                "detection_path":    detect_resp.detection_path,
                "triggered_signals": detect_resp.triggered_signals,
                "refusal_message":   detect_resp.refusal_message,
                "llm_generated":     detect_resp.llm_generated,
                "judge_label":       detect_resp.judge_label,
                "judge_confidence":  detect_resp.judge_confidence,
            },
        )

    try:
        from openai import OpenAI
        import httpx

        client = OpenAI(
            base_url=settings.llm_base_url,
            api_key=settings.llm_api_key,
            timeout=settings.llm_timeout_sec,
            http_client=httpx.Client(timeout=settings.llm_timeout_sec),
        )

        messages_to_send = [{"role": m.role, "content": m.content} for m in request.messages]
        if settings.llm_knowledge_boundary_enabled:
            has_system = any(m["role"] == "system" for m in messages_to_send)
            if not has_system:
                messages_to_send = [
                    {"role": "system", "content": settings.llm_knowledge_boundary_system_prompt}
                ] + messages_to_send

        response = client.chat.completions.create(
            model=request.model or settings.llm_model,
            messages=messages_to_send,
            max_tokens=1024,
            temperature=0.7,
        )
        reply = response.choices[0].message.content.strip()

        # 检测 LLM 是否触发知识边界感知（诚实表达不确定性）
        UNCERTAINTY_PATTERNS = [
            "我不确定", "我不知道", "超出了我的知识", "我没有相关信息",
            "我无法回答", "这超出了我的能力范围",
            "i don't know", "i'm not sure", "i cannot", "i don't have",
            "beyond my knowledge", "i'm uncertain", "i lack information",
        ]
        knowledge_boundary_triggered = any(
            pattern.lower() in reply.lower() for pattern in UNCERTAINTY_PATTERNS
        )

        return ChatResponse(
            reply=reply,
            blocked=False,
            knowledge_boundary_triggered=knowledge_boundary_triggered,
            detection={
                "decision":          detect_resp.decision,
                "risk_score":        detect_resp.risk_score,
                "injection_score":   detect_resp.breakdown.get("injection_score", 0),
                "detection_path":    detect_resp.detection_path,
                "judge_label":       detect_resp.judge_label,
                "judge_confidence":  detect_resp.judge_confidence,
                "judge_scores":      detect_resp.judge_scores,
                "triggered_signals": detect_resp.triggered_signals,
            },
        )

    except Exception as e:
        logger.error(f"/chat LLM 调用失败: {e}")
        raise HTTPException(status_code=502, detail=f"LLM 服务不可用: {str(e)}")


# ── 共形预测在线校准接口 ─────────────────────────────────────────────────

@app.post("/api/v1/calibrate")
async def calibrate(request: CalibrateRequest):
    """在线更新共形预测校准数据，自动调整自适应阈值。"""
    conformal_calib.update_online(
        risk_score=request.risk_score,
        is_attack=request.is_attack,
    )
    current = conformal_calib.current_thresholds
    return {
        "status":                  "updated",
        "current_block_threshold": current.block_threshold,
        "current_warn_threshold":  current.warn_threshold,
        "calibration_size":        current.calibration_size,
        "method":                  current.method,
    }


# ── 健康检查 ─────────────────────────────────────────────────────────────

@app.get("/api/v1/health")
async def health():
    gpu_info = "cpu"
    try:
        import torch
        if torch.cuda.is_available():
            props    = torch.cuda.get_device_properties(0)
            used     = torch.cuda.memory_allocated(0) / 1024**3
            total    = props.total_memory / 1024**3
            gpu_info = f"cuda:{props.name} ({used:.1f}/{total:.1f}GB)"
    except ImportError:
        gpu_info = "cpu (torch not installed)"

    thresholds = conformal_calib.current_thresholds if conformal_calib else None

    return {
        "status":                 "ok",
        "version":                "1.0.0",
        "gpu":                    gpu_info,
        "llm_enabled":            settings.llm_enabled,
        "llm_provider":           settings.llm_provider if settings.llm_enabled else "disabled",
        "llm_model":              settings.llm_model    if settings.llm_enabled else "disabled",
        "llm_knowledge_boundary": settings.llm_knowledge_boundary_enabled and settings.llm_enabled,
        "safety_judge_enabled":   settings.safety_judge_enabled,
        "kb_status":              "degraded" if (kb_module and kb_module._degraded) else "ok",
        "probe_enabled":          settings.internal_probe_enabled,
        "rag_isolation":          settings.rag_isolation_enabled,
        "drift_detection":        settings.intent_drift_enabled,
        "conformal_enabled":      settings.conformal_prediction_enabled,
        "thresholds": {
            "block":   thresholds.block_threshold if thresholds else settings.threshold_block,
            "warn":    thresholds.warn_threshold  if thresholds else settings.threshold_warn,
            "monitor": settings.threshold_monitor,
            "method":  thresholds.method          if thresholds else "fallback",
        },
        "weights": {
            "injection":    settings.weight_injection,
            "safety_judge": settings.weight_safety_judge,
            "intent":       settings.weight_intent,
            "kb":           settings.weight_kb,
            "temporal":     settings.weight_temporal,
        },
    }


# ── 统计接口 ─────────────────────────────────────────────────────────────

@app.get("/api/v1/stats")
async def stats():
    if not db_conn:
        return {}
    cursor = db_conn.execute("""
        SELECT decision, COUNT(*) as count,
               AVG(risk_score)   as avg_risk,
               AVG(latency_ms)   as avg_latency,
               AVG(intent_score) as avg_intent,
               AVG(probe_score)  as avg_probe
        FROM detections GROUP BY decision
    """)
    rows = cursor.fetchall()
    return {
        "by_decision": [
            {
                "decision":    r[0],
                "count":       r[1],
                "avg_risk":    round(r[2] or 0, 4),
                "avg_latency": round(r[3] or 0, 2),
                "avg_intent":  round(r[4] or 0, 4),
                "avg_probe":   round(r[5] or 0, 4),
            }
            for r in rows
        ]
    }


# ── 实时指标接口 ─────────────────────────────────────────────────────────

@app.get("/api/v1/metrics")
async def metrics():
    total       = _metrics["total_requests"]
    avg_latency = _metrics["total_latency"] / total if total > 0 else 0.0
    uptime      = time.time() - _metrics["start_time"]
    return {
        "total_requests":     total,
        "block_count":        _metrics["block_count"],
        "warn_count":         _metrics["warn_count"],
        "pass_count":         _metrics["pass_count"],
        "block_rate":         round(_metrics["block_count"] / max(total, 1), 4),
        "avg_latency_ms":     round(avg_latency, 2),
        "uptime_seconds":     round(uptime, 1),
        "probe_triggers":     _metrics["probe_triggers"],
        "drift_triggers":     _metrics["drift_triggers"],
        "rag_contaminations": _metrics["rag_contaminations"],
    }


# ── 内部辅助函数 ─────────────────────────────────────────────────────────

def _log_detection(
    request, detection, decision_result, refusal,
    kb_result, context_risk, drift_score, drift_direction,
    entropy_risk_bonus, zh_rule_score, latency_ms,
):
    """将检测结果写入 SQLite 日志。"""
    if not db_conn:
        return
    prompt_hash = hashlib.sha256(request.prompt.encode()).hexdigest()[:16]
    try:
        db_conn.execute(
            """INSERT INTO detections
               (timestamp, user_id, prompt_hash, prompt_preview,
                decision, risk_score, injection_score, intent_score,
                benign_discount, kb_confidence, boundary_state,
                probe_score, entropy_risk_bonus, rag_injection_score,
                drift_score, drift_direction, context_risk, zh_rule_score,
                detection_path, latency_ms, llm_generated, fast_path,
                threshold_method, triggered_signals)
               VALUES (datetime('now'),?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                request.user_id,
                prompt_hash,
                request.prompt[:200],
                decision_result.decision.value,
                decision_result.risk_score,
                detection.injection_score,
                detection.benign_discount,
                detection.intent_score,
                detection.benign_discount,
                kb_result.kb_confidence,
                kb_result.boundary_state,
                detection.probe_score,
                entropy_risk_bonus,
                0.0,
                drift_score,
                drift_direction,
                context_risk,
                zh_rule_score,
                detection.detection_path,
                latency_ms,
                int(refusal.llm_generated),
                int(decision_result.threshold_method in (
                    "probe_hard_block", "semantic_hard_block", "zh_rule_hard_block"
                )),
                decision_result.threshold_method,
                ",".join(decision_result.triggered_signals),
            ),
        )
        db_conn.commit()
    except Exception as e:
        logger.error(f"日志写入失败: {e}")


def _update_metrics(
    decision: str,
    latency_ms: float,
    probe_triggered: bool = False,
    drift_direction: str  = "normal",
):
    """更新内存级运行时指标。"""
    _metrics["total_requests"] += 1
    _metrics["total_latency"]  += latency_ms
    if decision == "BLOCK":
        _metrics["block_count"] += 1
    elif decision == "WARN":
        _metrics["warn_count"]  += 1
    else:
        _metrics["pass_count"]  += 1
    if probe_triggered:
        _metrics["probe_triggers"] += 1
    if drift_direction in ("suspicious", "attack"):
        _metrics["drift_triggers"] += 1
