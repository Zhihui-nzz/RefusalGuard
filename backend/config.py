"""
RefusalGuard 统一配置管理 v2.0
所有可调参数通过 .env 文件管理，代码中零硬编码
依赖：pip install pydantic-settings
"""
from pydantic_settings import BaseSettings
from pydantic import Field
from pathlib import Path
import torch

class Settings(BaseSettings):
    base_dir: Path = Field(default=Path(__file__).parent.parent)

    injection_model_id: str = Field(
        default="backend/models/deberta-injection"
    )
    embedding_model_id: str = Field(
        # 替换为多语言模型，中文检测精度提升约30%
        default="backend/models/multilingual-minilm"
    )
    device: str = Field(
        default="auto",
        description="cuda / cpu / auto（自动检测GPU可用性）"
    )

    kb_embed_model: str = Field(
        default="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
        description="句向量模型路径，可以是 HF Hub ID 或本地目录"
    )


    model_cache_dir: Path = Field(default=Path("models"))
    knowledge_base_dir: Path = Field(default=Path("backend/data/knowledge_base"))
    log_dir: Path = Field(default=Path("backend/data/logs"))
    db_filename: str = Field(default="refusalguard.db")

    # 决策阈值 
    threshold_block: float = Field(default=0.65)
    threshold_warn: float = Field(default=0.40)
    threshold_monitor: float = Field(default=0.20)
    injection_hard_block: float = Field(
        default=0.90,
        description="注入分超过此值直接BLOCK，不走加权公式"
    )

    #  风险公式权重
    weight_injection: float = Field(default=0.65)
    weight_kb: float = Field(default=0.20)
    weight_temporal: float = Field(default=0.10)
    weight_trust: float = Field(default=0.05)

    # 性能配置
    max_prompt_length: int = Field(
        default=2048,
        description="超出此长度的输入将被截断而非报错"
    )
    inference_timeout_sec: float = Field(default=10.0)
    query_cache_size: int = Field(default=1000)
    max_vram_gb: float = Field(
        default=6.0,
        description="最大显存占用GB，为LLM预留剩余空间"
    )

    # LLM 集成配置 
    llm_enabled: bool = Field(
        default=False,
        description="是否启用LLM（需要先启动Ollama或配置API Key）"
    )
    llm_provider: str = Field(
        default="ollama",
        description="llm提供商: ollama / qwen_api"
    )
    llm_model: str = Field(default="qwen2.5:7b")
    llm_base_url: str = Field(default="http://localhost:11434/v1" )
    llm_api_key: str = Field(default="ollama")
    llm_timeout_sec: float = Field(default=30.0)

    # 语义熵配置（前沿研究，需要llm_enabled=True）
    semantic_entropy_enabled: bool = Field(default=False)
    semantic_entropy_samples: int = Field(
        default=5,
        description="采样次数，越高越准确，但延迟成倍增加"
    )

    #  多轮检测配置 
    context_detection_enabled: bool = Field(default=True)
    session_history_maxlen: int = Field(default=10)

    @property
    def db_path(self) -> Path:
        return self.base_dir / self.log_dir / self.db_filename

    @property
    def resolved_device(self) -> str:
        """解析 auto 设备选择"""
        if self.device != "auto":
            return self.device
        if torch.cuda.is_available():
            free = torch.cuda.get_device_properties(0).total_memory \
                   - torch.cuda.memory_allocated(0)
            if free > 2 * 1024**3:  # 至少2GB空闲
                return "cuda"
        return "cpu"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        # 允许 .env 中的 KEY 不区分大小写
        case_sensitive = False
        extra = "ignore"   # 允许 .env 中有 pydantic 不管的系统环境变量


# 全局单例，所有模块 from backend.config import settings
settings = Settings()