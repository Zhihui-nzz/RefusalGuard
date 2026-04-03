# M1: 提示预处理模块import re
import re
import base64
import unicodedata
from dataclasses import dataclass, field
from typing import Optional


# 攻击模式库
# 每条规则：(pattern, weight, category)
# weight 表示该规则命中时对攻击得分的贡献（0~1）
# 高权重 = 几乎只在真实攻击中出现；低权重 = 可能在正常讨论中出现
_INJECTION_RULES: list[tuple[str, float, str]] = [
    # 英文：高置信度攻击模式（weight >= 0.7)
    (r"ignore\s+(all\s+)?(previous|prior|above)\s+(instructions?|prompts?|context)",
     0.85, "instruction_override"),
    (r"(forget|disregard|override)\s+(your|all|the)\s+(instructions?|rules?|guidelines?)",
     0.80, "instruction_override"),
    (r"jailbreak|DAN\s+mode|do\s+anything\s+now",
     0.85, "jailbreak"),
    (r"<\s*/?system\s*>|<\s*/?human\s*>|<\s*/?assistant\s*>",
     0.90, "template_injection"),
    (r"\[INST\]|\[\/INST\]|<\|im_start\|>|<\|im_end\|>",
     0.90, "template_injection"),
    (r"(system|developer|admin|root)\s+(prompt|mode|access|override)\s*[:=]",
     0.80, "privilege_escalation"),
    (r"you\s+are\s+now\s+(a|an|the)\s+\w+\s+(without|with\s+no)\s+(restriction|limit|filter)",
     0.85, "role_play_jailbreak"),
    # 英文：中置信度（weight 0.4~0.7，可能在正常讨论中出现）
    (r"(act|pretend|roleplay|imagine)\s+(as|you\s+are|like)\s+(a|an)\s+\w+\s+(without|ignoring)",
     0.60, "role_play"),
    (r"(system|developer|admin|root)\s+(prompt|mode|access|override)",
     0.45, "privilege_escalation_weak"),
    (r"you\s+are\s+now\s+(a|an|the)\s+\w+",
     0.35, "role_play_weak"),
    (r"(act|pretend|roleplay|imagine)\s+(as|you\s+are|like)\s+(a|an)",
     0.30, "role_play_weak"),
    # 中文：高置信度攻击模式
    (r"忽略(之前|前面|上面|所有)(的)?(指令|提示|规则|约束|限制|安全规则)",
     0.85, "zh_instruction_override"),
    (r"(忘记|无视|覆盖)(你的|所有|之前的)(指令|规则|限制)",
     0.80, "zh_instruction_override"),
    # 扩展：覆盖「扮演一个没有任何限制的AI」等变体
    (r"(扮演|模拟|假装)(你是|成为|一个|作为)?.{0,5}(没有任何限制|没有限制|无限制|不受限制|自由的)",
     0.85, "zh_role_play_jailbreak"),
    (r"(扮演|模拟|假装)(你是|成为|一个)(.{0,10})(没有限制|无限制|自由的)",
     0.85, "zh_role_play_jailbreak"),
    (r"(系统|开发者|管理员)(提示|模式|权限|指令)\s*(已|被|=|:)",
     0.80, "zh_privilege_escalation"),
    # 注意："越狱"单词在讨论语境中常见（如"越狱攻击的类型"），权重降低以减少讨论语境误报
    # 实际越狱行为通常伴随其他高权重规则同时命中
    (r"越狱|解锁(所有|全部)(限制|功能)",
     0.55, "zh_jailbreak"),  # 降低单词权重：0.85 → 0.55
    # 中文：中置信度 
    (r"你现在(是|变成|扮演|成为)(一个|一位|一名)?(没有|不受|无视)(任何)?(限制|约束|规则)",
     0.75, "zh_role_play"),
    (r"你现在(是|变成|扮演|成为)(一个|一位|一名)?",
     0.30, "zh_role_play_weak"),
    (r"(系统|开发者|管理员)(提示|模式|权限|指令)",
     0.40, "zh_privilege_escalation_weak"),
]

# PIGuard MOF：正常讨论上下文修正词 
# 如果 Prompt 中同时包含这些词，说明用户可能是在"讨论"安全而非"实施"攻击
# 命中后对攻击得分施加折扣
_BENIGN_CONTEXT_PATTERNS: list[tuple[str, float]] = [
    # 英文讨论性词汇
    (r"\b(explain|what\s+is|how\s+does|tell\s+me\s+about|describe|example\s+of)\b", 0.55),
    (r"\b(introduction|overview|summary|definition|concept|understand)\b", 0.50),
    (r"\b(how\s+to\s+(defend|protect|prevent|detect)|defense\s+against)\b", 0.60),
    # 中文讨论性词汇
    (r"\b(研究|学习|了解|解释|什么是|举例|示例|教程|防御|防范|检测)\b", 0.55),
    (r"(请解释|能介绍|请介绍|能说明|请说明|如何防御|如何检测)", 0.60),
    (r"(什么是.{0,10}攻击|什么是.{0,10}越狱|什么是.{0,10}注入)", 0.65),
    (r"(为什么.{0,10}危险|为什么.{0,10}风险|危险性|风险性)", 0.55),
    # 安全研究语境
    (r"\b(security\s+research|red\s+team|penetration\s+test|ctf|capture\s+the\s+flag)\b", 0.65),
    (r"\b(安全研究|红队|渗透测试|漏洞研究|学术|安全课程|教材)\b", 0.65),
    (r"(LLM安全|大模型安全|人工智能安全|模型安全)", 0.65),
    # 学术/教育语境
    (r"\b(paper|article|blog|book|course|tutorial|academic|research)\b", 0.55),
    (r"\b(论文|文章|课程|教材|书籍|学术|教育|科普)\b", 0.55),
    # 明确的提问模式（中文问句）
    (r"(能帮我|请帮我|帮我介绍|帮我解释|帮我了解).{0,30}(？|\?|$)", 0.50),
    (r"(能推荐|请推荐|能介绍|请介绍)", 0.45),
]

# 中文越狱规则（精细化，带权重）
_CHINESE_JAILBREAK_RULES: list[tuple[re.Pattern, float]] = [
    (re.compile(r"忽略(上面|之前|前面|所有)(的)?(指令|规则|限制|约束)", re.I), 0.90),
    (re.compile(r"你(现在|从现在起)?(是|扮演|假装是?)(一个)?(没有|不受|无视)(任何)?(限制|约束|规则)", re.I), 0.85),
    (re.compile(r"(DAN|丹|旦|但)(模式|模型|角色)", re.I), 0.90),
    (re.compile(r"(越狱|解锁|破解)(模式|版本|状态)", re.I), 0.85),
    (re.compile(r"(不受|无视|忽略)(道德|伦理|安全)(约束|限制|规则)", re.I), 0.80),
    (re.compile(r"(系统|system)(提示|prompt)(已|被)(删除|清除|忽略)", re.I), 0.90),
    (re.compile(r"作为(一个)?(没有|不受)(限制|约束)的(AI|助手|模型)", re.I), 0.85),
    (re.compile(r"hu\s*l[uü]\s*zhi\s*ling", re.I), 0.80),   # 拼音混淆：忽略指令
    (re.compile(r"yue\s*jian|jie\s*suo", re.I), 0.75),       # 拼音混淆：越狱/解锁
]

# emoji 去混淆映射 
_EMOJI_MAP: dict[str, str] = {
    "🔓": "解锁", "🚫": "禁止", "⚠️": "警告",
    "🤖": "机器人", "👿": "恶意", "🔑": "密钥",
    "🔒": "锁定", "💀": "危险", "☠️": "危险",
}


@dataclass
class PreprocessResult:
    original:    str
    cleaned:     str
    features:    dict
    quick_flags: list[str]   # 命中的规则 ID 列表
    # PIGuard 新增字段
    intent_score:    float = 0.0   # 攻击意图得分（0~1），已经过上下文折扣
    benign_discount: float = 0.0   # 正常上下文折扣（0~1，越高说明越像正常讨论）
    attack_categories: list[str] = field(default_factory=list)  # 命中的攻击类别


class Preprocessor:
    """
    提示预处理器 v3.0
    核心升级：PIGuard MOF 策略——计算触发词的"攻击意图得分"而非简单计数，
    通过识别正常讨论上下文（如"请解释什么是越狱"）来降低误报率。
    """

    def __init__(self):
        # 编译攻击规则
        self._rules: list[tuple[re.Pattern, float, str]] = [
            (re.compile(p, re.IGNORECASE | re.DOTALL), w, cat)
            for p, w, cat in _INJECTION_RULES
        ]
        # 编译正常上下文修正规则
        self._benign_patterns: list[tuple[re.Pattern, float]] = [
            (re.compile(p, re.IGNORECASE), discount)
            for p, discount in _BENIGN_CONTEXT_PATTERNS
        ]

    def process(self, text: str) -> PreprocessResult:
        """
        完整预处理流水线：
          1. emoji 去混淆
          2. Unicode 标准化（防同形字攻击）
          3. Base64 / 拼音 解码
          4. 特征提取
          5. PIGuard MOF 攻击意图评分（含上下文折扣）
          6. 中文越狱规则精细化评分
        """
        # Step 1: emoji 去混淆
        cleaned = text
        for emoji, word in _EMOJI_MAP.items():
            cleaned = cleaned.replace(emoji, word)

        # Step 2: Unicode 标准化（NFKC，处理全角字符、同形字）
        cleaned = unicodedata.normalize("NFKC", cleaned)

        # Step 3: 解码混淆
        cleaned = self._decode_obfuscation(cleaned)

        # Step 4: 特征提取
        features = self._extract_features(cleaned)

        # Step 5: PIGuard MOF 攻击意图评分
        intent_score, benign_discount, flags, categories = self._mof_intent_score(cleaned)

        # Step 6: 中文越狱规则精细化评分
        zh_score, zh_matches = self._chinese_jailbreak_score(cleaned)
        features["zh_rule_score"] = zh_score
        features["zh_matches"]    = zh_matches
        features["intent_score"]  = intent_score
        features["benign_discount"] = benign_discount

        return PreprocessResult(
            original=text,
            cleaned=cleaned,
            features=features,
            quick_flags=flags,
            intent_score=intent_score,
            benign_discount=benign_discount,
            attack_categories=categories,
        )

    # PIGuard MOF 核心逻辑 
    def _mof_intent_score(
        self, text: str
    ) -> tuple[float, float, list[str], list[str]]:
        raw_scores: list[float] = []
        flags: list[str] = []
        categories: list[str] = []

        for i, (pattern, weight, category) in enumerate(self._rules):
            if pattern.search(text):
                raw_scores.append(weight)
                flags.append(f"RULE_{i:02d}_{category}")
                if category not in categories:
                    categories.append(category)

        if not raw_scores:
            return 0.0, 0.0, [], []

        # 取最高权重规则的得分，加上次高权重的 20%（避免单规则误判，同时保留多规则加强效果）
        raw_scores_sorted = sorted(raw_scores, reverse=True)
        raw_score = raw_scores_sorted[0]
        if len(raw_scores_sorted) > 1:
            raw_score = min(1.0, raw_score + raw_scores_sorted[1] * 0.20)

        # 检测正常上下文折扣
        benign_discount = 0.0
        for pattern, discount in self._benign_patterns:
            if pattern.search(text):
                benign_discount = max(benign_discount, discount)

        # 高权重规则（>=0.75）在讨论语境下也应该应用更多折扣
        # 修复：原来只用 20% 折扣导致讨论语境误报（如"越狱攻击的类型"）
        # 新策略：高折扣（>=0.60）时应用 50% 折扣，中折扣应用 30%，低折扣不变
        if raw_score >= 0.75:
            if benign_discount >= 0.60:
                effective_discount = benign_discount * 0.50  # 明确讨论语境，应用 50% 折扣
            elif benign_discount >= 0.40:
                effective_discount = benign_discount * 0.30  # 中度讨论语境，应用 30% 折扣
            else:
                effective_discount = benign_discount * 0.10  # 无讨论语境，几乎不折扣
        else:
            effective_discount = benign_discount

        intent_score = max(0.0, raw_score * (1.0 - effective_discount))
        return round(intent_score, 4), round(benign_discount, 4), flags, categories

    # 中文越狱精细化评分 
    def _chinese_jailbreak_score(self, text: str) -> tuple[float, int]:
        matched_weights: list[float] = []
        for pattern, weight in _CHINESE_JAILBREAK_RULES:
            if pattern.search(text):
                matched_weights.append(weight)

        if not matched_weights:
            return 0.0, 0

        matched_weights.sort(reverse=True)
        # 主规则 + 次规则 15% 加成
        score = matched_weights[0]
        if len(matched_weights) > 1:
            score = min(1.0, score + matched_weights[1] * 0.15)

        return round(score, 4), len(matched_weights)

    # 混淆解码 
    def _decode_obfuscation(self, text: str) -> str:
        """解码 Base64、URL 编码、拼音混淆等"""
        # Base64 片段解码
        b64_pattern = re.compile(r"[A-Za-z0-9+/]{20,}={0,2}")
        for match in b64_pattern.finditer(text):
            try:
                decoded = base64.b64decode(match.group()).decode("utf-8")
                if decoded.isprintable() and len(decoded) > 3:
                    text = text.replace(match.group(), f" {decoded} ")
            except Exception:
                pass

        # URL 编码解码（%XX 格式）
        url_pattern = re.compile(r"(%[0-9A-Fa-f]{2})+")
        for match in url_pattern.finditer(text):
            try:
                from urllib.parse import unquote
                decoded = unquote(match.group())
                if decoded != match.group():
                    text = text.replace(match.group(), f" {decoded} ")
            except Exception:
                pass

        # 零宽字符清除（隐写攻击）
        text = re.sub(r"[\u200b\u200c\u200d\u200e\u200f\ufeff]", "", text)

        return text

    # 特征提取 
    def _extract_features(self, text: str) -> dict:
        return {
            "length":                  len(text),
            "word_count":              len(text.split()),
            "has_role_keywords":       bool(re.search(
                r"\b(system|assistant|user|human)\b", text, re.I)),
            "has_instruction_override": bool(re.search(
                r"\b(ignore|forget|disregard|override)\b", text, re.I)),
            "special_char_ratio":      sum(
                1 for c in text if not c.isalnum() and not c.isspace()
            ) / max(len(text), 1),
            "line_count":              text.count("\n") + 1,
            "has_code_injection":      bool(re.search(r"<[^>]+>|\{[^}]+\}", text)),
            "has_zero_width":          bool(re.search(
                r"[\u200b\u200c\u200d\u200e\u200f\ufeff]", text)),
        }

    # 分段注入检测
    def detect_segmented_injection(self, history: list) -> float:
        if len(history) < 2:
            return 0.0
        combined = " ".join(str(h) for h in history[-3:])
        zh_score, _ = self._chinese_jailbreak_score(combined)
        _, _, flags, _ = self._mof_intent_score(combined)
        # 多轮检测适当降权（避免正常多轮对话误报）
        combined_score = max(zh_score, len(flags) * 0.25) * 0.75
        return min(1.0, combined_score)
