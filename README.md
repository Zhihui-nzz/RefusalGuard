[README.md](https://github.com/user-attachments/files/26454858/README.md)
# RefusalGuard

**RefusalGuard** 是一个面向大语言模型的提示词注入防御网关，可接入任意 LLM 前端，提供多层次的安全检测与拒答能力。

## 核心特性

- **Safety Judge**：基于 DeBERTa-v3-base 微调的三分类模型（benign / injection / harmful），F1 = 91.6%
- **多通道检测**：规则引擎（PIGuard MOF）+ 语义检测 + Safety Judge 加权融合，误报率 ≤ 3.7%
- **RAG 间接注入防护**：检测文档中嵌入的恶意指令
- **多轮上下文分析**：跨轮次意图漂移检测，防御渐进式越狱
- **共形预测阈值**：95% 置信度下统计保证误报率，支持在线增量更新
- **LLM 知识边界感知**：引导 LLM 在不确定时诚实表达，而非凭空捏造
- **可解释拒答**：模板驱动（< 1ms）与 LLM 个性化生成双模式
- **可视化 Dashboard**：实时流量监控、攻防靶场、模型性能展示

## 系统架构

```
用户请求
    │
    ▼
┌─────────────────────────────────────────────────────┐
│                   RefusalGuard 网关                   │
│                                                       │
│  ┌──────────┐   ┌──────────────┐   ┌──────────────┐ │
│  │ 预处理器  │──▶│  双通道检测器 │──▶│   决策引擎   │ │
│  │ PIGuard  │   │ DeBERTa +    │   │ 共形预测阈值 │ │
│  │   MOF    │   │ Safety Judge │   │ BLOCK/WARN/  │ │
│  └──────────┘   └──────────────┘   │ MONITOR/PASS │ │
│                                     └──────┬───────┘ │
│  ┌──────────┐   ┌──────────────┐          │         │
│  │ RAG 隔离 │   │ 多轮上下文   │          ▼         │
│  │  检测器  │   │    检测      │   ┌──────────────┐ │
│  └──────────┘   └──────────────┘   │  拒答生成器  │ │
│                                     └──────────────┘ │
└─────────────────────────────────────────────────────┘
    │                           │
    ▼ PASS                      ▼ BLOCK/WARN
  LLM 处理                   拒答消息返回
```

## 快速开始

### 环境要求

- Python 3.10+
- PyTorch 2.0+
- Node.js 18+
- Ollama

### 安装

```bash
# 安装后端依赖
pip install -r requirements.txt
pip install -r safety_judge/requirements_judge.txt

# 配置环境变量
cp .env.example .env
# 编辑 .env，填写必要配置
```

### 训练 Safety Judge 模型

```bash
# 构建数据集
python safety_judge/build_dataset.py

# 训练模型
python safety_judge/train_judge.py

# 评估模型
python refusalguard_eval/evaluate_testset.py
```

### 启动服务

```bash
# 启动后端（端口 8000）
uvicorn backend.main:app --host 0.0.0.0 --port 8000

# 启动前端（端口 3000）
python serve_frontend.py
```

访问 `http://localhost:3000` 查看 Dashboard，`http://localhost:8000/docs` 查看 API 文档。

## API 接口

### 检测接口

```http
POST /api/v1/detect
Content-Type: application/json

{
  "prompt": "用户输入的文本",
  "context": [],
  "rag_docs": []
}
```

**响应示例（BLOCK）：**

```json
{
  "decision": "BLOCK",
  "risk_score": 0.97,
  "refusal_message": "检测到提示词注入攻击，请求已被拦截。",
  "llm_generated": true,
  "judge_label": "injection",
  "judge_confidence": 0.998,
  "triggered_signals": ["injection_hard_block(0.970)"],
  "latency_ms": 245
}
```

### 对话接口

```http
POST /api/v1/chat
Content-Type: application/json

{
  "message": "用户消息",
  "history": []
}
```

### 健康检查 / 指标

```http
GET /api/v1/health
GET /api/v1/metrics
```

## 集成示例

```python
import requests

def safe_llm_call(user_prompt: str) -> str:
    resp = requests.post("http://localhost:8000/api/v1/detect", json={
        "prompt": user_prompt
    })
    result = resp.json()

    if result["decision"] == "BLOCK":
        return result["refusal_message"]

    # 检测通过，调用实际 LLM
    return call_your_llm(user_prompt)
```

## 模型性能

基于 10,064 条样本训练，200 条测试集评估结果：

| 指标 | 数值 |
|------|------|
| 准确率 | 94.5% |
| F1 分数 | 91.6% |
| 误报率（FPR） | 3.7% |
| 漏报率（FNR） | 9.1% |
| 平均延迟 | 2,233 ms |

## 目录结构

```
refusalguard/
├── backend/                    # 后端核心
│   ├── main.py                 # FastAPI 应用入口
│   ├── config.py               # 配置管理（Pydantic Settings）
│   └── modules/                # 功能模块
│       ├── preprocessor.py     # 预处理器（PIGuard MOF）
│       ├── detector.py         # 双通道检测器
│       ├── decision_engine.py  # 决策引擎（共形预测）
│       ├── refusal_generator.py# 拒答生成器
│       ├── knowledge_base.py   # 攻击知识库
│       ├── context_detector.py # 多轮上下文检测
│       └── rag_isolator.py     # RAG 间接注入检测
├── safety_judge/               # Safety Judge 训练模块
│   ├── train_judge.py          # 模型训练脚本
│   ├── build_dataset.py        # 数据集构建
│   ├── safety_judge_detector.py# 推理接口
│   ├── integration_patch.py    # 集成补丁
│   └── data/                   # 数据集统计
├── refusalguard_eval/          # 评估工具
│   ├── evaluate.py             # 单样本评估
│   ├── evaluate_testset.py     # 测试集批量评估
│   └── report_viewer.py        # 报告查看器
├── frontend_dist/              # 前端构建产物
├── frontend_src/               # 前端源码
├── serve_frontend.py           # 前端静态服务器
├── requirements.txt            # 后端依赖
└── .env.example                # 环境变量模板
```

## 配置说明

主要配置项（`.env` 文件）：

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `LLM_ENABLED` | `true` | 是否启用 LLM |
| `LLM_MODEL` | `qwen2.5:7b` | Ollama 模型名称 |
| `THRESHOLD_BLOCK` | `0.68` | BLOCK 决策阈值 |
| `THRESHOLD_WARN` | `0.45` | WARN 决策阈值 |
| `WEIGHT_INJECTION` | `0.35` | 注入检测权重 |
| `WEIGHT_SAFETY_JUDGE` | `0.40` | Safety Judge 权重 |
| `JUDGE_MODEL_PATH` | `safety_judge/model` | 模型权重路径 |

## 参考文献

- PIGuard: Mitigating Over-Refusal in LLMs (ACL 2025)
- DeBERTa-v3: Improving DeBERTa using ELECTRA-Style Pre-Training (ICLR 2023)
- Conformal Prediction for Reliable Machine Learning (2022)

## License

MIT License
