"""Graphiti server: auth, chat with LLM + memory, user sessions."""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from graph_service.db import close_db, init_db
from graph_service.routers import auth, chat, sessions

# TODO: auth middleware for protected routes; currently no鉴权
# TODO: real verification code send (email); default code 20250325 for dev


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield
    await close_db()


app = FastAPI(
    title="Graphiti Graph Service",
    description="Auth (email+code), chat with UCloud LLM and user memory, session history.",
    lifespan=lifespan,
)

app.include_router(auth.router)
app.include_router(chat.router)
app.include_router(sessions.router)


@app.get("/health")
async def health():
    return {"status": "ok"}
