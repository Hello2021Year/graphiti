"""
File processing: parse doc/md to Markdown and chunk for graph ingest.
Follows MemOS (MemReader) approach: markitdown for file→md, chonkie for sentence chunking.
Modes: fast (graphiti default), fine (smaller chunks), memos (MemOS-style: chonkie SentenceChunker).
"""

from __future__ import annotations

import logging
import os
from typing import Literal

from graphiti_core.utils.content_chunking import chunk_text_content  # type: ignore

from graph_service.parsers import parse_file

logger = logging.getLogger(__name__)

IngestMode = Literal['fast', 'fine', 'memos']

# Fine mode: smaller chunks for finer-grained episodes
FINE_CHUNK_SIZE_TOKENS = 800
FINE_OVERLAP_TOKENS = 100

# MemOS/chonkie defaults (SentenceChunker: chunk_size in tokens, chunk_overlap)
MEMOS_CHUNK_SIZE = 2048
MEMOS_CHUNK_OVERLAP = 128


def _chunk_with_chonkie(text: str) -> list[str]:
    """Chunk text with chonkie SentenceChunker (MemOS mem-reader style). Returns list of chunk texts."""
    try:
        from chonkie import SentenceChunker  # type: ignore
    except ImportError:
        logger.warning(
            'chonkie not installed; fallback to graphiti chunk_text_content for memos mode'
        )
        return chunk_text_content(text)
    chunker = SentenceChunker(
        chunk_size=MEMOS_CHUNK_SIZE,
        chunk_overlap=MEMOS_CHUNK_OVERLAP,
    )
    chunks = chunker.chunk(text)
    return [c.text for c in chunks] if chunks else [text]


def process_doc_or_md(path_or_content: str, mode: IngestMode = 'fast') -> list[str]:
    """Parse doc/md (file path or raw Markdown) and return list of text chunks.

    - If path_or_content is an existing file path, it is parsed with MarkItDown (MemOS uses markitdown) first.
    - Otherwise it is treated as raw Markdown string.
    - fast: default chunk size/overlap from graphiti_core.
    - fine: smaller chunks (FINE_*) for finer-grained ingest.
    - memos: MemOS-style — chonkie SentenceChunker (sentence boundaries, chunk_size/overlap like MemReader).
      Requires optional dependency: pip install graph-service[mem-reader] or chonkie.

    Returns:
        List of text chunks to be turned into RawEpisodes for add_episode_bulk.
    """
    if os.path.isfile(path_or_content):
        text = parse_file(path_or_content)
    else:
        text = path_or_content

    text = (text or '').strip()
    if not text:
        return []

    if mode == 'memos':
        chunks = _chunk_with_chonkie(text)
    elif mode == 'fine':
        chunks = chunk_text_content(
            text,
            chunk_size_tokens=FINE_CHUNK_SIZE_TOKENS,
            overlap_tokens=FINE_OVERLAP_TOKENS,
        )
    else:
        chunks = chunk_text_content(text)

    logger.debug('process_doc_or_md mode=%s -> %s chunks', mode, len(chunks))
    return chunks
