"""
Chunk text (MemOS-style). No graphiti dependency.
Uses chonkie if available, else simple size-based split.
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_CHUNK_SIZE = int(os.environ.get('FILE_PARSER_CHUNK_SIZE', '1280'))
DEFAULT_CHUNK_OVERLAP = int(os.environ.get('FILE_PARSER_CHUNK_OVERLAP', '200'))


def chunk_text(
    text: str,
    chunk_size: int | None = None,
    chunk_overlap: int | None = None,
    backend: str = 'sentence',
) -> list[str]:
    """
    Split text into chunks. Backend: 'sentence' (chonkie if available) or 'simple'.
    Returns list of chunk strings.
    """
    text = (text or '').strip()
    if not text:
        return []
    size = chunk_size or DEFAULT_CHUNK_SIZE
    overlap = chunk_overlap or DEFAULT_CHUNK_OVERLAP

    if backend == 'sentence':
        try:
            from chonkie import SentenceChunker  # type: ignore

            c = SentenceChunker(chunk_size=size, chunk_overlap=overlap)
            chunks = c.chunk(text)
            return [chunk.text for chunk in chunks] if chunks else [text]
        except ImportError:
            logger.debug('chonkie not installed, using simple chunker')
            backend = 'simple'

    if backend == 'simple':
        return _simple_chunk(text, size, overlap)
    return _simple_chunk(text, size, overlap)


def _simple_chunk(text: str, chunk_size: int, overlap: int) -> list[str]:
    """Character-based chunking with overlap (approx tokens ~ 4 chars)."""
    char_size = chunk_size * 4
    char_overlap = overlap * 4
    out = []
    start = 0
    while start < len(text):
        end = min(start + char_size, len(text))
        chunk = text[start:end]
        if chunk.strip():
            out.append(chunk)
        start = end - char_overlap
        if start >= len(text):
            break
    return out if out else [text]
