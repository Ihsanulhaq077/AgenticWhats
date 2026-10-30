"""LLM provider abstraction.

``mock`` provider: no network calls. The graph falls back to the deterministic
rule-based agent (Baseline 1 in the evaluation plan), so the entire platform
runs offline with zero API keys.

``openai`` provider: any OpenAI-compatible /chat/completions endpoint
(OpenAI, Azure-compatible gateways, Groq, OpenRouter, local vLLM/Ollama...).
"""

from typing import Any

import httpx

from app.config.settings import get_settings

settings = get_settings()


class LLMService:
    @property
    def available(self) -> bool:
        return settings.llm_provider == "openai" and bool(settings.llm_api_key)

    @property
    def mode(self) -> str:
        return "openai-compatible" if self.available else "rule-based-mock"

    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict] | None = None,
        temperature: float = 0.2,
        max_tokens: int = 600,
    ) -> dict[str, Any]:
        """Return {"content": str, "tool_calls": [{"name","arguments"}]}."""
        if not self.available:
            return {"content": "", "tool_calls": []}
        payload: dict[str, Any] = {
            "model": settings.llm_model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if tools:
            payload["tools"] = [
                {"type": "function", "function": t} if "function" not in t else t for t in tools
            ]
        resp = httpx.post(
            f"{settings.llm_base_url.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {settings.llm_api_key}"},
            json=payload,
            timeout=60,
        )
        resp.raise_for_status()
        choice = resp.json()["choices"][0]["message"]
        tool_calls = []
        for tc in choice.get("tool_calls") or []:
            fn = tc.get("function", {})
            args = fn.get("arguments")
            if isinstance(args, str):
                import json
                try:
                    args = json.loads(args)
                except ValueError:
                    args = {}
            tool_calls.append({"id": tc.get("id", ""), "name": fn.get("name", ""), "arguments": args or {}})
        raw = dict(choice)
        raw.setdefault("role", "assistant")
        return {"content": choice.get("content") or "", "tool_calls": tool_calls, "raw": raw}


llm_service = LLMService()
