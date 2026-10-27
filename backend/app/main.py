import asyncio
from contextlib import asynccontextmanager, suppress
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from app.config import settings
from app.db import engine
from app.routers import auth, registry, staff, competitions, federation, reports, telegram
from app.services.notifications import worker


@asynccontextmanager
async def lifespan(app):
    task = asyncio.create_task(worker()) if settings.notifications_worker else None
    yield
    if task:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
    engine.dispose()


app = FastAPI(title="ОренКод · Платформа ФСП", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins.split(","),
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "X-Active-Role"],
)


@app.exception_handler(IntegrityError)
async def integrity_error(request: Request, exc: IntegrityError):
    return JSONResponse(
        status_code=409,
        content={
            "detail": "Запись уже существует или нарушена целостность связанных данных"
        },
    )


@app.get("/api/health", tags=["Состояние"])
def health():
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    return {"status": "ok", "database": "connected"}


for router in [
    telegram.router,
    auth.router,
    registry.router,
    staff.router,
    competitions.router,
    federation.router,
    reports.router,
]:
    app.include_router(router, prefix="/api")
