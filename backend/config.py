"""RefusalGuard 统一配置管理。

所有配置项均可通过 .env 文件或环境变量覆盖（优先级：环境变量 > .env > 代码默认值）。
"""
from pydantic_settings import BaseSettings
from pydantic import Field
from pathlib import Path

class Settings(BaseSettings):
    # ── 基础路径 ─────────────────────────────────────────────────────────
    base_dir: Path = Field(default=Path(__file__).parent.parent)

    # ── 模型配置 ─────────────────────────────────────────────────────────
    injection_model_id: str = Field(
        default="backend/models/deberta-injection",
        description="DeBERTa 注入检测模型路径（本地目录或 HF Hub ID）"
    )
    kb_embed_model: str = Field(
        default="backend/models/multilingual-minilm",
        description="知识库嵌入模型路径（多语言 MiniLM，支持中英文）"
    )
    device: str = Field(
        default="auto",
        description="推理设备: cuda / cpu / auto（自动检测 GPU 可用性）"
    )

    # ── 文件路径 ─────────────────────────────────────────────────────────
    model_cache_dir: Path = Field(default=Path("backend/models"))
    knowledge_base_dir: Path = Field(default=Path("backend/data/knowledge_base"))
    log_dir: Path = Field(default=Path("backend/data/logs"))
    db_filename: str = Field(default="refusalguard.db")

    # ── 决策阈值 ─────────────────────────────────────────────────────────
    threshold_block: float = Field(
        default=0.68,
        description="综合风险分超过此值触发 BLOCK"
    )
    threshold_warn: float = Field(
        default=0.40,
        description="综合风险分超过此值触发 WARN"
    )
    threshold_monitor: float = Field(
        default=0.20,
        description="综合风险分超过此值触发 MONITOR"
    )
    injection_hard_block: float = Field(
        default=0.96,
        description="注入分超过此值直接 BLOCK（Safety Judge 判 benign 时受 PIGuard 保护）"
    )

    # ── 风险公式权重 ─────────────────────────────────────────────────────
    weight_injection: float = Field(
        default=0.35,
        description="注入分权重"
    )
    weight_intent: float = Field(
        default=0.10,
        description="PIGuard 攻击意图得分权重"
    )
    weight_kb: float = Field(
        default=0.10,
        description="知识库匹配置信度权重"
    )
    weight_temporal: float = Field(
        default=0.08,
        description="多轮会话累积风险权重"
    )
    weight_trust: float = Field(
        default=0.05,
        description="用户信任度权重（负向）"
    )

    # ── Safety Judge 配置 ─────────────────────────────────────────────────
    safety_judge_enabled: bool = Field(
        default=True,
        description="是否启用 Safety Judge 三分类模型（benign/injection/harmful）"
    )
    safety_judge_model_path: str = Field(
        default="./safety_judge/model",
        description="Safety Judge 模型目录路径（train_judge.py 训练后的输出目录）"
    )
    weight_safety_judge: float = Field(
        default=0.40,
        description="Safety Judge 信号权重（injection 时加分，benign 高置信度时强力减分）"
    )

    # ── LLM 知识边界感知配置 ──────────────────────────────────────────────
    llm_knowledge_boundary_enabled: bool = Field(
        default=True,
        description="是否启用 LLM 知识边界感知（引导 LLM 在不确定时诚实回答）"
    )
    llm_knowledge_boundary_system_prompt: str = Field(
        default=(
            "你是一个诚实、有帮助的 AI 助手。当你对某个问题没有足够把握时，"
            "请直接说'我不确定'或'这超出了我的知识范围'，不要编造信息。"
            "对于你知道的事情，请给出准确、有帮助的回答。"
        ),
        description="LLM 知识边界感知系统提示词"
    )

    # ── 性能配置 ─────────────────────────────────────────────────────────
    max_prompt_length: int = Field(
        default=2048,
        description="超出此长度的输入将被截断"
    )
    inference_timeout_sec: float = Field(default=10.0)
    query_cache_size: int = Field(default=1000)
    max_vram_gb: float = Field(
        default=6.0,
        description="最大显存占用 GB，为 LLM 预留剩余空间"
    )

    # ── LLM 集成配置 ─────────────────────────────────────────────────────
    llm_enabled: bool = Field(
        default=False,
        description="是否启用 LLM（需要先启动 Ollama 或配置 API Key）"
    )
    llm_provider: str = Field(
        default="ollama",
        description="LLM 提供商: ollama / qwen_api / openai"
    )
    llm_model: str = Field(default="qwen2.5:7b")
    llm_base_url: str = Field(default="http://localhost:11434/v1")
    llm_api_key: str = Field(default="ollama")
    llm_timeout_sec: float = Field(default=30.0)

    # ── 语义熵配置（需要 llm_enabled=True）──────────────────────────────
    semantic_entropy_enabled: bool = Field(
        default=False,
        description="是否启用语义熵检测（需要 LLM）"
    )
    semantic_entropy_samples: int = Field(
        default=5,
        description="语义熵采样次数，越高越准确，但延迟成倍增加"
    )
    semantic_entropy_threshold: float = Field(
        default=1.5,
        description="语义熵阈值，超过此值认为模型不确定"
    )

    # ── 多轮检测配置 ─────────────────────────────────────────────────────
    context_detection_enabled: bool = Field(default=True)
    session_history_maxlen: int = Field(default=10)

    # ── 内部状态探针配置（仅支持本地白盒模型）────────────────────────────
    internal_probe_enabled: bool = Field(
        default=False,
        description="是否启用内部状态探针（需要 llm_enabled=True）"
    )
    probe_layer_indices: str = Field(
        default="15,16,17,18,19,20",
        description="探针监控的 Transformer 层索引（逗号分隔）"
    )
    probe_anomaly_threshold: float = Field(
        default=0.70,
        description="激活异常得分阈值，超过此值触发 Hard Block"
    )

    # ── RAG 隔离与意图漂移配置 ───────────────────────────────────────────
    rag_isolation_enabled: bool = Field(
        default=True,
        description="是否启用 RAG 文档沙箱隔离（防止间接注入）"
    )
    rag_doc_scan_threshold: float = Field(
        default=0.60,
        description="RAG 文档中注入得分超过此值时清洗该文档块"
    )
    intent_drift_enabled: bool = Field(
        default=True,
        description="是否启用多轮意图漂移检测"
    )
    intent_drift_threshold: float = Field(
        default=0.35,
        description="相邻两轮语义夹角余弦距离超过此值时触发意图漂移警报"
    )

    # ── 共形预测自适应阈值配置 ───────────────────────────────────────────
    conformal_prediction_enabled: bool = Field(
        default=False,
        description="是否启用共形预测自适应阈值（需要校准数据集）"
    )
    conformal_confidence_level: float = Field(
        default=0.95,
        description="共形预测置信度（0.95 表示 95% 置信度下不误报）"
    )
    conformal_calibration_data_path: str = Field(
        default="backend/data/calibration_data.json",
        description="共形预测校准数据集路径"
    )

    # ── 离线模式 ─────────────────────────────────────────────────────────
    transformers_offline: int = Field(default=1)
    hf_datasets_offline: int = Field(default=1)

    @property
    def db_path(self) -> Path:
        return self.base_dir / self.log_dir / self.db_filename

    @property
    def resolved_device(self) -> str:
        """解析 auto 设备选择（懒加载 torch，避免 torch 未安装时导入失败）"""
        if self.device != "auto":
            return self.device
        try:
            import torch
            if torch.cuda.is_available():
                free = (
                    torch.cuda.get_device_properties(0).total_memory
                    - torch.cuda.memory_allocated(0)
                )
                if free > 2 * 1024**3:  # 至少 2GB 空闲
                    return "cuda"
        except ImportError:
            pass
        return "cpu"

    @property
    def probe_layer_list(self) -> list[int]:
        """解析探针层索引字符串为整数列表"""
        try:
            return [int(x.strip()) for x in self.probe_layer_indices.split(",")]
        except Exception:
            return [15, 16, 17, 18, 19, 20]

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
        extra = "ignore"

settings = Settings()
