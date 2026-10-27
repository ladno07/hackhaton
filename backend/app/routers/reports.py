from datetime import date
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from app.db import get_db
from app.models import *
from app.security import Actor, current_actor, allow
from app.services.common import *
from app.services.reports import population, export_document, MIME
from app.services.protocols import versions

router = APIRouter(tags=["Документы и аналитика"])


def download(title, headers, rows, fmt, filename, subtitle=""):
    data = export_document(title, headers, rows, fmt, subtitle)
    return Response(
        data,
        media_type=MIME[fmt],
        headers={
            "Content-Disposition": f'attachment; filename="{filename}.{fmt}"',
            "Cache-Control": "no-store",
        },
    )


@router.get("/dashboard")
def dashboard(actor: Actor = Depends(current_actor), db: Session = Depends(get_db)):
    ids = visible_athletes(db, actor)
    query = select(CompetitionApplication).where(
        CompetitionApplication.status == "pending"
    )
    rank_query = select(RankApplication).where(RankApplication.status == "pending")
    if actor.role != "admin":
        query = query.where(CompetitionApplication.athlete_id.in_(ids))
        if actor.role == "judge":
            rank_query = rank_query.where(
                RankApplication.judge_id == own(db, Judge, actor).id
            )
        else:
            rank_query = rank_query.where(RankApplication.athlete_id.in_(ids))
    team_query = select(CompetitionTeam.id).where(CompetitionTeam.status == "pending")
    if actor.role != "admin":
        team_query = team_query.where(
            CompetitionTeam.id.in_(
                select(CompetitionTeamMember.team_id).where(
                    CompetitionTeamMember.athlete_id.in_(ids)
                )
            )
        )
    pending_teams = len(db.scalars(team_query).all())
    judge_id = own(db, Judge, actor).id if actor.role == "judge" else None
    assignments = (
        db.scalar(
            select(func.count())
            .select_from(CompetitionJudge)
            .where(CompetitionJudge.judge_id == judge_id)
        )
        if judge_id
        else 0
    )
    categories = (
        db.scalar(
            select(func.count())
            .select_from(JudgeCategory)
            .where(
                JudgeCategory.judge_id == judge_id,
                JudgeCategory.expires_on >= date.today(),
            )
        )
        if judge_id
        else 0
    )
    return {
        "assignments": assignments,
        "categories": categories,
        "athletes": len(ids),
        "competitions": db.scalar(
            select(func.count())
            .select_from(Competition)
            .where(Competition.state != "draft")
        ),
        "applications": len(db.scalars(query).all()) + pending_teams,
        "rank_applications": len(db.scalars(rank_query).all()),
        "results": db.scalar(
            select(func.count())
            .select_from(CompetitionResult)
            .where(CompetitionResult.athlete_id.in_(ids))
        ),
        "ranks": db.scalar(
            select(func.count())
            .select_from(SportsRank)
            .where(
                SportsRank.athlete_id.in_(ids), SportsRank.expires_on >= date.today()
            )
        ),
        "organizations": db.scalar(select(func.count()).select_from(Organization)),
    }


@router.get("/reports/population")
def population_report(
    start_year: int = Query(date.today().year - 1, ge=1970, le=2100),
    end_year: int = Query(date.today().year, ge=1970, le=2100),
    organization_id: int | None = None,
    discipline_id: int | None = None,
    municipality: str = "",
    min_age: int = 0,
    max_age: int = 100,
    actor: Actor = Depends(allow("admin")),
    db: Session = Depends(get_db),
):
    if not 1 <= end_year - start_year <= 30:
        raise HTTPException(422, "Укажите период от 2 до 31 года")
    return population(
        db,
        start_year,
        end_year,
        organization_id,
        discipline_id,
        municipality,
        min_age,
        max_age,
    )


@router.get("/exports/population.{fmt}")
def export_population(
    fmt: str,
    start_year: int = Query(date.today().year - 1, ge=1970, le=2100),
    end_year: int = Query(date.today().year, ge=1970, le=2100),
    organization_id: int | None = None,
    discipline_id: int | None = None,
    municipality: str = "",
    min_age: int = 0,
    max_age: int = 100,
    actor: Actor = Depends(allow("admin")),
    db: Session = Depends(get_db),
):
    if not 1 <= end_year - start_year <= 30:
        raise HTTPException(422, "Укажите период от 2 до 31 года")
    data = population(
        db,
        start_year,
        end_year,
        organization_id,
        discipline_id,
        municipality,
        min_age,
        max_age,
    )
    totals = "; ".join(f"{r['year']}: {r['count']}" for r in data["totals"])
    return download(
        "Численность занимающихся спортивным программированием",
        data["headers"],
        data["rows"],
        fmt,
        "population",
        totals + ". " + data["source"],
    )


@router.get("/exports/protocol/{comp_id}.{fmt}")
def protocol(
    comp_id: int,
    fmt: str,
    version: int | None = None,
    actor: Actor = Depends(current_actor),
    db: Session = Depends(get_db),
):
    comp = require(db, Competition, comp_id)
    if comp.state != "published":
        raise HTTPException(409, "Протокол ещё не опубликован")
    history = versions(db, comp.id)
    picked = (
        next((v for v in history if v.version == version), None)
        if version
        else history[-1]
    )
    if not picked:
        raise HTTPException(404, "Редакция протокола не найдена")
    teams = any(e["team_name"] for e in picked.entries)
    rows = [
        [e["place"]]
        + ([e["team_name"] or "—"] if teams else [])
        + [e["full_name"], e["organization"], e["score"]]
        for e in picked.entries
    ]
    judges = "; ".join(
        f"{db.get(Judge, j.judge_id).user.full_name} — {j.position}"
        for j in db.scalars(
            select(CompetitionJudge).where(CompetitionJudge.competition_id == comp.id)
        )
    )
    edition = f"Редакция {picked.version} от {picked.created_at:%d.%m.%Y}"
    if picked.version > 1:
        edition += f", основание исправления: {picked.reason}"
    if picked is not history[-1]:
        edition += f". Заменена редакцией {history[-1].version}"
    return download(
        "Итоговый протокол: " + comp.title,
        ["Место"]
        + (["Команда"] if teams else [])
        + ["Спортсмен", "Организация", "Баллы"],
        rows,
        fmt,
        f"protocol-{comp.id}-v{picked.version}",
        f"{edition}. {comp.start_date} — {comp.end_date}. {comp.location}. {comp.calendar_plan} № {comp.calendar_number}. Судейская коллегия: {judges or 'не назначена'}",
    )


@router.get("/exports/athlete/{athlete_id}.{fmt}")
def athlete_report(
    athlete_id: int,
    fmt: str,
    actor: Actor = Depends(current_actor),
    db: Session = Depends(get_db),
):
    a = can_athlete(db, actor, athlete_id)
    rows = [
        [
            c.start_date,
            c.title,
            db.get(Discipline, c.discipline_id).short_name,
            r.place,
            r.score,
        ]
        for r, c in db.execute(
            select(CompetitionResult, Competition)
            .join(Competition, Competition.id == CompetitionResult.competition_id)
            .where(
                CompetitionResult.athlete_id == a.id, Competition.state == "published"
            )
            .order_by(Competition.start_date.desc())
        )
    ]
    return download(
        "История выступлений: " + a.user.full_name,
        ["Дата", "Соревнование", "Дисциплина", "Место", "Баллы"],
        rows,
        fmt,
        f"athlete-{a.id}",
    )


@router.get("/exports/team.{fmt}")
def team_export(
    fmt: str,
    season: int = date.today().year,
    discipline_id: int | None = None,
    order: bool = False,
    actor: Actor = Depends(allow("admin")),
    db: Session = Depends(get_db),
):
    query = select(TeamMember).where(TeamMember.season == season)
    if discipline_id:
        query = query.where(TeamMember.discipline_id == discipline_id)
    rows = []
    for t in db.scalars(query):
        a = db.get(Athlete, t.athlete_id)
        if a.suspended_until and a.suspended_until >= date.today():
            raise HTTPException(
                409,
                "В сборной есть отстранённый спортсмен. Обновите состав перед выгрузкой",
            )
        rows.append(
            [
                a.user.full_name,
                db.get(Discipline, t.discipline_id).short_name,
                a.municipality,
            ]
        )
    title = (
        f"ПРОЕКТ ПРИКАЗА. Утверждение сборной Оренбургской области на {season} год"
        if order
        else f"Сборная Оренбургской области · {season}"
    )
    subtitle = (
        "Утвердить следующий состав сборной. Номер, дата и подпись уполномоченного лица заполняются после согласования."
        if order
        else "Состав сформирован федерацией вручную на основе сезонного рейтинга."
    )
    return download(
        title,
        ["Спортсмен", "Дисциплина", "Муниципалитет"],
        rows,
        fmt,
        "team-order" if order else "team",
        subtitle,
    )


@router.get("/coaching/athletes/{athlete_id}/summary")
def coaching_summary(
    athlete_id: int,
    year: int | None = Query(None, ge=1970, le=2100),
    discipline_id: int | None = Query(None, ge=1),
    actor: Actor = Depends(allow("coach", "admin")),
    db: Session = Depends(get_db),
):
    athlete = can_athlete(db, actor, athlete_id)
    entries = db.execute(
        select(CompetitionResult, Competition, Discipline)
        .join(Competition, Competition.id == CompetitionResult.competition_id)
        .join(Discipline, Discipline.id == Competition.discipline_id)
        .where(
            CompetitionResult.athlete_id == athlete.id, Competition.state == "published"
        )
        .order_by(Competition.start_date.desc(), Competition.id.desc())
    ).all()
    results = [
        {
            "id": result.id,
            "competition_id": comp.id,
            "title": comp.title,
            "start_date": comp.start_date,
            "discipline_id": discipline.id,
            "discipline": discipline.short_name,
            "place": result.place,
            "score": result.score,
            "team_name": result.team_name,
        }
        for result, comp, discipline in entries
        if (year is None or comp.start_date.year == year)
        and (discipline_id is None or comp.discipline_id == discipline_id)
    ]
    return {
        "athlete": {"id": athlete.id, "full_name": athlete.user.full_name},
        "years": sorted({comp.start_date.year for _, comp, _ in entries}, reverse=True),
        "disciplines": [
            {"id": key, "name": name}
            for key, name in sorted({(d.id, d.short_name) for _, _, d in entries})
        ],
        "stats": {
            "performances": len(results),
            "wins": sum(r["place"] == 1 for r in results),
            "podiums": sum(r["place"] <= 3 for r in results),
            "best_place": min((r["place"] for r in results), default=None),
        },
        "results": results,
    }
