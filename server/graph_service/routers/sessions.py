"""Sessions: list and get session detail (user history)."""

from fastapi import APIRouter, HTTPException, Query

from graph_service.dto.session_dto import MessageItem, SessionDetail, SessionSummary
from graph_service.services.session_service import (
    create_session,
    get_session,
    get_session_messages,
    list_sessions,
)

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.get("", response_model=list[SessionSummary])
async def list_user_sessions(
    user_id: int = Query(..., description="User ID (from login)"),
) -> list[SessionSummary]:
    rows = await list_sessions(user_id)
    return [
        SessionSummary(
            id=r["id"],
            user_id=r["user_id"],
            name=r["name"],
            created_at=r["created_at"],
            updated_at=r["updated_at"],
        )
        for r in rows
    ]


@router.post("", response_model=SessionSummary)
async def create_user_session(
    user_id: int = Query(..., description="User ID"),
    name: str = Query("New session", description="Session name"),
) -> SessionSummary:
    sid = await create_session(user_id, name)
    row = await get_session(sid, user_id)
    if not row:
        raise HTTPException(status_code=500, detail="Failed to create session")
    return SessionSummary(
        id=row["id"],
        user_id=row["user_id"],
        name=row["name"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


@router.get("/{session_id}", response_model=SessionDetail)
async def get_session_detail(
    session_id: int,
    user_id: int = Query(..., description="User ID"),
) -> SessionDetail:
    session = await get_session(session_id, user_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    messages = await get_session_messages(session_id, user_id)
    return SessionDetail(
        id=session["id"],
        user_id=session["user_id"],
        name=session["name"],
        created_at=session["created_at"],
        updated_at=session["updated_at"],
        messages=[
            MessageItem(
                id=m["id"],
                session_id=m["session_id"],
                role=m["role"],
                content=m["content"],
                created_at=m["created_at"],
            )
            for m in messages
        ],
    )
