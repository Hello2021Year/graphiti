from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from graph_service.config import get_settings
from graph_service.errors import ResourceNotFoundError, ServiceNotReadyError
from graph_service.routers import ingest, retrieve
from graph_service.zep_graphiti import initialize_graphiti, shutdown_graphiti


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = get_settings()
    await initialize_graphiti(settings)
    yield
    await ingest.shutdown_ingest_queue()
    await shutdown_graphiti()


app = FastAPI(lifespan=lifespan)


app.include_router(retrieve.router)
app.include_router(ingest.router)


@app.exception_handler(ResourceNotFoundError)
async def handle_not_found_exception(_, exc: ResourceNotFoundError):
    return JSONResponse(content={'detail': str(exc)}, status_code=404)


@app.exception_handler(ServiceNotReadyError)
async def handle_service_not_ready_exception(_, exc: ServiceNotReadyError):
    return JSONResponse(content={'detail': str(exc)}, status_code=503)


@app.get('/healthcheck')
async def healthcheck():
    return JSONResponse(content={'status': 'healthy'}, status_code=200)
