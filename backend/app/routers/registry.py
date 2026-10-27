from datetime import date
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, delete
from sqlalchemy.orm import Session
from app.db import get_db
from app.models import *
from app.schemas import (
    ProfileIn,
    LinkIn,
    LinkState,
    OrganizationIn,
    RolesIn,
    SuspensionIn,
)
from app.security import Actor, current_actor, allow
from app.services.common import *
from app.services.notifications import notify
from app.services.ratings import rating_levels

router = APIRouter(tags=["Реестры и профили"])


def athlete_view(db, athlete):
    ranks = db.scalars(
        select(SportsRank)
        .where(SportsRank.athlete_id == athlete.id)
        .order_by(SportsRank.assigned_on.desc())
    ).all()
    org = (
        db.get(Organization, athlete.organization_id)
        if athlete.organization_id
        else None
    )
    return {
        **row(athlete),
        "full_name": athlete.user.full_name,
        "sex": athlete.user.sex,
        "age": age_at(athlete.user.birth_date),
        "organization": org.name if org else "Без организации",
        "disciplines": [
            row(d)
            for d in db.scalars(
                select(AthleteDiscipline).where(
                    AthleteDiscipline.athlete_id == athlete.id
                )
            )
        ],
        "ranks": [row(r) for r in ranks],
    }


@router.get("/metadata")
def metadata(actor: Actor = Depends(current_actor), db: Session = Depends(get_db)):
    return {
        "disciplines": [
            row(x) for x in db.scalars(select(Discipline).order_by(Discipline.id))
        ],
        "types": [row(x) for x in db.scalars(select(CompetitionType))],
        "rating_levels": rating_levels(db),
        "organizations": [row(x) for x in db.scalars(select(Organization))],
        "age_groups": [
            row(x)
            for x in db.scalars(
                select(AgeGroup).order_by(AgeGroup.sort_order, AgeGroup.id)
            )
        ],
    }


@router.get("/athletes")
def athletes(
    q: str = "",
    discipline_id: int | None = None,
    organization_id: int | None = None,
    municipality: str = "",
    min_age: int = 0,
    max_age: int = 100,
    rank: str = "",
    mine: bool = False,
    actor: Actor = Depends(allow("admin", "coach", "athlete")),
    db: Session = Depends(get_db),
):
    ids = visible_athletes(db, actor) if mine or actor.role == "athlete" else None
    output = []
    for athlete in db.scalars(select(Athlete).order_by(Athlete.id)):
        if ids is not None and athlete.id not in ids:
            continue
        item = athlete_view(db, athlete)
        if (
            q.lower() not in item["full_name"].lower()
            or not min_age <= item["age"] <= max_age
        ):
            continue
        if discipline_id and not any(
            d["discipline_id"] == discipline_id for d in item["disciplines"]
        ):
            continue
        if (
            organization_id
            and athlete.organization_id != organization_id
            or municipality.lower() not in athlete.municipality.lower()
        ):
            continue
        if rank and not any(
            r["name"] == rank and r["expires_on"] >= date.today() for r in item["ranks"]
        ):
            continue
        # An unlinked coach can discover names, municipality and disciplines only.
        if actor.role == "coach" and athlete.id not in visible_athletes(db, actor):
            item = {
                k: item[k]
                for k in [
                    "id",
                    "full_name",
                    "municipality",
                    "organization",
                    "organization_id",
                    "disciplines",
                    "age",
                ]
            }
        output.append(item)
    return output


@router.get("/athletes/{athlete_id}")
def athlete_detail(
    athlete_id: int,
    actor: Actor = Depends(current_actor),
    db: Session = Depends(get_db),
):
    return athlete_view(db, can_athlete(db, actor, athlete_id))


@router.put("/athletes/{athlete_id}")
def update_profile(
    athlete_id: int,
    data: ProfileIn,
    actor: Actor = Depends(allow("admin", "athlete")),
    db: Session = Depends(get_db),
):
    athlete = can_athlete(db, actor, athlete_id)
    if data.organization_id:
        require(db, Organization, data.organization_id)
    discipline_ids = [d.discipline_id for d in data.disciplines]
    if len(set(discipline_ids)) != len(discipline_ids):
        raise HTTPException(422, "Дисциплина указана дважды")
    for d in data.disciplines:
        require(db, Discipline, d.discipline_id)
    athlete.user.full_name = data.full_name
    if "sex" in data.model_fields_set:
        athlete.user.sex = data.sex
    for key, value in data.model_dump(
        mode="json", exclude={"full_name", "sex", "disciplines", "rusada_date"}
    ).items():
        setattr(athlete, key, value)
    athlete.rusada_date = data.rusada_date
    db.execute(
        delete(AthleteDiscipline).where(AthleteDiscipline.athlete_id == athlete.id)
    )
    db.add_all(
        [
            AthleteDiscipline(athlete_id=athlete.id, **d.model_dump())
            for d in data.disciplines
        ]
    )
    audit(db, actor, "Изменение профиля", athlete)
    return athlete_view(db, athlete)


@router.put("/athletes/{athlete_id}/suspension")
def suspension(
    athlete_id: int,
    data: SuspensionIn,
    actor: Actor = Depends(allow("admin")),
    db: Session = Depends(get_db),
):
    athlete = require(db, Athlete, athlete_id)
    athlete.suspended_until = data.suspended_until
    athlete.suspension_reason = data.reason
    audit(db, actor, "Изменение отстранения", athlete, data.model_dump(mode="json"))
    return row(athlete)


@router.get("/coaches")
def coaches(actor: Actor = Depends(current_actor), db: Session = Depends(get_db)):
    return [
        {
            "id": c.id,
            "full_name": c.user.full_name,
            "organization_id": c.organization_id,
        }
        for c in db.scalars(select(Coach))
    ]


@router.get("/judges")
def judges(actor: Actor = Depends(current_actor), db: Session = Depends(get_db)):
    return [
        {
            "id": j.id,
            "full_name": j.user.full_name,
            "categories": [
                row(c)
                for c in db.scalars(
                    select(JudgeCategory).where(JudgeCategory.judge_id == j.id)
                )
            ],
        }
        for j in db.scalars(select(Judge))
    ]


@router.post("/organizations", status_code=201)
def add_organization(
    data: OrganizationIn,
    actor: Actor = Depends(allow("admin")),
    db: Session = Depends(get_db),
):
    obj = Organization(**data.model_dump())
    db.add(obj)
    audit(db, actor, "Создание организации", obj)
    return row(obj)


@router.put("/organizations/{org_id}")
def edit_organization(
    org_id: int,
    data: OrganizationIn,
    actor: Actor = Depends(allow("admin")),
    db: Session = Depends(get_db),
):
    obj = require(db, Organization, org_id)
    for k, v in data.model_dump().items():
        setattr(obj, k, v)
    audit(db, actor, "Изменение организации", obj)
    return row(obj)


@router.get("/links")
def links(
    actor: Actor = Depends(allow("admin", "coach", "athlete")),
    db: Session = Depends(get_db),
):
    query = select(AthleteCoach)
    if actor.role == "coach":
        query = query.where(AthleteCoach.coach_id == own(db, Coach, actor).id)
    if actor.role == "athlete":
        query = query.where(AthleteCoach.athlete_id == own(db, Athlete, actor).id)
    return [
        {
            **row(x),
            "athlete": db.get(Athlete, x.athlete_id).user.full_name,
            "coach": db.get(Coach, x.coach_id).user.full_name,
            "history": [
                row(h)
                for h in db.scalars(
                    select(LinkHistory)
                    .where(LinkHistory.link_id == x.id)
                    .order_by(LinkHistory.id)
                )
            ],
        }
        for x in db.scalars(query)
    ]


@router.post("/links", status_code=201)
def request_link(
    data: LinkIn, actor: Actor = Depends(allow("coach")), db: Session = Depends(get_db)
):
    athlete = require(db, Athlete, data.athlete_id)
    require(db, Discipline, data.discipline_id)
    if not db.get(AthleteDiscipline, (athlete.id, data.discipline_id)):
        raise HTTPException(422, "Спортсмен не занимается выбранной дисциплиной")
    coach = own(db, Coach, actor)
    link = AthleteCoach(
        athlete_id=athlete.id, coach_id=coach.id, discipline_id=data.discipline_id
    )
    db.add(link)
    audit(db, actor, "Запрос связи с тренером", link)
    db.add(LinkHistory(link_id=link.id, actor_id=actor.user.id, status="pending"))
    notify(
        db,
        [athlete.user_id],
        "Запрос от тренера",
        coach.user.full_name,
        f"link:{link.id}",
    )
    return row(link)


@router.patch("/links/{link_id}")
def change_link(
    link_id: int,
    data: LinkState,
    actor: Actor = Depends(allow("admin", "athlete", "coach")),
    db: Session = Depends(get_db),
):
    link = require(db, AthleteCoach, link_id)
    athlete = require(db, Athlete, link.athlete_id)
    coach = require(db, Coach, link.coach_id)
    if actor.role != "admin" and not (
        actor.role == "athlete"
        and athlete.user_id == actor.user.id
        or actor.role == "coach"
        and coach.user_id == actor.user.id
    ):
        raise HTTPException(403, "Нет доступа к связи")
    if data.status == "active" and actor.role != "athlete":
        raise HTTPException(403, "Связь подтверждает только спортсмен")
    if link.status == "ended" or (link.status == "pending" and data.status == "paused"):
        raise HTTPException(409, "Недопустимый переход статуса")
    link.status = data.status
    db.add(LinkHistory(link_id=link.id, actor_id=actor.user.id, status=data.status))
    audit(db, actor, "Изменение связи с тренером", link, {"status": data.status})
    notify(
        db,
        [athlete.user_id, coach.user_id],
        "Связь с тренером изменена",
        data.status,
        f"link-change:{link.id}:{now().isoformat()}",
    )
    return row(link)


@router.get("/users")
def users(actor: Actor = Depends(allow("admin")), db: Session = Depends(get_db)):
    return [
        {
            "id": u.id,
            "full_name": u.full_name,
            "email": u.email,
            "roles": [r.id for r in u.roles],
        }
        for u in db.scalars(select(User))
    ]


@router.put("/users/{user_id}/roles")
def roles(
    user_id: int,
    data: RolesIn,
    actor: Actor = Depends(allow("admin")),
    db: Session = Depends(get_db),
):
    user = require(db, User, user_id)
    if user_id == actor.user.id and "admin" not in data.roles:
        raise HTTPException(409, "Нельзя снять с себя роль администратора")
    user.roles = [require(db, Role, name) for name in set(data.roles)]
    for name, model in [("athlete", Athlete), ("coach", Coach), ("judge", Judge)]:
        if name in data.roles and not db.scalar(
            select(model).where(model.user_id == user_id)
        ):
            db.add(model(user_id=user_id))
    audit(db, actor, "Изменение ролей", user, {"roles": data.roles})
    return {"roles": data.roles}
