from datetime import date
from pathlib import PurePath
from typing import Literal
from urllib.parse import quote
from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session
from app.db import get_db
from app.models import *
from app.schemas import (
    CompetitionIn,
    StateIn,
    ApplicationIn,
    Decision,
    ResultsIn,
    ProtocolCorrectionIn,
    JudgeIn,
    CompetitionTypeIn,
    AgeGroupIn,
)
from app.security import Actor, current_actor, allow
from app.services.common import *
from app.services.notifications import notify, admins, athlete_audience
from app.services.ratings import recalculate, rating_level
from app.services.competition_teams import expand_results
from app.services.protocols import (
    add_version,
    check_entries,
    current_results,
    rank_warnings,
    version_history,
)
from app.services.age_groups import (
    age_check,
    age_error,
    competition_groups,
    group_view,
)

router = APIRouter(tags=["Соревнования"])

REGULATION_MAX_SIZE = 10 * 1024 * 1024
REGULATION_TYPES = {
    ".pdf": ("application/pdf", (b"%PDF-",)),
    ".docx": (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        (b"PK\x03\x04",),
    ),
    ".doc": ("application/msword", (b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1",)),
    ".odt": ("application/vnd.oasis.opendocument.text", (b"PK\x03\x04",)),
}


def locked(db, key):
    obj = db.scalar(select(Competition).where(Competition.id == key).with_for_update())
    if not obj:
        raise HTTPException(404, "Соревнование не найдено")
    return obj


def regulation_info(db, comp_id):
    obj = db.get(CompetitionRegulation, comp_id)
    if not obj:
        return None
    return {k: getattr(obj, k) for k in ("filename", "size", "uploaded_at")}


def set_groups(db, comp, data):
    """Binds age groups; the overall age range follows the selected groups."""
    groups = [require(db, AgeGroup, i) for i in dict.fromkeys(data.age_group_ids)]
    if any(g.discipline_id not in (None, comp.discipline_id) for g in groups):
        raise HTTPException(422, "Возрастная группа относится к другой дисциплине")
    db.execute(
        delete(CompetitionAgeGroup).where(CompetitionAgeGroup.competition_id == comp.id)
    )
    db.add_all(
        [CompetitionAgeGroup(competition_id=comp.id, age_group_id=g.id) for g in groups]
    )
    if groups:
        comp.min_age = min(g.min_age for g in groups)
        comp.max_age = max(g.max_age for g in groups)


def competition_view(db, comp, actor):
    data = row(comp)
    groups = competition_groups(db, comp.id)
    data["age_groups"] = [group_view(g) for g in groups]
    data["regulation_file"] = regulation_info(db, comp.id)
    data["discipline"] = db.get(Discipline, comp.discipline_id).short_name
    data["type"] = db.get(CompetitionType, comp.type_id).name
    data["participants"] = len(
        db.scalars(
            select(CompetitionApplication.id).where(
                CompetitionApplication.competition_id == comp.id,
                CompetitionApplication.status == "approved",
            )
        ).all()
    )
    data["eligible"] = None
    data["age_check"] = None
    if actor.role == "athlete":
        data["age_check"] = age_check(db, comp, own(db, Athlete, actor), groups)
        data["eligible"] = data["age_check"]["eligible"]
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
    kind = require(db, CompetitionType, data.type_id)
    obj = Competition(
        **data.model_dump(exclude={"regulation_url", "age_group_ids"}),
        rating_level=rating_level(data.status, kind.rating_class),
        regulation_url=str(data.regulation_url) if data.regulation_url else None,
    )
    db.add(obj)
    db.flush()
    set_groups(db, obj, data)
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
    kind = require(db, CompetitionType, data.type_id)
    for k, v in data.model_dump(exclude={"regulation_url", "age_group_ids"}).items():
        setattr(obj, k, v)
    obj.rating_level = rating_level(data.status, kind.rating_class)
    obj.regulation_url = str(data.regulation_url) if data.regulation_url else None
    set_groups(db, obj, data)
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
    view = competition_view(db, comp, actor)
    group_names = {g["id"]: g["name"] for g in view["age_groups"]}
    return {
        **view,
        "applications": [
            {
                **row(a),
                "full_name": db.get(Athlete, a.athlete_id).user.full_name,
                "age_group": group_names.get(a.age_group_id),
            }
            for a in db.scalars(applications)
        ],
        "results": [
            {**row(r), "full_name": db.get(Athlete, r.athlete_id).user.full_name}
            for r in current_results(db, comp.id)
        ]
        if comp.state == "published" or actor.role == "admin"
        else [],
        "protocol_version": db.scalar(
            select(func.max(ProtocolVersion.version)).where(
                ProtocolVersion.competition_id == comp.id
            )
        ),
        "judges": [
            {**row(j), "full_name": db.get(Judge, j.judge_id).user.full_name}
            for j in judges
        ],
    }


@router.put("/competitions/{comp_id}/regulation")
async def upload_regulation(
    comp_id: int,
    file: UploadFile = File(...),
    actor: Actor = Depends(allow("admin")),
    db: Session = Depends(get_db),
):
    comp = locked(db, comp_id)
    if comp.state == "published":
        raise HTTPException(409, "Положение нельзя заменить после публикации итогов")
    name = PurePath((file.filename or "").replace("\\", "/")).name.strip()
    ext = PurePath(name).suffix.lower()
    if ext not in REGULATION_TYPES:
        raise HTTPException(422, "Допустимые форматы положения: PDF, DOCX, DOC, ODT")
    content = await file.read(REGULATION_MAX_SIZE + 1)
    if not content:
        raise HTTPException(422, "Файл пустой")
    if len(content) > REGULATION_MAX_SIZE:
        raise HTTPException(413, "Размер положения не должен превышать 10 МБ")
    mime, signatures = REGULATION_TYPES[ext]
    if not content.startswith(signatures):
        raise HTTPException(422, "Содержимое файла не соответствует расширению")
    obj = db.get(CompetitionRegulation, comp_id) or CompetitionRegulation(
        competition_id=comp_id
    )
    obj.filename = name[-255:]
    obj.content_type = mime
    obj.size = len(content)
    obj.data = content
    obj.uploaded_by = actor.user.id
    obj.uploaded_at = now()
    db.add(obj)
    comp.revision += 1
    audit(
        db,
        actor,
        "Загрузка положения",
        comp,
        {"filename": obj.filename, "size": obj.size},
    )
    if comp.state != "draft":
        athlete_ids = db.scalars(
            select(CompetitionApplication.athlete_id).where(
                CompetitionApplication.competition_id == comp.id,
                CompetitionApplication.status != "rejected",
            )
        ).all()
        notify(
            db,
            [u for a in athlete_ids for u in athlete_audience(db, a)],
            "Обновлено положение",
            comp.title,
            f"competition-regulation:{comp.id}:{comp.revision}",
        )
    return regulation_info(db, comp_id)


@router.delete("/competitions/{comp_id}/regulation", status_code=204)
def remove_regulation(
    comp_id: int, actor: Actor = Depends(allow("admin")), db: Session = Depends(get_db)
):
    comp = locked(db, comp_id)
    if comp.state == "published":
        raise HTTPException(409, "Положение нельзя удалить после публикации итогов")
    obj = require(db, CompetitionRegulation, comp_id)
    audit(db, actor, "Удаление положения", comp, {"filename": obj.filename})
    db.delete(obj)


@router.get("/competitions/{comp_id}/regulation")
def download_regulation(
    comp_id: int, actor: Actor = Depends(current_actor), db: Session = Depends(get_db)
):
    comp = require(db, Competition, comp_id)
    if comp.state == "draft" and actor.role != "admin":
        raise HTTPException(404, "Соревнование не найдено")
    obj = db.get(CompetitionRegulation, comp_id)
    if not obj:
        raise HTTPException(404, "Положение не прикреплено")
    fallback = f"regulation-{comp_id}{PurePath(obj.filename).suffix}"
    return Response(
        obj.data,
        media_type=obj.content_type,
        headers={
            "Content-Disposition": f'attachment; filename="{fallback}"; '
            f"filename*=UTF-8''{quote(obj.filename)}",
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.post("/competitions/{comp_id}/applications", status_code=201)
def apply(
    comp_id: int,
    data: ApplicationIn,
    actor: Actor = Depends(allow("athlete", "coach")),
    db: Session = Depends(get_db),
):
    comp = locked(db, comp_id)
    if comp.entry_mode == "team":
        raise HTTPException(409, "Подайте общую заявку через вкладку «Команды»")
    athlete = can_athlete(db, actor, data.athlete_id, comp.discipline_id)
    if comp.state != "open" or comp.deadline < date.today():
        raise HTTPException(409, "Приём заявок закрыт")
    if athlete.suspended_until and athlete.suspended_until >= date.today():
        raise HTTPException(422, "У спортсмена действует отстранение")
    check = age_check(db, comp, athlete)
    if not check["eligible"]:
        raise HTTPException(422, age_error(check))
    enrollment = db.get(AthleteDiscipline, (athlete.id, comp.discipline_id))
    if (
        not enrollment
        or enrollment.start_year > comp.start_date.year
        or enrollment.end_year is not None
        and enrollment.end_year < comp.start_date.year
    ):
        raise HTTPException(422, "Добавьте действующую дисциплину в профиль спортсмена")
    obj = CompetitionApplication(
        competition_id=comp.id,
        athlete_id=athlete.id,
        age_group_id=check["groups"][0]["id"] if check["groups"] else None,
        submitted_by=actor.user.id,
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


@router.get("/competitions/{comp_id}/eligibility")
def eligibility(
    comp_id: int,
    athlete_id: int,
    actor: Actor = Depends(allow("admin", "athlete", "coach")),
    db: Session = Depends(get_db),
):
    comp = require(db, Competition, comp_id)
    if comp.state == "draft" and actor.role != "admin":
        raise HTTPException(404, "Соревнование не найдено")
    return age_check(db, comp, can_athlete(db, actor, athlete_id))


@router.patch("/applications/{application_id}")
def moderate(
    application_id: int,
    data: Decision,
    actor: Actor = Depends(allow("admin")),
    db: Session = Depends(get_db),
):
    obj = require(db, CompetitionApplication, application_id)
    comp = locked(db, obj.competition_id)
    if comp.entry_mode == "team":
        raise HTTPException(
            409, "Рассматривайте командную заявку целиком во вкладке «Команды»"
        )
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
    if judge.archived_at:
        raise HTTPException(409, "Судья в архиве")
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
    entries = expand_results(db, comp, data)
    check_entries(entries, approved)
    db.add_all(
        [CompetitionResult(competition_id=comp.id, **r.model_dump()) for r in entries]
    )
    comp.state = "published"
    add_version(db, comp, actor.user.id)
    audit(
        db,
        actor,
        "Публикация результатов и протокола",
        comp,
        {"participants": len(entries)},
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
    return {"state": comp.state, "count": len(entries), "version": 1}


@router.put("/competitions/{comp_id}/results")
def correct(
    comp_id: int,
    data: ProtocolCorrectionIn,
    actor: Actor = Depends(allow("admin")),
    db: Session = Depends(get_db),
):
    comp = locked(db, comp_id)
    if comp.state != "published":
        raise HTTPException(409, "Исправить можно только опубликованный протокол")
    current = {r.athlete_id: r for r in current_results(db, comp.id)}
    entries = expand_results(db, comp, data)
    check_entries(entries, current)
    fields = ("place", "score", "team_name")
    changed = [
        r
        for r in entries
        if any(getattr(current[r.athlete_id], k) != getattr(r, k) for k in fields)
    ]
    if not changed:
        raise HTTPException(422, "Изменений в протоколе нет")
    # rows keep their ids: ranks and rank applications refer to them
    for r in changed:
        for k in fields:
            setattr(current[r.athlete_id], k, getattr(r, k))
    version = add_version(db, comp, actor.user.id, data.reason)
    warnings = rank_warnings(db, [current[r.athlete_id].id for r in changed])
    audit(
        db,
        actor,
        "Исправление протокола",
        comp,
        {
            "version": version.version,
            "reason": data.reason,
            "changed": len(changed),
            "rank_warnings": warnings,
        },
    )
    recalculate(db, comp.start_date.year)
    for athlete_id in current:
        notify(
            db,
            athlete_audience(db, athlete_id),
            "Протокол исправлен",
            f"{comp.title}: редакция {version.version}. {data.reason}",
            f"protocol:{comp.id}:{athlete_id}:v{version.version}",
        )
    return {
        "version": version.version,
        "changed": len(changed),
        "rank_warnings": warnings,
    }


@router.get("/competitions/{comp_id}/protocol-versions")
def protocol_versions(
    comp_id: int, actor: Actor = Depends(current_actor), db: Session = Depends(get_db)
):
    comp = require(db, Competition, comp_id)
    if comp.state != "published":
        return []
    return version_history(db, comp.id)


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
            "can_download_certificate": actor.role in {"admin", "athlete"}
            or (
                actor.role == "coach"
                and db.scalar(
                    select(AthleteCoach.id)
                    .join(Coach, Coach.id == AthleteCoach.coach_id)
                    .where(
                        Coach.user_id == actor.user.id,
                        AthleteCoach.athlete_id == r.athlete_id,
                        AthleteCoach.discipline_id == c.discipline_id,
                        AthleteCoach.status == "active",
                    )
                )
                is not None
            ),
            "full_name": db.get(Athlete, r.athlete_id).user.full_name,
            "title": c.title,
            "start_date": c.start_date,
            "discipline_id": c.discipline_id,
            "status": c.status,
            "rating_level": c.rating_level,
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
    scope: Literal["upcoming", "past"] | None = None,
    actor: Actor = Depends(allow("admin", "judge")),
    db: Session = Depends(get_db),
):
    """upcoming: the competition has not ended yet; past: it ended before today."""
    query = (
        select(CompetitionJudge, Competition, Discipline)
        .join(Competition, Competition.id == CompetitionJudge.competition_id)
        .join(Discipline, Discipline.id == Competition.discipline_id)
    )
    if actor.role == "judge":
        query = query.where(CompetitionJudge.judge_id == own(db, Judge, actor).id)
    if scope == "upcoming":
        query = query.where(Competition.end_date >= date.today()).order_by(
            Competition.start_date, Competition.id
        )
    elif scope == "past":
        query = query.where(Competition.end_date < date.today()).order_by(
            Competition.start_date.desc(), Competition.id.desc()
        )
    return [
        {
            **row(j),
            "title": c.title,
            "start_date": c.start_date,
            "end_date": c.end_date,
            "location": c.location,
            "discipline": d.short_name,
            "state": c.state,
        }
        for j, c, d in db.execute(query)
    ]


@router.post("/competition-types", status_code=201)
def add_type(
    data: CompetitionTypeIn,
    actor: Actor = Depends(allow("admin")),
    db: Session = Depends(get_db),
):
    obj = CompetitionType(**data.model_dump())
    db.add(obj)
    audit(db, actor, "Создание типа соревнования", obj)
    return row(obj)


@router.get("/age-groups")
def age_groups(actor: Actor = Depends(current_actor), db: Session = Depends(get_db)):
    return [
        row(g)
        for g in db.scalars(select(AgeGroup).order_by(AgeGroup.sort_order, AgeGroup.id))
    ]


def used_in_competitions(db, group_id, states):
    return db.scalar(
        select(Competition.id)
        .join(CompetitionAgeGroup, CompetitionAgeGroup.competition_id == Competition.id)
        .where(
            CompetitionAgeGroup.age_group_id == group_id, Competition.state.in_(states)
        )
    )


@router.post("/age-groups", status_code=201)
def add_age_group(
    data: AgeGroupIn,
    actor: Actor = Depends(allow("admin")),
    db: Session = Depends(get_db),
):
    if data.discipline_id:
        require(db, Discipline, data.discipline_id)
    obj = AgeGroup(**data.model_dump())
    db.add(obj)
    audit(db, actor, "Создание возрастной группы", obj, data.model_dump())
    return row(obj)


@router.put("/age-groups/{group_id}")
def edit_age_group(
    group_id: int,
    data: AgeGroupIn,
    actor: Actor = Depends(allow("admin")),
    db: Session = Depends(get_db),
):
    obj = require(db, AgeGroup, group_id)
    if data.discipline_id:
        require(db, Discipline, data.discipline_id)
    if used_in_competitions(db, group_id, ["open", "closed", "published"]):
        raise HTTPException(
            409, "Группа уже используется в объявленном соревновании, создайте новую"
        )
    for k, v in data.model_dump().items():
        setattr(obj, k, v)
    audit(db, actor, "Изменение возрастной группы", obj, data.model_dump())
    return row(obj)


@router.delete("/age-groups/{group_id}", status_code=204)
def delete_age_group(
    group_id: int, actor: Actor = Depends(allow("admin")), db: Session = Depends(get_db)
):
    obj = require(db, AgeGroup, group_id)
    if db.scalar(
        select(CompetitionAgeGroup.competition_id).where(
            CompetitionAgeGroup.age_group_id == group_id
        )
    ):
        raise HTTPException(409, "Группа используется в соревнованиях")
    audit(db, actor, "Удаление возрастной группы", obj, {"name": obj.name})
    db.delete(obj)
