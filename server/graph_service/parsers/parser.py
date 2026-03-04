"""
File-to-Markdown parser using Microsoft MarkItDown.
Used by the file ingest API to convert uploaded files to text for graph building.
"""
import logging

logger = logging.getLogger(__name__)


def parse_file(file_path: str) -> str:
    """Parse the file at the given path and return its content as Markdown text.

    Uses MarkItDown (https://github.com/microsoft/markitdown) to support
    PDF, Word, Excel, PowerPoint, images, HTML, etc.

    Args:
        file_path: Absolute or relative path to the file.

    Returns:
        Markdown string content of the file.

    Raises:
        Exception: On unsupported format or read/convert errors.
    """
    from markitdown import MarkItDown

    md = MarkItDown(enable_plugins=False)
    result = md.convert(file_path)
    text = result.text_content or ''
    logger.debug('Parsed file %s -> %s chars', file_path, len(text))
    return text
