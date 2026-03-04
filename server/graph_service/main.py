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


app.include_router(retrieve.router)
app.include_router(ingest.router)


@app.get('/healthcheck')
async def healthcheck():
    return JSONResponse(content={'status': 'healthy'}, status_code=200)
