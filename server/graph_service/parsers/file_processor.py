"""
File processing (MemOS-style): parse doc/md → chunk → optional LLM extract.
All logic in parsers folder; no graphiti dependency.
Returns list of message-like dicts {content, tags, memory_type} for downstream use.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from graph_service.parsers.chunker import chunk_text
from graph_service.parsers.llm_client import extract_memory_from_chunk
from graph_service.parsers.parser import parse_file

logger = logging.getLogger(__name__)


def process_file_to_messages(
    path_or_content: str,
    mode: str = 'fast',
    *,
    use_llm: bool = False,
    api_key: str | None = None,
    model: str = 'gpt-4o-mini',
    api_base: str | None = None,
    chunk_size: int | None = None,
    chunk_overlap: int | None = None,
) -> list[dict[str, Any]]:
    """
    Parse a doc/md file (or raw content) and return list of message-like dicts.

    - path_or_content: file path (existing) or raw Markdown string.
    - mode: 'fast' (chunk only) or 'fine' (chunk + LLM extraction per chunk).
    - use_llm: if True and mode=='fine', call LLM to extract structured memory per chunk.
    - api_key, model, api_base: for LLM (or from env OPENAI_API_KEY etc.).
    - chunk_size, chunk_overlap: optional; else from env FILE_PARSER_* or defaults.

    Returns list of dicts: {content: str, tags: list, memory_type: str}.
    No graphiti code; caller may map these to RawEpisode or elsewhere.
    """
    if os.path.isfile(path_or_content):
        text = parse_file(path_or_content)
    else:
        text = path_or_content
    text = (text or '').strip()
    if not text:
        return []

    chunks = chunk_text(
        text,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        backend='sentence',
    )
    if not chunks:
        return [{'content': text, 'tags': ['mode:fast'], 'memory_type': 'LongTermMemory'}]

    if mode == 'fine' and use_llm and api_key:
        messages = []
        for i, chunk in enumerate(chunks):
            if not chunk.strip():
                continue
            extracted = extract_memory_from_chunk(
                chunk,
                api_key=api_key,
                model=model,
                api_base=api_base,
            )
            if extracted.get('value'):
                messages.append(
                    {
                        'content': extracted['value'],
                        'tags': extracted.get('tags', []) + ['mode:fine', 'multimodal:file'],
                        'memory_type': extracted.get('memory_type', 'LongTermMemory'),
                    }
                )
            else:
                messages.append(
                    {
                        'content': chunk,
                        'tags': ['mode:fine', 'fallback:no_llm'],
                        'memory_type': 'LongTermMemory',
                    }
                )
        logger.info(
            'File processed (fine+LLM): %s chunks -> %s messages', len(chunks), len(messages)
        )
        return messages

    return [
        {'content': c, 'tags': ['mode:fast', 'multimodal:file'], 'memory_type': 'LongTermMemory'}
        for c in chunks
        if c.strip()
    ]
