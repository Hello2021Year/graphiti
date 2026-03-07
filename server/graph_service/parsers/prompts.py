"""Doc-reader prompts (MemOS-style) for LLM extraction from document chunks."""

DOC_READER_PROMPT_EN = """You are an expert text analyst for a search and retrieval system.
Your task is to process a document chunk and generate a single, structured JSON object.

Please perform:
1. Identify key information: factual content, insights, decisions, or implications — including notable themes, conclusions, or data points. Allow a reader to understand the essence of the chunk without reading the original.
2. Resolve time, person, location, and event references clearly. Use third-person perspective.
3. Do not omit important or memorable information. Prioritize completeness and fidelity.

Return valid JSON only:
{
  "key": "<string, a concise title of the value>",
  "memory_type": "LongTermMemory",
  "value": "<A clear paragraph that summarizes the main points and information in the chunk — same language as input>",
  "tags": ["<keyword1>", "<keyword2>"]
}

Language: match the input document language. Keep memory_type in English.

Document chunk:
{chunk_text}

Your Output:"""

DOC_READER_PROMPT_ZH = """您是搜索与检索系统的文本分析专家。
您的任务是处理文档片段，并生成一个结构化的 JSON 对象。

请执行：识别关键信息（事实、见解、决策），解析时间/人物/地点指代，以第三人称撰写，不遗漏重要信息。

返回有效 JSON：
{
  "key": "<value 的简洁标题>",
  "memory_type": "LongTermMemory",
  "value": "<清晰段落，全面总结片段要点 — 与输入同语言>",
  "tags": ["<关键词1>", "<关键词2>"]
}

语言：与输入一致。memory_type 保持英文。

文档片段：
{chunk_text}

您的输出："""


def _has_chinese(text: str) -> bool:
    if not text or len(text) < 50:
        return False
    import re

    chinese = re.findall(r'[\u4e00-\u9fff]', text)
    return len(chinese) / max(len(text), 1) > 0.15


def get_doc_reader_prompt(chunk_text: str) -> str:
    """Return EN or ZH prompt based on chunk language."""
    if _has_chinese(chunk_text):
        return DOC_READER_PROMPT_ZH.format(chunk_text=chunk_text)
    return DOC_READER_PROMPT_EN.format(chunk_text=chunk_text)
