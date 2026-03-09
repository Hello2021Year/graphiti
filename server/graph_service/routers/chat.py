"""Chat: add message, retrieve memory (search), call UCloud LLM, save history."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

from graph_service.dto.chat_dto import ChatRequest, ChatResponse
from graph_service.services.llm_service import chat_completion
from graph_service.services.session_service import (
    add_message,
    create_session,
    get_session_messages,
)

router = APIRouter(prefix="/chat", tags=["chat"])

# Max recent turns to include in context (user + assistant pairs)
RECENT_TURNS = 10


def _format_memory_context(search_results: list[Any] | None) -> str:
    if not search_results:
        return ""
    parts = []
    for r in search_results:
        if hasattr(r, "content"):
            parts.append(str(r.content))
        elif isinstance(r, dict) and "content" in r:
            parts.append(str(r["content"]))
        else:
            parts.append(str(r))
    if not parts:
        return ""
    return "Relevant memory:\n" + "\n".join(parts[:15])  # cap at 15 items


async def _get_memory_context(user_id: int, query: str, graphiti: Any | None) -> str:
    """If graphiti is available, run search and return formatted context."""
    if graphiti is None:
        return ""
    try:
        # search_async(query_text, user_id=str(user_id), ...)
        results = await graphiti.search_async(query, str(user_id))
        return _format_memory_context(results)
    except Exception:
        return ""


@router.post("", response_model=ChatResponse)
async def chat(
    req: ChatRequest,
    request: Request,
) -> ChatResponse:
    user_id = req.user_id
    session_id = req.session_id
    message = (req.message or "").strip()
    if not message:
        raise HTTPException(status_code=400, detail="message is required")

    if session_id is None:
        session_id = await create_session(
            user_id, name=req.session_name or "New session"
        )

    await add_message(session_id, user_id, "user", message)

    graphiti = getattr(request.app.state, "graphiti", None)
    if graphiti is not None:
        try:
            await graphiti.add_memory_async(message, str(user_id))
        except Exception:
            pass
    memory_context = await _get_memory_context(user_id, message, graphiti)

    # Build conversation history from DB (recent turns)
    history = await get_session_messages(session_id, user_id)
    # Exclude the message we just added from "history" for the LLM (we add it as the latest)
    turns = [
        (h["role"], h["content"])
        for h in history
        if h["role"] in ("user", "assistant")
    ]

    system_parts = []
    if memory_context:
        system_parts.append(memory_context)
    system_parts.append(
        "You are a helpful assistant. Use the conversation history and any relevant memory above to respond."
    )
    system_content = "\n\n".join(system_parts)

    messages_for_llm: list[dict[str, str]] = [
        {"role": "system", "content": system_content}
    ]
    for role, content in turns[-RECENT_TURNS * 2 :]:
        messages_for_llm.append({"role": role, "content": content})

    try:
        reply = await chat_completion(messages_for_llm)
    except ValueError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"LLM error: {e}")

    await add_message(session_id, user_id, "assistant", reply)

    return ChatResponse(session_id=session_id, reply=reply)
