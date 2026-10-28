import os

os.environ.setdefault("JWT_SECRET", "test-secret-longer-than-thirty-two-characters")
os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ["NOTIFICATIONS_WORKER"] = "false"
os.environ.setdefault(
    "PDF_FONT",
    r"C:/Windows/Fonts/arial.ttf"
    if os.name == "nt"
    else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
)
import pytest
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient
from app.db import Base, get_db
from app.main import app
import app.seed as seed_module


@pytest.fixture()
def env(monkeypatch):
    url = os.getenv("TEST_DATABASE_URL", "sqlite://")
    if url.startswith("postgresql") and make_url(url).database != "orencode_test":
        raise RuntimeError(
            "TEST_DATABASE_URL must point to a disposable orencode_test database"
        )
    kwargs = (
        {"connect_args": {"check_same_thread": False}, "poolclass": StaticPool}
        if url == "sqlite://"
        else {}
    )
    engine = create_engine(url, **kwargs)
    if url == "sqlite://":
        from sqlalchemy import event

        @event.listens_for(engine, "connect")
        def fk(conn, _):
            conn.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(seed_module, "SessionLocal", factory)
    seed_module.seed(demo=True, extras=False)

    def db_override():
        with factory() as db:
            try:
                yield db
                db.commit()
            except Exception:
                db.rollback()
                raise

    app.dependency_overrides[get_db] = db_override
    with TestClient(app) as client:

        def login(email, role):
            client.cookies.clear()
            res = client.post(
                "/api/auth/login",
                json={"email": email + "@demo.example", "password": "DemoPass2026!"},
            )
            assert res.status_code == 200, res.text
            data = res.json()
            client.cookies.clear()
            return {
                "Authorization": "Bearer " + data["access_token"],
                "X-Active-Role": role,
            }, data["user"]

        admin, admin_user = login("admin", "admin")
        athlete, athlete_user = login("athlete", "athlete")
        coach, coach_user = login("coach", "coach")
        judge, judge_user = login("judge", "judge")
        yield (
            client,
            factory,
            {"admin": admin, "athlete": athlete, "coach": coach, "judge": judge},
            {
                "admin": admin_user,
                "athlete": athlete_user,
                "coach": coach_user,
                "judge": judge_user,
            },
        )
    app.dependency_overrides.clear()
    Base.metadata.drop_all(engine)
    engine.dispose()
