from sqlalchemy import func, select
import app.seed as seed_module
from app.models import ApiToken, CoachChatMessage, RankApplication, TrainingGroup, Webhook


def counts(factory):
    with factory() as db:
        return [
            db.scalar(select(func.count()).select_from(m))
            for m in (RankApplication, ApiToken, Webhook, CoachChatMessage, TrainingGroup)
        ]


def test_demo_extras_top_up_loaded_base_once(env):
    client, factory, headers, _ = env
    assert counts(factory) == [0, 0, 0, 0, 0]
    # a base loaded before these features gets them on the next --demo run
    seed_module.seed(demo=True)
    assert counts(factory) == [2, 1, 1, 4, 1]
    seed_module.seed(demo=True)
    assert counts(factory) == [2, 1, 1, 4, 1]

    pending = client.get("/api/rank-applications", headers=headers["admin"]).json()
    assert {x["name"] for x in pending if x["status"] == "pending"} == {
        "II", "Судья первой категории"
    }
    assert any("Чемпионат" in (x["basis"] or "") for x in pending)
    links = client.get("/api/links", headers=headers["coach"]).json()
    chats = [
        client.get(f"/api/links/{x['id']}/messages", headers=headers["coach"]).json()
        for x in links
        if x["status"] == "active"
    ]
    assert sorted(len(c) for c in chats)[-1] == 4
    with factory() as db:
        assert db.scalars(select(Webhook)).one().active is False
