import asyncio
from contextlib import asynccontextmanager, suppress
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from app.config import settings
from app.db import engine
from app.routers import auth, registry, staff, competitions, federation, reports, public
from app.routers import awards, competition_teams, indicators, passports
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


@app.middleware("http")
async def public_privacy_headers(request, call_next):
    response = await call_next(request)
    if request.url.path.startswith(
        (
            "/api/public/",
            "/api/auth/",
            "/api/my/profile-visibility",
            "/api/athlete-profiles/",
            "/api/results",
        )
    ):
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Robots-Tag"] = "noindex, nofollow, noarchive"
        response.headers["X-Content-Type-Options"] = "nosniff"
    return response


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
    auth.router,
    registry.router,
    staff.router,
    competitions.router,
    competition_teams.router,
    passports.router,
    federation.router,
    reports.router,
    indicators.router,
    awards.router,
    public.router,
]:
    app.include_router(router, prefix="/api")
