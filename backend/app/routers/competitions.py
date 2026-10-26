from datetime import date
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.db import get_db
from app.models import *
from app.schemas import (
    CompetitionIn,
    StateIn,
    ApplicationIn,
    Decision,
    ResultsIn,
    JudgeIn,
    NameIn,
)
from app.security import Actor, current_actor, allow
from app.services.common import *
from app.services.notifications import notify, admins, athlete_audience
from app.services.ratings import recalculate

router = APIRouter(tags=["Соревнования"])


def locked(db, key):
    obj = db.scalar(select(Competition).where(Competition.id == key).with_for_update())
    if not obj:
        raise HTTPException(404, "Соревнование не найдено")
    return obj


def competition_view(db, comp, actor):
    data = row(comp)
    data["discipline"] = db.get(Discipline, comp.discipline_id).short_name
    data["participants"] = len(
        db.scalars(
            select(CompetitionApplication.id).where(
                CompetitionApplication.competition_id == comp.id,
                CompetitionApplication.status == "approved",
            )
        ).all()
    )
    data["eligible"] = None
    if actor.role == "athlete":
        athlete = own(db, Athlete, actor)
        data["eligible"] = (
            comp.min_age
            <= age_at(athlete.user.birth_date, comp.start_date)
            <= comp.max_age
        )
    return data


@router.get("/competitions")
def competitions(
    discipline_id: int | None = None,
    state: str = "",
    q: str = "",
    eligible: bool = False,
    actor: Actor = Depends(current_actor),
    db: Session = Depends(get_db),
):
    query = select(Competition).order_by(Competition.start_date.desc())
    if actor.role != "admin":
        query = query.where(Competition.state != "draft")
    if discipline_id:
        query = query.where(Competition.discipline_id == discipline_id)
    if state:
        query = query.where(Competition.state == state)
    items = [
        competition_view(db, c, actor)
        for c in db.scalars(query)
        if q.lower() in c.title.lower()
    ]
    return [c for c in items if not eligible or c["eligible"] is not False]


@router.post("/competitions", status_code=201)
def create(
    data: CompetitionIn,
    actor: Actor = Depends(allow("admin")),
    db: Session = Depends(get_db),
):
    require(db, Discipline, data.discipline_id)
    require(db, CompetitionType, data.type_id)
    obj = Competition(
        **data.model_dump(exclude={"regulation_url"}),
        regulation_url=str(data.regulation_url) if data.regulation_url else None,
    )
    db.add(obj)
    audit(db, actor, "Создание соревнования", obj)
    return row(obj)


@router.put("/competitions/{comp_id}")
def update(
    comp_id: int,
    data: CompetitionIn,
    actor: Actor = Depends(allow("admin")),
    db: Session = Depends(get_db),
):
    obj = locked(db, comp_id)
    if obj.state != "draft":
        raise HTTPException(409, "Редактировать можно только черновик")
    require(db, Discipline, data.discipline_id)
    require(db, CompetitionType, data.type_id)
    for k, v in data.model_dump(exclude={"regulation_url"}).items():
        setattr(obj, k, v)
    obj.regulation_url = str(data.regulation_url) if data.regulation_url else None
    audit(db, actor, "Изменение соревнования", obj)
    return row(obj)


@router.delete("/competitions/{comp_id}", status_code=204)
def remove(
    comp_id: int, actor: Actor = Depends(allow("admin")), db: Session = Depends(get_db)
):
    obj = locked(db, comp_id)
    if obj.state != "draft":
        raise HTTPException(409, "Удалить можно только черновик")
    audit(db, actor, "Удаление соревнования", obj)
    db.delete(obj)


@router.patch("/competitions/{comp_id}/state")
def set_state(
    comp_id: int,
    data: StateIn,
    actor: Actor = Depends(allow("admin")),
    db: Session = Depends(get_db),
):
    comp = locked(db, comp_id)
    if (
        data.state
        not in {
            "draft": ["open"],
            "open": ["closed"],
            "closed": ["open"],
            "published": [],
        }[comp.state]
    ):
        raise HTTPException(409, "Недопустимый переход статуса")
    if data.state == "open" and comp.deadline < date.today():
        raise HTTPException(422, "Срок подачи заявок уже прошёл")
    comp.state = data.state
    comp.revision += 1
    audit(db, actor, "Изменение статуса соревнования", comp, {"state": data.state})
    if data.state == "open":
        notify(
            db,
            db.scalars(select(User.id)).all(),
            "Открыта регистрация",
            comp.title,
            f"competition-open:{comp.id}:{comp.revision}",
        )
    return row(comp)


@router.get("/competitions/{comp_id}")
def detail(
    comp_id: int, actor: Actor = Depends(current_actor), db: Session = Depends(get_db)
):
    comp = require(db, Competition, comp_id)
    if comp.state == "draft" and actor.role != "admin":
        raise HTTPException(404, "Соревнование не найдено")
    applications = select(CompetitionApplication).where(
        CompetitionApplication.competition_id == comp.id
    )
    if actor.role != "admin":
        applications = applications.where(
            CompetitionApplication.athlete_id.in_(visible_athletes(db, actor))
        )
    judges = db.scalars(
        select(CompetitionJudge).where(CompetitionJudge.competition_id == comp.id)
    ).all()
    return {
        **competition_view(db, comp, actor),
        "applications": [
            {**row(a), "full_name": db.get(Athlete, a.athlete_id).user.full_name}
            for a in db.scalars(applications)
        ],
        "results": [
            {**row(r), "full_name": db.get(Athlete, r.athlete_id).user.full_name}
            for r in db.scalars(
                select(CompetitionResult)
                .where(CompetitionResult.competition_id == comp.id)
                .order_by(CompetitionResult.place)
            )
        ]
        if comp.state == "published" or actor.role == "admin"
        else [],
        "judges": [
            {**row(j), "full_name": db.get(Judge, j.judge_id).user.full_name}
            for j in judges
        ],
    }


@router.post("/competitions/{comp_id}/applications", status_code=201)
def apply(
    comp_id: int,
    data: ApplicationIn,
    actor: Actor = Depends(allow("athlete", "coach")),
    db: Session = Depends(get_db),
):
    comp = locked(db, comp_id)
    athlete = can_athlete(db, actor, data.athlete_id, comp.discipline_id)
    if comp.state != "open" or comp.deadline < date.today():
        raise HTTPException(409, "Приём заявок закрыт")
    if athlete.suspended_until and athlete.suspended_until >= date.today():
        raise HTTPException(422, "У спортсмена действует отстранение")
    if (
        not comp.min_age
        <= age_at(athlete.user.birth_date, comp.start_date)
        <= comp.max_age
    ):
        raise HTTPException(
            422, "Спортсмен не подходит по возрасту на дату соревнования"
        )
    enrollment = db.get(AthleteDiscipline, (athlete.id, comp.discipline_id))
    if (
        not enrollment
        or enrollment.start_year > comp.start_date.year
        or enrollment.end_year is not None
        and enrollment.end_year < comp.start_date.year
    ):
        raise HTTPException(422, "Добавьте действующую дисциплину в профиль спортсмена")
    obj = CompetitionApplication(
        competition_id=comp.id, athlete_id=athlete.id, submitted_by=actor.user.id
    )
    db.add(obj)
    audit(db, actor, "Подача заявки", obj)
    notify(
        db,
        admins(db),
        "Новая заявка на соревнование",
        f"{athlete.user.full_name}: {comp.title}",
        f"application:{obj.id}",
    )
    return row(obj)


@router.patch("/applications/{application_id}")
def moderate(
    application_id: int,
    data: Decision,
    actor: Actor = Depends(allow("admin")),
    db: Session = Depends(get_db),
):
    obj = require(db, CompetitionApplication, application_id)
    comp = locked(db, obj.competition_id)
    if comp.state == "published" or obj.status != "pending":
        raise HTTPException(409, "Заявка уже рассмотрена или протокол опубликован")
    obj.status, obj.comment = data.status, data.comment
    audit(db, actor, "Рассмотрение заявки", obj, data.model_dump())
    notify(
        db,
        athlete_audience(db, obj.athlete_id),
        "Статус заявки изменён",
        f"{comp.title}: {data.status}. {data.comment}",
        f"application-decision:{obj.id}",
    )
    return row(obj)


@router.post("/competitions/{comp_id}/judges", status_code=201)
def assign_judge(
    comp_id: int,
    data: JudgeIn,
    actor: Actor = Depends(allow("admin")),
    db: Session = Depends(get_db),
):
    comp = locked(db, comp_id)
    judge = require(db, Judge, data.judge_id)
    if comp.state == "published":
        raise HTTPException(409, "Протокол уже опубликован")
    category = db.scalar(
        select(JudgeCategory).where(
            JudgeCategory.judge_id == judge.id,
            JudgeCategory.expires_on >= comp.end_date,
        )
    )
    if not category:
        raise HTTPException(
            422, "Нет судейской категории, действующей до окончания соревнования"
        )
    obj = CompetitionJudge(
        competition_id=comp.id, judge_id=judge.id, position=data.position
    )
    db.add(obj)
    audit(db, actor, "Назначение судьи", comp, data.model_dump())
    notify(
        db,
        [judge.user_id],
        "Назначение на соревнование",
        f"{comp.title}: {data.position}",
        f"judge:{comp.id}:{judge.id}",
    )
    return row(obj)


@router.post("/competitions/{comp_id}/results")
def publish(
    comp_id: int,
    data: ResultsIn,
    actor: Actor = Depends(allow("admin")),
    db: Session = Depends(get_db),
):
    comp = locked(db, comp_id)
    if comp.state != "closed":
        raise HTTPException(409, "Закройте приём заявок перед публикацией")
    if comp.end_date > date.today():
        raise HTTPException(422, "Соревнование ещё не завершено")
    approved = set(
        db.scalars(
            select(CompetitionApplication.athlete_id).where(
                CompetitionApplication.competition_id == comp.id,
                CompetitionApplication.status == "approved",
            )
        ).all()
    )
    ids = [r.athlete_id for r in data.results]
    places = [r.place for r in data.results]
    if (
        set(ids) != approved
        or len(set(ids)) != len(ids)
        or sorted(places) != list(range(1, len(approved) + 1))
    ):
        raise HTTPException(
            422,
            "Нужны результаты всех одобренных участников с уникальными местами от 1 до N",
        )
    db.add_all(
        [
            CompetitionResult(competition_id=comp.id, **r.model_dump())
            for r in data.results
        ]
    )
    comp.state = "published"
    audit(
        db,
        actor,
        "Публикация результатов и протокола",
        comp,
        {"participants": len(ids)},
    )
    recalculate(db, comp.start_date.year)
    for athlete_id in approved:
        notify(
            db,
            athlete_audience(db, athlete_id),
            "Опубликован протокол",
            comp.title,
            f"protocol:{comp.id}:{athlete_id}",
        )
    return {"state": comp.state, "count": len(ids)}


@router.get("/results")
def history(
    athlete_id: int | None = None,
    actor: Actor = Depends(current_actor),
    db: Session = Depends(get_db),
):
    ids = visible_athletes(db, actor)
    if athlete_id:
        can_athlete(db, actor, athlete_id)
        ids = {athlete_id}
    return [
        {
            **row(r),
            "full_name": db.get(Athlete, r.athlete_id).user.full_name,
            "title": c.title,
            "start_date": c.start_date,
            "discipline_id": c.discipline_id,
            "level": c.level,
        }
        for r, c in db.execute(
            select(CompetitionResult, Competition)
            .join(Competition, Competition.id == CompetitionResult.competition_id)
            .where(
                CompetitionResult.athlete_id.in_(ids), Competition.state == "published"
            )
            .order_by(Competition.start_date.desc())
        )
    ]


@router.get("/assignments")
def assignments(
    actor: Actor = Depends(allow("admin", "judge")), db: Session = Depends(get_db)
):
    query = select(CompetitionJudge, Competition).join(
        Competition, Competition.id == CompetitionJudge.competition_id
    )
    if actor.role == "judge":
        query = query.where(CompetitionJudge.judge_id == own(db, Judge, actor).id)
    return [
        {**row(j), "title": c.title, "start_date": c.start_date, "state": c.state}
        for j, c in db.execute(query)
    ]


@router.post("/competition-types", status_code=201)
def add_type(
    data: NameIn, actor: Actor = Depends(allow("admin")), db: Session = Depends(get_db)
):
    obj = CompetitionType(name=data.name)
    db.add(obj)
    audit(db, actor, "Создание типа соревнования", obj)
    return row(obj)
