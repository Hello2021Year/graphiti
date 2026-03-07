"""
LLM client for doc extraction (no graphiti dependency).
Uses OpenAI-compatible API from config or env.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)


def _parse_json_from_response(response_text: str) -> dict[str, Any]:
    """Parse JSON from LLM response (allow code block wrapper)."""
    s = (response_text or '').strip()
    m = re.search(r'```(?:json)?\s*([\s\S]*?)```', s, re.I)
    if m:
        s = m.group(1).strip()
    i = s.find('{')
    if i == -1:
        return {}
    s = s[i:].strip()
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        pass
    j = max(s.rfind('}'), s.rfind(']'))
    if j != -1:
        try:
            return json.loads(s[: j + 1])
        except json.JSONDecodeError:
            pass
    return {}


def extract_memory_from_chunk(
    chunk_text: str,
    *,
    api_key: str,
    model: str = 'gpt-4o-mini',
    api_base: str | None = None,
    temperature: float = 0.3,
    max_tokens: int = 2048,
) -> dict[str, Any]:
    """
    Call OpenAI-compatible API to extract one memory (key, value, memory_type, tags) from a doc chunk.
    Returns dict with keys: value, key, memory_type, tags (or empty dict on failure).
    """
    from graph_service.parsers.prompts import get_doc_reader_prompt

    prompt = get_doc_reader_prompt(chunk_text)
    base = api_base or 'https://api.openai.com/v1'
    try:
        import httpx

        resp = httpx.post(
            f'{base.rstrip("/")}/chat/completions',
            headers={'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'},
            json={
                'model': model,
                'messages': [{'role': 'user', 'content': prompt}],
                'temperature': temperature,
                'max_tokens': max_tokens,
            },
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()
        content = (data.get('choices') or [{}])[0].get('message', {}).get('content') or ''
        out = _parse_json_from_response(content)
        if not out:
            return {}
        return {
            'value': out.get('value', '').strip(),
            'key': out.get('key', ''),
            'memory_type': out.get('memory_type', 'LongTermMemory'),
            'tags': out.get('tags', []) if isinstance(out.get('tags'), list) else [],
        }
    except Exception as e:
        logger.warning('LLM extract failed for chunk: %s', e)
        return {}
