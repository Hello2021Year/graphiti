import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from graph_service.config import get_settings
from graph_service.routers import ingest, retrieve
from graph_service.routers.ingest import async_worker
from graph_service.zep_graphiti import create_graphiti


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    # if settings.auth_db_path:
    #     os.environ['AUTH_DB_PATH'] = settings.auth_db_path
    # from graph_service.auth.db import init_db
    # init_db()
    client = create_graphiti(settings)
    await client.build_indices_and_constraints()
    app.state.graphiti = client

    # Start async worker for POST /messages (own persistent client to avoid "connection closed")
    # See: https://github.com/getzep/graphiti/pull/1178
    await async_worker.start()

    yield

    await async_worker.stop()
    await client.close()


app = FastAPI(lifespan=lifespan)
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)

# app.include_router(auth.router)
app.include_router(retrieve.router)
app.include_router(ingest.router)


@app.get('/healthcheck')
async def healthcheck():
    return JSONResponse(content={'status': 'healthy'}, status_code=200)
