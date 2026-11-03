from contextlib import asynccontextmanager

import asyncpg
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
import httpx

from app.db import create_pool
from app.tenders.policy import DomainError
from app.tenders.repository import Repository
from app.tenders.routes import router
from app.tenders.storage import SourceStorage


def create_app():
    @asynccontextmanager
    async def lifespan(app):
        pool = await create_pool()
        try:
            async with httpx.AsyncClient(timeout=15,follow_redirects=False) as auth_client:
                app.state.pool = pool
                app.state.auth_client = auth_client
                app.state.repository = Repository(pool)
                app.state.storage = SourceStorage(auth_client)
                yield
        finally:
            await pool.close()

    application = FastAPI(title="Tender Intelligence API",version="0.1.0",lifespan=lifespan)
    application.include_router(router)

    async def database_unavailable(request: Request, error: Exception):
        return JSONResponse(status_code=503,content={"code":"DATABASE_UNAVAILABLE",
            "message":"The database is temporarily unavailable; retry this request.","retryable":True})

    for error_type in (ConnectionError,TimeoutError,asyncpg.PostgresConnectionError,
                       asyncpg.CannotConnectNowError,asyncpg.TooManyConnectionsError):
        application.add_exception_handler(error_type,database_unavailable)

    @application.exception_handler(DomainError)
    async def domain_error(request: Request, error: DomainError):
        return JSONResponse(status_code=error.status_code,
                            content={"code":error.code,"message":error.message,"retryable":error.status_code==503})

    @application.exception_handler(RequestValidationError)
    async def validation_error(request: Request, error: RequestValidationError):
        return JSONResponse(status_code=422,content={"code":"INVALID_REQUEST","message":"The request does not match the endpoint schema.","retryable":False})

    @application.get("/health")
    async def health():
        return {"status":"ok"}

    return application


app = create_app()
