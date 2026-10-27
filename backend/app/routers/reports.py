from datetime import date, timedelta
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from app.db import get_db
from app.models import *
from app.security import Actor, current_actor, allow
from app.services.common import *
from app.config import settings
from app.services.documents import OfficialDocument, export_document, MIME
from app.services.reports import population
from app.services.protocols import versions

router = APIRouter(tags=["Документы и аналитика"])
HEAD = (settings.fsp_head_position, settings.fsp_head_name)


def download(doc: OfficialDocument, fmt, filename):
    data = export_document(doc, fmt)
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
    judge_id = own(db, Judge, actor).id if actor.role == "judge" else None
    assignments = (
        db.scalar(
            select(func.count())
            .select_from(CompetitionJudge)
            .join(Competition, Competition.id == CompetitionJudge.competition_id)
            .where(
                CompetitionJudge.judge_id == judge_id,
                Competition.end_date >= date.today(),
            )
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
        "applications": len(db.scalars(query).all()),
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


ATTENTION_DAYS = 30  # same window as expiry notifications


@router.get("/dashboard/attention")
def attention(
    actor: Actor = Depends(allow("admin")), db: Session = Depends(get_db)
):
    """Federation to-do list: what waits for a decision or expires soon."""
    today = date.today()
    until = today + timedelta(days=ATTENTION_DAYS)
    items = []

    def add(kind, id, title, detail, due_on, date_label, link):
        items.append(
            {
                "kind": kind,
                "id": id,
                "title": title,
                "detail": detail,
                "due_on": due_on,
                "date_label": date_label,
                "link": link,
                "overdue": due_on < today,
            }
        )

    pending = db.execute(
        select(Competition, func.count(CompetitionApplication.id))
        .join(CompetitionApplication, CompetitionApplication.competition_id == Competition.id)
        .where(CompetitionApplication.status == "pending")
        .group_by(Competition.id)
    ).all()
    for c, count in pending:
        add(
            "applications",
            c.id,
            c.title,
            f"На рассмотрении: {count}",
            c.deadline,
            "приём до",
            f"/competitions/{c.id}",
        )
    for a in db.scalars(
        select(RankApplication).where(RankApplication.status == "pending")
    ):
        owner = db.get(Athlete, a.athlete_id) if a.athlete_id else db.get(Judge, a.judge_id)
        add(
            "rank_applications",
            a.id,
            owner.user.full_name,
            ("Разряд: " if a.athlete_id else "Категория: ") + a.name,
            a.created_at.date(),
            "подана",
            "/ranks",
        )
    for r in db.scalars(
        select(SportsRank).where(
            SportsRank.expires_on >= today, SportsRank.expires_on <= until
        )
    ):
        add(
            "ranks",
            r.id,
            db.get(Athlete, r.athlete_id).user.full_name,
            r.name,
            r.expires_on,
            "истекает",
            "/registry",
        )
    for c, judge in db.execute(
        select(JudgeCategory, Judge)
        .join(Judge, Judge.id == JudgeCategory.judge_id)
        .where(
            Judge.archived_at.is_(None),
            JudgeCategory.expires_on >= today,
            JudgeCategory.expires_on <= until,
        )
    ):
        add(
            "categories",
            c.id,
            judge.user.full_name,
            c.name,
            c.expires_on,
            "истекает",
            "/registry",
        )
    for d in db.scalars(select(Deadline).where(Deadline.done == False)):
        add("reports", d.id, d.title, "Срок отчётности", d.due_on, "срок", "/settings")
    governor = date(today.year if today.month == 1 else today.year + 1, 2, 1)
    if governor <= until:
        add(
            "reports",
            0,
            "Ходатайства на премии Губернатора",
            "Срок подачи",
            governor,
            "срок",
            "/ratings",
        )

    items.sort(key=lambda x: x["due_on"])
    kinds = ("applications", "rank_applications", "ranks", "categories", "reports")
    return {
        "window_days": ATTENTION_DAYS,
        "counts": {k: sum(i["kind"] == k for i in items) for k in kinds},
        "items": items,
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
    actor: Actor = Depends(allow("admin", "ministry")),
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
    actor: Actor = Depends(allow("admin", "ministry")),
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
    totals = "; ".join(f"{r['year']} — {r['count']}" for r in data["totals"])
    filters = [
        ("Организация", organization_id and require(db, Organization, organization_id).name),
        ("Дисциплина", discipline_id and require(db, Discipline, discipline_id).name),
        ("Муниципалитет", municipality),
        ("Возраст", f"{min_age}–{max_age} лет" if (min_age, max_age) != (0, 100) else ""),
    ]
    return download(
        OfficialDocument(
            kind="Отчёт",
            title="о численности лиц, занимающихся спортивным программированием",
            headers=data["headers"],
            rows=data["rows"],
            dated=date.today(),
            meta=[
                ("Период", f"{start_year}–{end_year} гг."),
                *[(label, value) for label, value in filters if value],
                ("Итого по годам", totals),
            ],
            outro=["Методика подсчёта: " + data["source"]],
            signatures=[HEAD, ("Исполнитель", actor.user.full_name)],
        ),
        fmt,
        "population",
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
    panel = [
        (db.get(Judge, j.judge_id).user.full_name, j.position)
        for j in db.scalars(
            select(CompetitionJudge).where(CompetitionJudge.competition_id == comp.id)
        )
    ]
    judges = "; ".join(f"{name} — {position}" for name, position in panel)
    by_position = lambda title: next(
        (name for name, position in panel if position == title), ""
    )
    edition = f"Редакция {picked.version} от {picked.created_at:%d.%m.%Y}"
    if picked.version > 1:
        edition += f", основание исправления: {picked.reason}"
    if picked is not history[-1]:
        edition += f". Заменена редакцией {history[-1].version}"
    return download(
        OfficialDocument(
            kind="Итоговый протокол",
            title=f"соревнования «{comp.title}»",
            headers=["Место"]
            + (["Команда"] if teams else [])
            + ["Спортсмен", "Организация", "Баллы"],
            rows=rows,
            dated=comp.end_date,
            meta=[
                ("Редакция", edition),
                ("Дисциплина", db.get(Discipline, comp.discipline_id).name),
                (
                    "Сроки проведения",
                    f"{comp.start_date:%d.%m.%Y} — {comp.end_date:%d.%m.%Y}",
                ),
                ("Место проведения", comp.location),
                ("Календарный план", f"{comp.calendar_plan} № {comp.calendar_number}"),
                ("Участников", len(rows)),
                ("Судейская коллегия", judges or "не назначена"),
            ],
            signatures=[
                ("Главный судья", by_position("Главный судья")),
                ("Главный секретарь", by_position("Главный секретарь")),
            ],
        ),
        fmt,
        f"protocol-{comp.id}-v{picked.version}",
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
            n,
            f"{c.start_date:%d.%m.%Y}",
            c.title,
            db.get(Discipline, c.discipline_id).short_name,
            r.place,
            r.score,
        ]
        for n, (r, c) in enumerate(db.execute(
            select(CompetitionResult, Competition)
            .join(Competition, Competition.id == CompetitionResult.competition_id)
            .where(
                CompetitionResult.athlete_id == a.id, Competition.state == "published"
            )
            .order_by(Competition.start_date.desc())
        ), 1)
    ]
    org = a.organization_id and db.get(Organization, a.organization_id)
    return download(
        OfficialDocument(
            kind="Справка",
            title="о результатах выступлений спортсмена",
            headers=["№ п/п", "Дата", "Соревнование", "Дисциплина", "Место", "Баллы"],
            rows=rows,
            dated=date.today(),
            meta=[
                ("Спортсмен", a.user.full_name),
                ("Дата рождения", f"{a.user.birth_date:%d.%m.%Y}"),
                ("Организация", org.name if org else "не указана"),
                ("Муниципалитет", a.municipality),
                ("Выступлений", len(rows)),
            ],
            outro=[
                "Сведения сформированы по опубликованным итоговым протоколам "
                "соревнований. Справка выдана для предъявления по месту требования."
            ],
            signatures=[HEAD],
        ),
        fmt,
        f"athlete-{a.id}",
    )


@router.get("/exports/team.{fmt}")
def team_export(
    fmt: str,
    season: int = date.today().year,
    discipline_id: int | None = None,
    order: bool = False,
    actor: Actor = Depends(allow("admin", "ministry")),
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
                len(rows) + 1,
                a.user.full_name,
                f"{a.user.birth_date:%d.%m.%Y}",
                db.get(Discipline, t.discipline_id).short_name,
                a.municipality,
            ]
        )
    team = (
        "спортивной сборной команды Оренбургской области "
        f"по спортивному программированию на {season} год"
    )
    headers = ["№ п/п", "Фамилия, имя, отчество", "Дата рождения", "Дисциплина",
               "Муниципалитет"]
    if order:
        doc = OfficialDocument(
            kind="Приказ",
            title="Об утверждении состава " + team,
            headers=headers,
            rows=rows,
            number="",
            draft=True,
            intro=[
                "В соответствии с Федеральным законом от 04.12.2007 № 329-ФЗ "
                "«О физической культуре и спорте в Российской Федерации», на основании "
                f"итогов сезонного рейтинга спортсменов за {season} год",
                "ПРИКАЗЫВАЮ:",
                f"1. Утвердить состав {team} согласно приложению к настоящему приказу.",
                "2. Тренерам обеспечить подготовку спортсменов к участию "
                "в соревнованиях в составе сборной команды.",
                "3. Контроль за исполнением настоящего приказа оставляю за собой.",
            ],
            signatures=[HEAD],
            appendix=[
                "Приложение",
                f"к приказу {settings.fsp_short_name}",
                "от «___» ____________ 20___ г. № ________",
            ],
            table_title="Состав " + team,
        )
    else:
        doc = OfficialDocument(
            kind="Список",
            title="кандидатов в состав " + team,
            headers=headers,
            rows=rows,
            dated=date.today(),
            outro=["Состав сформирован федерацией на основе сезонного рейтинга."],
            signatures=[HEAD],
        )
    return download(doc, fmt, "team-order" if order else "team")


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


def judging_history(db, judge_id, year=None):
    """Competitions the judge worked at, i.e. assignments that already ended."""
    entries = db.execute(
        select(CompetitionJudge, Competition, Discipline)
        .join(Competition, Competition.id == CompetitionJudge.competition_id)
        .join(Discipline, Discipline.id == Competition.discipline_id)
        .where(
            CompetitionJudge.judge_id == judge_id, Competition.end_date < date.today()
        )
        .order_by(Competition.start_date.desc(), Competition.id.desc())
    ).all()
    participants = dict(
        db.execute(
            select(CompetitionResult.competition_id, func.count())
            .where(
                CompetitionResult.competition_id.in_(
                    [c.id for _, c, _ in entries]
                )
            )
            .group_by(CompetitionResult.competition_id)
        ).all()
    )
    years = sorted({c.start_date.year for _, c, _ in entries}, reverse=True)
    items = [
        {
            "competition_id": c.id,
            "title": c.title,
            "start_date": c.start_date,
            "end_date": c.end_date,
            "location": c.location,
            "discipline": d.short_name,
            "status": c.status,
            "state": c.state,
            "position": j.position,
            "participants": participants.get(c.id, 0),
        }
        for j, c, d in entries
        if year is None or c.start_date.year == year
    ]
    return years, items


@router.get("/judging/report")
def judging_report(
    year: int | None = Query(None, ge=1970, le=2100),
    actor: Actor = Depends(allow("judge")),
    db: Session = Depends(get_db),
):
    judge = own(db, Judge, actor)
    years, items = judging_history(db, judge.id, year)
    return {
        "judge": {"id": judge.id, "full_name": actor.user.full_name},
        "years": years,
        "stats": {
            "competitions": len(items),
            "chief": sum(i["position"] == "Главный судья" for i in items),
            "participants": sum(i["participants"] for i in items),
            "disciplines": len({i["discipline"] for i in items}),
        },
        "items": items,
    }


@router.get("/exports/judging.{fmt}")
def judging_export(
    fmt: Literal["pdf", "docx", "xlsx"],
    year: int | None = Query(None, ge=1970, le=2100),
    actor: Actor = Depends(allow("judge")),
    db: Session = Depends(get_db),
):
    judge = own(db, Judge, actor)
    _, items = judging_history(db, judge.id, year)
    period = f"{year} год" if year else "за всё время"
    return download(
        OfficialDocument(
            kind="Отчёт",
            title="о судейской деятельности",
            headers=["№ п/п", "Сроки", "Соревнование", "Дисциплина",
                     "Место проведения", "Должность", "Участников"],
            rows=[
                [
                    n,
                    f"{i['start_date']:%d.%m.%Y} — {i['end_date']:%d.%m.%Y}",
                    i["title"],
                    i["discipline"],
                    i["location"],
                    i["position"],
                    i["participants"],
                ]
                for n, i in enumerate(items, 1)
            ],
            dated=date.today(),
            meta=[
                ("Спортивный судья", actor.user.full_name),
                ("Период", period),
                ("Соревнований", len(items)),
                (
                    "Из них главным судьёй",
                    sum(i["position"] == "Главный судья" for i in items),
                ),
            ],
            signatures=[("Спортивный судья", actor.user.full_name)],
        ),
        fmt,
        f"judging-{judge.id}" + (f"-{year}" if year else ""),
    )
