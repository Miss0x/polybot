"""llm_client.py — 统一大模型调用（OpenAI 兼容协议）

优先级：DEEPSEEK → GLM → KIMI → QWEN → OPENAI（任意一个有 key 即可用）。
用途：分诊（Jev 前的过渡方案，严格提示词约束）+ 标题翻译。
原则：温度 0、输出 JSON、失败即降级——绝不阻塞主管线。
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import httpx
from loguru import logger

_ROOT = Path(__file__).resolve().parent.parent.parent


def _load_env() -> None:
    env_path = _ROOT / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


_load_env()

# (env_key_name, base_url, default_model)
_PROVIDERS = [
    ("DEEPSEEK_API_KEY", "https://api.deepseek.com", "deepseek-chat"),
    ("GLM_API_KEY", "https://open.bigmodel.cn/api/paas/v4", "glm-4-flash"),
    ("KIMI_API_KEY", "https://api.moonshot.cn/v1", "moonshot-v1-8k"),
    ("QWEN_API_KEY", "https://dashscope.aliyuncs.com/compatible-mode/v1", "qwen-turbo"),
    ("OPENAI_API_KEY", os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1"), "gpt-4o-mini"),
]


def _detect_provider() -> tuple[str, str, str] | None:
    for env_name, base, model in _PROVIDERS:
        key = os.environ.get(env_name, "").strip()
        if key:
            return (key, base, model)
    return None


def chat(system: str, user: str, temperature: float = 0.0, max_tokens: int = 2000) -> str | None:
    """单轮对话。失败返回 None（调用方自行降级）。"""
    provider = _detect_provider()
    if provider is None:
        return None
    key, base, model = provider
    try:
        with httpx.Client(timeout=60.0) as client:
            resp = client.post(
                f"{base}/chat/completions",
                headers={"Authorization": f"Bearer {key}"},
                json={
                    "model": model,
                    "messages": [{"role": "system", "content": system},
                                 {"role": "user", "content": user}],
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                },
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]
    except Exception as exc:
        logger.warning("LLM 调用失败（{}）: {}", model, exc)
        return None


def chat_json(system: str, user: str, max_tokens: int = 2000) -> list | dict | None:
    """要求 JSON 输出并解析；解析失败返回 None。"""
    content = chat(system, user, temperature=0.0, max_tokens=max_tokens)
    if not content:
        return None
    # 容错：剥掉可能的 ```json 围栏
    text = content.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        try:
            start, end = text.find("["), text.rfind("]")
            if start >= 0 and end > start:
                return json.loads(text[start:end + 1])
            start, end = text.find("{"), text.rfind("}")
            if start >= 0 and end > start:
                return json.loads(text[start:end + 1])
        except json.JSONDecodeError:
            return None
    return None


def llm_available() -> bool:
    return _detect_provider() is not None
