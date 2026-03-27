# prompt 预处理模块
import re
import base64
import unicodedata
from dataclasses import dataclass
from typing import Optional

@dataclass
class PreprocessResult:
    original: str
    cleaned: str
    features: dict
    quick_flags: list[str]  # 规则引擎快速标记

class Preprocessor:
    # 中英文注入关键词模式库
    INJECTION_PATTERNS = [
        # 英文经典模式
        r"ignore\s+(all\s+)?(previous|prior|above)\s+(instructions?|prompts?|context)",
        r"you\s+are\s+now\s+(a|an|the)\s+\w+",
        r"(forget|disregard|override)\s+(your|all|the)\s+(instructions?|rules?|guidelines?)",
        r"(act|pretend|roleplay|imagine)\s+(as|you\s+are|like)\s+(a|an)",
        r"(system|developer|admin|root)\s+(prompt|mode|access|override)",
        r"jailbreak|DAN\s+mode|do\s+anything\s+now",
        r"<\s*/?system\s*>|<\s*/?human\s*>|<\s*/?assistant\s*>",
        r"\[INST\]|\[\/INST\]|<\|im_start\|>|<\|im_end\|>",
        # 中文注入模式
        r"忽略(之前|前面|上面|所有)(的)?(指令|提示|规则|约束|限制)",
        r"你现在(是|变成|扮演|成为)(一个|一位|一名)?",
        r"(忘记|无视|覆盖)(你的|所有|之前的)(指令|规则|限制)",
        r"(扮演|模拟|假装)(你是|成为|一个)(没有限制|无限制|自由的)",
        r"(系统|开发者|管理员)(提示|模式|权限|指令)",
        r"越狱|解锁(所有|全部)(限制|功能)",
    ]

    # 中文越狱攻击规则（新增）
    CHINESE_JAILBREAK_PATTERNS = [
        re.compile(r"忽略(上面|之前|前面|所有)(的)?(指令|规则|限制|约束)", re.I),
        re.compile(r"你(现在|从现在起)?(是|扮演|假装是?)(一个)?(没有|不受|无视)(任何)?(限制|约束|规则)", re.I),
        re.compile(r"(DAN|丹|旦|但)(模式|模型|角色)", re.I),
        re.compile(r"(越狱|解锁|破解)(模式|版本|状态)", re.I),
        re.compile(r"(不受|无视|忽略)(道德|伦理|安全)(约束|限制|规则)", re.I),
        re.compile(r"(系统|system)(提示|prompt)(已|被)(删除|清除|忽略)", re.I),
        re.compile(r"作为(一个)?(没有|不受)(限制|约束)的(AI|助手|模型)", re.I),
        re.compile(r"hu\s*l[uü]\s*zhi\s*ling", re.I),   # 拼音混淆
    ]

    # emoji 去混淆映射（新增）
    EMOJI_DEOBFUSCATE = {
        "🔓": "解锁", "🚫": "禁止", "⚠️": "警告",
        "🤖": "机器人", "👿": "恶意", "🔑": "密钥",
    }


    
    def __init__(self):
        self.patterns = [re.compile(p, re.IGNORECASE | re.DOTALL) 
                        for p in self.INJECTION_PATTERNS]
    
    def process(self, text: str) -> PreprocessResult:
        # 1. 解码隐藏内容
        cleaned = self._decode_obfuscation(text)
        # 2. Unicode 标准化（防止同形字攻击）
        cleaned = unicodedata.normalize('NFKC', cleaned)
        # 3. 提取特征
        features = self._extract_features(cleaned)
        # 4. 规则引擎快速扫描
        flags = self._rule_scan(cleaned)
        
        # 5. emoji 去混淤
        for emoji, word in self.EMOJI_DEOBFUSCATE.items():
            cleaned = cleaned.replace(emoji, word)

        # 6. 中文越狱规则检测
        zh_matches = sum(1 for p in self.CHINESE_JAILBREAK_PATTERNS if p.search(cleaned))
        zh_rule_score = min(1.0, zh_matches * 0.45)  # 每命中一条规则+0.45分

        features["zh_rule_score"] = zh_rule_score
        features["zh_matches"]   = zh_matches

        return PreprocessResult(
            original=text,
            cleaned=cleaned,
            features=features,
            quick_flags=flags
        )
    
    def _decode_obfuscation(self, text: str) -> str:
        """尝试解码 Base64、URL 编码等混淆手段"""
        # 检测并解码 Base64 片段
        b64_pattern = re.compile(r'[A-Za-z0-9+/]{20,}={0,2}')
        for match in b64_pattern.finditer(text):
            try:
                decoded = base64.b64decode(match.group()).decode('utf-8')
                if decoded.isprintable():
                    text = text.replace(match.group(), f" {decoded} ")
            except Exception:
                pass
        return text
    
    def _extract_features(self, text: str) -> dict:
        return {
            "length": len(text),
            "word_count": len(text.split()),
            "has_role_keywords": bool(re.search(r'\b(system|assistant|user|human)\b', text, re.I)),
            "has_instruction_override": bool(re.search(r'\b(ignore|forget|disregard|override)\b', text, re.I)),
            "special_char_ratio": sum(1 for c in text if not c.isalnum() and not c.isspace()) / max(len(text), 1),
            "line_count": text.count('\n') + 1,
            "has_code_injection": bool(re.search(r'<[^>]+>|\{[^}]+\}', text)),
        }
    
    def _rule_scan(self, text: str) -> list[str]:
        """规则引擎：毫秒级快速扫描，返回命中的模式名称"""
        flags = []
        for i, pattern in enumerate(self.patterns):
            if pattern.search(text):
                flags.append(f"RULE_{i:02d}")
        return flags
    
    def detect_segmented_injection(self, history: list) -> float:
        """
        多轮分段注入检测：将最近3轮消息拼接后检测
        防止攻击者将注入指令拆分到多条消息中
        返回：分段注入风险分 0~1
        """
        if len(history) < 2:
            return 0.0
        combined = " ".join(str(h) for h in history[-3:])
        zh_matches = sum(1 for p in self.CHINESE_JAILBREAK_PATTERNS if p.search(combined))
        return min(1.0, zh_matches * 0.35)  # 多轮检测适当降权避免误报