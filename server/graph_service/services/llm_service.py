"""Call third-party LLM (UCloud) for chat completion."""

from typing import Any

import httpx

from graph_service.config import get_settings


async def chat_completion(
    messages: list[dict[str, str]],
    *,
    model: str | None = None,
    max_tokens: int = 2048,
) -> str:
    """Call UCloud LLM chat API. messages: [{"role": "user"|"assistant"|"system", "content": "..."}]."""
    settings = get_settings()
    if not settings.UCLOUD_API_KEY:
        raise ValueError("UCLOUD_API_KEY not configured")
    url = f"{settings.UCLOUD_LLM_BASE_URL.rstrip('/')}/chat/completions"
    payload: dict[str, Any] = {
        "model": model or settings.UCLOUD_LLM_MODEL,
        "messages": messages,
        "max_tokens": max_tokens,
    }
    headers = {
        "Authorization": f"Bearer {settings.UCLOUD_API_KEY}",
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()
    choices = data.get("choices") or []
    if not choices:
        return ""
    msg = choices[0].get("message") or {}
    return (msg.get("content") or "").strip()
