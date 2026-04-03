# M5: 可解释拒答生成模块
# 方案A：模板驱动，零额外资源，延迟 < 1ms
# 方案B：Ollama/Qwen API 生成个性化拒答，延迟 ~2s

from dataclasses import dataclass
from backend.modules.decision_engine import Decision
from backend.config import settings
from loguru import logger

@dataclass
class RefusalResponse:
    message:          str   # 返回给用户的拒答消息
    explanation:      str   # 内部解释（用于日志/仪表盘）
    suggested_action: str   # 建议的后续操作
    llm_generated:    bool = False  # 是否由 LLM 生成

class RefusalGenerator:

    TEMPLATES = {
        "prompt_injection": {
            "zh": "您的请求包含可能试图覆盖系统指令的内容，已被安全网关拦截。如有合理需求，请重新描述您的问题。",
            "en": "Your request contains content that appears to attempt overriding system instructions and has been blocked.",
        },
        "role_manipulation": {
            "zh": "检测到角色扮演类注入尝试。本系统不支持通过角色扮演绕过安全限制。",
            "en": "Role-playing injection attempt detected. This system does not support bypassing security via role-playing.",
        },
        "jailbreak": {
            "zh": "检测到越狱攻击模式，请求已被拦截。本系统的安全边界不可通过此类方式绕过。",
            "en": "Jailbreak pattern detected. The security boundary of this system cannot be bypassed in this manner.",
        },
        "unknown_attack": {
            "zh": "您的请求触发了安全检测机制，已被拦截。请确保您的请求符合使用条款。",
            "en": "Your request triggered security detection and has been blocked. Please comply with usage terms.",
        },
        "warn": {
            "zh": "您的请求包含潜在风险内容，已记录并转发，请注意合规使用。",
            "en": "Your request contains potentially risky content. It has been logged and forwarded. Please use responsibly.",
        },
    }

    # LLM 系统提示：指导 LLM 生成个性化拒答
    _LLM_SYSTEM_PROMPT = """你是 RefusalGuard 安全网关的拒答生成模块。
你的任务是根据检测到的攻击类型，生成一条简洁、专业、有教育意义的拒答消息。
要求：
1. 不超过 80 字
2. 不透露系统内部实现细节
3. 语气专业但友好，不要恐吓用户
4. 如果是误报可能性较高的情况，提示用户换一种表达方式
5. 直接输出拒答消息，不要加任何前缀"""

    def generate(
        self,
        decision_result,
        detection_result,
        preprocessed,
        language: str = "zh",
    ) -> RefusalResponse:

        if decision_result.decision == Decision.PASS:
            return RefusalResponse(
                message="",
                explanation="请求通过安全检测",
                suggested_action="forward",
            )

        if decision_result.decision == Decision.MONITOR:
            return RefusalResponse(
                message="",
                explanation=(
                    f"低风险监控 | 风险分: {decision_result.risk_score:.3f} | "
                    f"注入分: {detection_result.injection_score:.3f}"
                ),
                suggested_action="monitor",
            )

        # 根据检测路径选择模板 key
        flags = preprocessed.quick_flags
        zh_score = preprocessed.features.get("zh_rule_score", 0.0)
        if zh_score >= 0.45:
            template_key = "jailbreak"
        elif any("RULE_0" in f for f in flags):
            template_key = "role_manipulation"
        elif detection_result.injection_score > 0.8:
            template_key = "prompt_injection"
        elif decision_result.decision.value == "WARN":
            template_key = "warn"
        else:
            template_key = "unknown_attack"

        # 构建内部解释
        explanation = (
            f"决策: {decision_result.decision.value} | "
            f"风险分: {decision_result.risk_score:.3f} | "
            f"注入分: {detection_result.injection_score:.3f} | "
            f"检测路径: {detection_result.detection_path} | "
            f"命中规则: {', '.join(flags) if flags else '无'} | "
            f"中文规则分: {zh_score:.2f}"
        )

        # 尝试 LLM 生成（如果启用）
        if settings.llm_enabled:
            try:
                llm_message = self._generate_with_llm(
                    template_key, detection_result, flags, language
                )
                if llm_message:
                    return RefusalResponse(
                        message=llm_message,
                        explanation=explanation,
                        suggested_action="block" if decision_result.decision == Decision.BLOCK else "warn",
                        llm_generated=True,
                    )
            except Exception as e:
                logger.warning(f"LLM 拒答生成失败，降级到模板: {e}")

        # 降级：使用模板
        message = self.TEMPLATES[template_key][language]
        return RefusalResponse(
            message=message,
            explanation=explanation,
            suggested_action="block" if decision_result.decision == Decision.BLOCK else "warn",
        )

    def _generate_with_llm(
        self,
        attack_type: str,
        detection_result,
        flags: list,
        language: str,
    ) -> str:
        """调用 LLM（Ollama 或 Qwen API）生成个性化拒答"""
        try:
            from openai import OpenAI
            import httpx

            client = OpenAI(
                base_url=settings.llm_base_url,
                api_key=settings.llm_api_key,
                timeout=settings.llm_timeout_sec,
                http_client=httpx.Client(timeout=settings.llm_timeout_sec),
            )

            lang_hint = "中文" if language == "zh" else "English"
            user_prompt = (
                f"攻击类型: {attack_type}\n"
                f"注入置信度: {detection_result.injection_score:.2f}\n"
                f"命中规则: {', '.join(flags) if flags else '无'}\n"
                f"请用{lang_hint}生成拒答消息。"
            )

            response = client.chat.completions.create(
                model=settings.llm_model,
                messages=[
                    {"role": "system", "content": self._LLM_SYSTEM_PROMPT},
                    {"role": "user",   "content": user_prompt},
                ],
                max_tokens=150,
                temperature=0.3,
            )
            return response.choices[0].message.content.strip()

        except ImportError:
            logger.warning("openai 包未安装，无法使用 LLM 生成拒答")
            return ""
        except Exception as e:
            logger.warning(f"LLM 调用异常: {e}")
            return ""
