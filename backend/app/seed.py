"""Initialize reference data. --demo opts into entirely fictional personal data."""

import argparse
import os
from datetime import date, timedelta
from sqlalchemy import select
from app.db import SessionLocal
from app.models import *
from app.security import password_hash, Actor
from app.services.common import audit, age_at
from app.services.ratings import recalculate
from app.services.notifications import admins, athlete_audience, notify
from app.config import settings
from app.services.documents import OfficialDocument, export_document
from app.services.protocols import add_version
from app.services.awards import DEFAULT_AMOUNTS, achievements
from app.services.standards import STAGES, basis_of, meets, readiness

DISCIPLINES = [
    ("Программирование алгоритмическое", "Алгоритмы"),
    ("Программирование продуктовое", "Продуктовая разработка"),
    (
        "Программирование систем информационной безопасности",
        "Информационная безопасность",
    ),
    ("Программирование систем искусственного интеллекта", "Искусственный интеллект"),
    ("Программирование робототехники", "Робототехника"),
    ("Программирование беспилотных авиационных систем", "Беспилотные системы"),
]

# Default groups for all disciplines; the federation adjusts them to the current
# sport rules in "Управление → Возрастные группы". Age is counted by birth year.
AGE_GROUPS = [
    ("Юноши", "male", 14, 17),
    ("Девушки", "female", 14, 17),
    ("Юниоры", "male", 18, 21),
    ("Юниорки", "female", 18, 21),
    ("Мужчины", "male", 18, 100),
    ("Женщины", "female", 18, 100),
]
# Rating class of the type decides the rating level of national competitions.
COMPETITION_TYPES = [
    ("Чемпионат", "main"),
    ("Первенство", "junior"),
    ("Кубок", "main"),
    ("Турнир", "other"),
]
FEMALE_NAMES = {
    "Арина", "Анна", "Алиса", "Вера", "Дарья", "Ева", "Мирослава", "Полина", "София"
}


ROLES = [
    ("admin", "Федерация"),
    ("athlete", "Спортсмен"),
    ("coach", "Тренер"),
    ("judge", "Судья"),
    ("ministry", "Минспорт"),
]
MINISTRY_DEMO = "minsport@demo.example"


def ministry_demo(db):
    """Read-only ministry account; the demo admin can also switch to this cabinet."""
    ministry = db.get(Role, "ministry")
    admin = db.scalar(select(User).where(User.email == "admin@demo.example"))
    if admin and ministry not in admin.roles:
        admin.roles = [*admin.roles, ministry]
    if db.scalar(select(User.id).where(User.email == MINISTRY_DEMO)):
        return
    user = User(
        email=MINISTRY_DEMO,
        full_name="Демо · Ольга Степнова",
        birth_date=date(1984, 3, 9),
        sex="female",
        password_hash=password_hash.hash(os.getenv("DEMO_PASSWORD", "DemoPass2026!")),
    )
    user.roles = [ministry]
    db.add(user)
    db.flush()


def indicators_demo(db, admin, year):
    """Entered indicators with sources; one has a sample statistical form."""
    form = DevelopmentIndicator(
        year=year,
        name="Численность занимающихся по форме № 1-ФК",
        value=148,
        unit="чел.",
        source=f"Форма федерального статистического наблюдения № 1-ФК за {year} г., раздел «Спортивное программирование»",
        comment="Демонстрационное значение, не является официальной статистикой",
        updated_by=admin.id,
    )
    pdf = export_document(
        OfficialDocument(
            kind="Сведения",
            title=f"о численности занимающихся за {year} год",
            headers=["Показатель", "Значение"],
            rows=[
                ["Численность занимающихся", "148 чел."],
                ["Из них в возрасте до 18 лет", "97 чел."],
                ["Документ", "Демонстрационный образец, не имеет силы"],
            ],
            dated=date(year + 1, 1, 15),
            signatures=[(settings.fsp_head_position, settings.fsp_head_name)],
        ),
        "pdf",
    )
    form.documents.append(
        IndicatorDocument(
            filename=f"Форма 1-ФК за {year} год.pdf",
            content_type="application/pdf",
            size=len(pdf),
            data=pdf,
            uploaded_by=admin.id,
        )
    )
    db.add_all(
        [
            form,
            DevelopmentIndicator(
                year=year,
                name="Спортивных площадок для занятий",
                value=6,
                unit="ед.",
                source="Отчёты организаций, представленные в федерацию по итогам года",
                comment="Демонстрационное значение",
                updated_by=admin.id,
            ),
        ]
    )


def awards_demo(db, admin, year):
    """The winner of the demo interregional cup is already in the petition."""
    found = achievements(db, year)
    athlete_id, items = min(found.items(), key=lambda x: x[1][0]["place"])
    db.add(
        GovernorAward(
            year=year,
            athlete_id=athlete_id,
            status="nominated",
            amount=items[0]["amount"],
            basis=items[0],
            comment="Демо: решение совета федерации",
            updated_by=admin.id,
        )
    )


def appeals_demo(db, admin, coach_user, athletes, cup):
    """A warning the demo athlete may still appeal, a pending coach appeal on
    the cup protocol and a rejected one; no suspensions, ratings stay intact."""
    today = date.today()
    db.add_all(
        [
            Violation(
                athlete_id=athletes[0].id,
                kind="conduct",
                occurred_on=today - timedelta(days=1),
                description="Демо · Использование телефона в зоне соревнований",
                sanction="warning",
                created_by=admin.id,
            ),
            Violation(
                athlete_id=athletes[4].id,
                competition_id=cup.id,
                kind="rules",
                occurred_on=cup.start_date,
                description="Демо · Опоздание к началу тура без уважительной причины",
                sanction="warning",
                created_by=admin.id,
                created_at=now() - timedelta(days=29),
            ),
        ]
    )
    results = {
        r.athlete_id: r
        for r in db.scalars(
            select(CompetitionResult).where(CompetitionResult.competition_id == cup.id)
        )
    }
    for athlete, by, role, status in [
        (athletes[1], coach_user, "coach", "pending"),
        (athletes[3], athletes[3].user, "athlete", "rejected"),
    ]:
        db.add(
            Appeal(
                athlete_id=athlete.id,
                subject="result",
                competition_id=cup.id,
                result_id=results[athlete.id].id,
                protocol_version=1,
                reason="Демо · Решение задачи F не засчитано, хотя прошло все тесты "
                "в системе проверки (посылка 14:32)",
                request="Пересчитать баллы и место",
                submitted_by=by.id,
                submitted_role=role,
                status=status,
                decision="Демо · Посылка проверена повторно, решение превысило лимит времени"
                if status == "rejected"
                else "",
                decided_by=admin.id if status == "rejected" else None,
                decided_at=now() - timedelta(days=27) if status == "rejected" else None,
                # the pending one is fresh so the federation's term has not run out
                created_at=now() - timedelta(days=29 if status == "rejected" else 1),
            )
        )


RUN, PUSH, BEND = (
    "Бег 30 м",
    "Сгибание и разгибание рук в упоре лёжа",
    "Наклон вперёд из положения стоя",
)
TYPING, CONTEST = (
    "Набор эталонного текста на клавиатуре",
    "Решение задач тренировочного контеста за 5 часов",
)
# Illustrative thresholds for transfer to the stage (НП, УТ, ССМ, ВСМ); the
# federation checks them against the FSSP order for the sport. The contest
# standard is for discipline 1 (algorithmic programming) only.
STANDARDS = [
    ("ofp", RUN, "с", "lower", "male", None, (6.9, 6.2, 5.7, 5.4)),
    ("ofp", RUN, "с", "lower", "female", None, (7.2, 6.6, 6.2, 5.9)),
    ("ofp", PUSH, "раз", "higher", "male", None, (7, 13, 20, 25)),
    ("ofp", PUSH, "раз", "higher", "female", None, (4, 7, 10, 12)),
    ("ofp", BEND, "см", "higher", "male", None, (1, 3, 5, 6)),
    ("ofp", BEND, "см", "higher", "female", None, (3, 5, 8, 9)),
    ("sfp", TYPING, "зн/мин", "higher", None, None, (80, 120, 160, 200)),
    ("sfp", CONTEST, "задач", "higher", None, 1, (2, 4, 6, 8)),
]


def standards_demo(db, admin, coach_user, athletes):
    """The demo athlete has passed most standards for the next stage but lacks
    the rank; one coached athlete is ready, another is halfway; one was
    transferred last year."""
    today = date.today()
    source = "Демо · ориентир для показа, сверить с приказом Минспорта России об утверждении ФССП"
    catalog = {}
    for category, name, unit, better, sex, discipline_id, values in STANDARDS:
        for stage, threshold in zip(STAGES, values):
            s = TrainingStandard(
                stage=stage, category=category, name=name, unit=unit, better=better,
                threshold=threshold, sex=sex, discipline_id=discipline_id,
                source=source, sort_order=len(catalog) * 10,
            )
            db.add(s)
            catalog[stage, name, sex] = s
    db.flush()

    def record(athlete, stage, values, days_ago):
        sex = athlete.user.sex
        for name, value in values.items():
            s = catalog.get((stage, name, sex)) or catalog[stage, name, None]
            db.add(
                StandardResult(
                    athlete_id=athlete.id, standard_id=s.id, value=value,
                    tested_on=today - timedelta(days=days_ago), threshold=s.threshold,
                    passed=meets(s, value), recorded_by=coach_user.id, recorded_role="coach",
                )
            )

    record(athletes[0], "ssm", {RUN: 6.0, PUSH: 9, BEND: 9, TYPING: 170, CONTEST: 6}, 20)
    record(athletes[0], "ssm", {PUSH: 8}, 120)
    for a in athletes[1:3]:
        a.training_stage = STAGES["np"]
    record(athletes[1], "ut", {RUN: 6.1, PUSH: 15, BEND: 4, TYPING: 130, CONTEST: 4}, 14)
    record(athletes[2], "ut", {RUN: 6.5, PUSH: 6, BEND: 6, TYPING: 125}, 10)
    # last year's testing of the transferred athlete has already expired
    moved = athletes[3]
    record(moved, "ut", {RUN: 6.0, PUSH: 14, BEND: 4, TYPING: 128, CONTEST: 5}, 400)
    db.flush()
    moved.training_stage = STAGES["np"]
    state = readiness(db, moved, today - timedelta(days=390))
    db.add(
        StageTransfer(
            athlete_id=moved.id, from_stage=STAGES["np"], to_stage="ut",
            decided_on=today - timedelta(days=390), order_number="ДЕМО-25/Э",
            basis=basis_of(state), created_by=admin.id,
        )
    )
    moved.training_stage = STAGES["ut"]
    db.flush()
    ready = athletes[1]
    notify(
        db,
        [*admins(db), *athlete_audience(db, ready.id)],
        "Готов к переводу на следующий этап",
        f"{ready.user.full_name}: выполнены нормативы этапа «{STAGES['ut']}». "
        "Перевод оформляет федерация.",
        f"stage-ready:{ready.id}:ut",
    )


def seed(demo=False):
    with SessionLocal() as db:
        for k, v in ROLES:
            if not db.get(Role, k):
                db.add(Role(id=k, name=v))
        db.flush()
        if not db.scalar(select(Discipline.id)):
            db.add_all(
                [
                    Discipline(id=i + 1, name=n, short_name=s)
                    for i, (n, s) in enumerate(DISCIPLINES)
                ]
            )
        if not db.scalar(select(CompetitionType.id)):
            db.add_all(
                [
                    # ids from the sequence, so the federation can add types later
                    CompetitionType(name=n, rating_class=c)
                    for n, c in COMPETITION_TYPES
                ]
            )
        if not db.scalar(select(AgeGroup.id)):
            db.add_all(
                [
                    AgeGroup(
                        name=n,
                        sex=sex,
                        min_age=lo,
                        max_age=hi,
                        age_rule="year",
                        sort_order=i * 10,
                    )
                    for i, (n, sex, lo, hi) in enumerate(AGE_GROUPS)
                ]
            )
        for level, values in [
            ("russian_championship", (100, 80, 60)),
            ("russian_junior", (80, 60, 40)),
            ("interregional", (60, 45, 30)),
            ("regional", (40, 30, 20)),
        ]:
            if not db.get(RatingRule, level):
                db.add(
                    RatingRule(
                        level=level, first=values[0], second=values[1], third=values[2]
                    )
                )
        for level, values in DEFAULT_AMOUNTS:
            if not db.get(GovernorAwardRule, level):
                db.add(
                    GovernorAwardRule(
                        level=level, first=values[0], second=values[1], third=values[2]
                    )
                )
        db.commit()
        if not demo:
            return
        if db.scalar(select(User.id).where(User.email == "admin@demo.example")):
            # Demo data loaded before the ministry cabinet existed: add only it.
            ministry_demo(db)
            db.commit()
            return
        today = date.today()
        year = today.year
        hashed = password_hash.hash(os.getenv("DEMO_PASSWORD", "DemoPass2026!"))

        def make(email, name, roles, born=date(1999, 5, 12)):
            first = name.removeprefix("Демо · ").split()[0]
            u = User(
                email=email,
                full_name=name,
                birth_date=born,
                sex="female" if first in FEMALE_NAMES | {"Марина"} else "male",
                password_hash=hashed,
            )
            u.roles = [db.get(Role, r) for r in roles]
            db.add(u)
            db.flush()
            return u

        admin = make(
            "admin@demo.example",
            "Демо · Алексей Северный",
            ["admin", "athlete", "coach", "judge", "ministry"],
        )
        trainer = make("coach@demo.example", "Демо · Марина Ветрова", ["coach"])
        referee = make("judge@demo.example", "Демо · Павел Лесной", ["judge"])
        orgs = [
            Organization(name=n, kind="Учебный клуб", municipality=m)
            for n, m in [
                ("Демо · Код Оренбурга", "Оренбург"),
                ("Демо · Орский алгоритм", "Орск"),
                ("Демо · Бузулук IT", "Бузулук"),
            ]
        ]
        db.add_all(orgs)
        db.flush()
        coach = Coach(user_id=trainer.id, organization_id=orgs[0].id)
        db.add_all([coach, Coach(user_id=admin.id), Judge(user_id=admin.id)])
        judge = Judge(user_id=referee.id)
        db.add(judge)
        db.flush()
        db.add_all(
            [
                JudgeCategory(
                    judge_id=j.id,
                    name="Судья второй категории",
                    # two-year term, still valid for the demo period
                    assigned_on=today - timedelta(days=410),
                    expires_on=today + timedelta(days=320),
                    order_number="ДЕМО-26/С",
                )
                for j in db.scalars(select(Judge))
            ]
        )
        names = [
            "Арина Искрова",
            "Михаил Полянов",
            "София Звёздная",
            "Илья Родников",
            "Дарья Снежина",
            "Матвей Лучистый",
            "Ева Вершинина",
            "Тимофей Озёрный",
            "Анна Ладная",
            "Никита Туманов",
            "Вера Цветная",
            "Лев Рассветов",
            "Алиса Кедрова",
            "Роман Радужный",
            "Мирослава Ясная",
            "Даниил Весенний",
            "Полина Тихая",
            "Артём Дальний",
        ]
        athletes = []
        for i, name in enumerate(names):
            u = make(
                "athlete@demo.example" if i == 0 else f"athlete{i}@demo.example",
                "Демо · " + name,
                ["athlete"],
                date(year - 17 - i % 9, 3, 10),
            )
            if age_at(u.birth_date) < 18:
                u.guardian_name = "Демо · Законный представитель " + name.split()[-1]
                u.guardian_consent_at = now()
            a = Athlete(
                user_id=u.id,
                organization_id=orgs[i % 3].id,
                municipality=orgs[i % 3].municipality,
                training_stage="Учебно-тренировочный этап",
                rusada_date=today - timedelta(days=60),
            )
            db.add(a)
            db.flush()
            athletes.append(a)
            for d in {1, i % 6 + 1}:
                db.add(
                    AthleteDiscipline(
                        athlete_id=a.id, discipline_id=d, start_year=year - 3 + i % 4
                    )
                )
        a = Athlete(
            user_id=admin.id, organization_id=orgs[0].id, municipality="Оренбург"
        )
        db.add(a)
        db.flush()
        athletes.append(a)
        db.add(AthleteDiscipline(athlete_id=a.id, discipline_id=1, start_year=year - 1))
        for a in athletes:
            first = min(
                db.scalars(
                    select(AthleteDiscipline.start_year).where(
                        AthleteDiscipline.athlete_id == a.id
                    )
                )
            )
            db.add(
                AthleteOrganization(
                    athlete_id=a.id,
                    organization_id=a.organization_id,
                    start_date=date(first, 1, 1),
                )
            )
        # Demo transfer: the second athlete moved from Orenburg to Orsk last autumn.
        moved = athletes[1]
        db.flush()
        period = db.scalar(
            select(AthleteOrganization).where(
                AthleteOrganization.athlete_id == moved.id
            )
        )
        period.organization_id = orgs[0].id
        period.end_date = date(year - 1, 8, 31)
        db.add(
            AthleteOrganization(
                athlete_id=moved.id,
                organization_id=moved.organization_id,
                start_date=date(year - 1, 9, 1),
            )
        )
        for a in athletes[1:6]:
            link = AthleteCoach(
                athlete_id=a.id, coach_id=coach.id, discipline_id=1, status="active"
            )
            db.add(link)
            db.flush()
            db.add(LinkHistory(link_id=link.id, actor_id=a.user_id, status="active"))
        for k, days in enumerate([60, 30]):
            c = Competition(
                title=[
                    "Демо · Чемпионат Оренбургской области",
                    "Демо · Кубок регионов по алгоритмам",
                ][k],
                discipline_id=1,
                type_id=1 if k == 0 else 3,
                start_date=today - timedelta(days=days),
                end_date=today - timedelta(days=days),
                deadline=today - timedelta(days=days + 2),
                location="Оренбург · Демо-арена",
                format="onsite",
                status="regional" if k == 0 else "interregional",
                rating_level="regional" if k == 0 else "interregional",
                calendar_plan="Оренбургская область" if k == 0 else "ЕКП",
                calendar_number=f"ДЕМО-{k + 1}",
                state="published",
            )
            db.add(c)
            db.flush()
            db.add(
                CompetitionJudge(
                    competition_id=c.id, judge_id=judge.id, position="Главный судья"
                )
            )
            for i, a in enumerate(athletes[:8]):
                db.add(
                    CompetitionApplication(
                        competition_id=c.id,
                        athlete_id=a.id,
                        submitted_by=a.user_id,
                        status="approved",
                    )
                )
                db.add(
                    CompetitionResult(
                        competition_id=c.id,
                        athlete_id=a.id,
                        place=i + 1,
                        score=1000 - i * 97 - k * 10,
                    )
                )
            add_version(db, c, admin.id)
            cup = c
        db.flush()
        result = db.scalar(
            select(CompetitionResult).where(
                CompetitionResult.athlete_id == athletes[0].id
            )
        )
        db.add(
            SportsRank(
                athlete_id=athletes[0].id,
                discipline_id=1,
                name="III",
                assigned_on=today - timedelta(days=30),
                expires_on=today + timedelta(days=21),
                order_number="ДЕМО-26/Р",
                result_id=result.id,
            )
        )
        # Illustrative conditions for the personal path; not real EVSK norms.
        db.add_all(
            [
                EvskRule(
                    discipline_id=1,
                    level=level,
                    rank_name=rank,
                    max_place=place,
                    min_participants=count,
                    source="Демо · условие для показа, не является нормативом ЕВСК",
                )
                for rank, level, place, count in [
                    ("II", "regional", 3, 8),
                    ("I", "interregional", 2, 8),
                    ("КМС", "russian_championship", 3, 10),
                ]
            ]
        )
        for i in range(6):
            start = today + timedelta(days=10 + i * 6)
            c = Competition(
                title=[
                    "Демо · Открытый кубок Оренбуржья",
                    "Демо · Продуктовый хакатон",
                    "Демо · Киберщит региона",
                    "Демо · Интеллект на старте",
                    "Демо · Робототехническая лига",
                    "Демо · Беспилотный маршрут",
                ][i],
                discipline_id=i + 1,
                type_id=3,
                start_date=start,
                end_date=start + timedelta(days=1),
                deadline=start - timedelta(days=3),
                location=[
                    "Оренбург · Технопарк",
                    "Онлайн-платформа",
                    "Оренбург · Технопарк и онлайн-платформа",
                ][i % 3],
                format=["onsite", "online", "hybrid"][i % 3],
                status="regional",
                rating_level="regional",
                calendar_plan="Оренбургская область",
                calendar_number=f"ДЕМО-{i + 10}",
                state="open",
            )
            db.add(c)
            db.flush()
            # Open cup: every group; "Интеллект на старте": youth only.
            groups = {0: [n for n, *_ in AGE_GROUPS], 3: ["Юноши", "Девушки"]}
            if i in groups:
                bound = db.scalars(
                    select(AgeGroup).where(AgeGroup.name.in_(groups[i]))
                ).all()
                db.add_all(
                    [
                        CompetitionAgeGroup(competition_id=c.id, age_group_id=g.id)
                        for g in bound
                    ]
                )
                c.min_age = min(g.min_age for g in bound)
                c.max_age = max(g.max_age for g in bound)
                participants = ", ".join(
                    f"{g.name} {g.min_age}–{g.max_age}"
                    if g.max_age < 100
                    else f"{g.name} {g.min_age}+"
                    for g in bound
                ) + " (по году рождения)"
            else:
                participants = f"{c.min_age}–{c.max_age} лет на дату старта"
            pdf = export_document(
                OfficialDocument(
                    kind="Положение",
                    title=f"о проведении соревнования «{c.title}»",
                    headers=["Раздел", "Содержание"],
                    rows=[
                        ["Наименование", c.title],
                        ["Сроки", f"{c.start_date:%d.%m.%Y} — {c.end_date:%d.%m.%Y}"],
                        ["Место", c.location],
                        ["Участники", participants],
                        ["Заявки", f"Через платформу до {c.deadline:%d.%m.%Y}"],
                        ["Документ", "Демонстрационный образец, не имеет силы"],
                    ],
                    number=c.calendar_number,
                    approve=(settings.fsp_head_position, settings.fsp_head_name),
                ),
                "pdf",
            )
            db.add(
                CompetitionRegulation(
                    competition_id=c.id,
                    filename=f"Положение {c.calendar_number}.pdf",
                    content_type="application/pdf",
                    size=len(pdf),
                    data=pdf,
                    uploaded_by=admin.id,
                )
            )
        db.add(
            Deadline(
                title="Отчёт о численности занимающихся",
                due_on=today + timedelta(days=12),
            )
        )
        indicators_demo(db, admin, year - 1)
        awards_demo(db, admin, (today - timedelta(days=30)).year)
        appeals_demo(db, admin, trainer, athletes, cup)
        standards_demo(db, admin, trainer, athletes)
        ministry_demo(db)
        audit(db, Actor(admin, "admin"), "Загрузка фиктивных демоданных", admin)
        notify(
            db,
            [u.id for u in db.scalars(select(User))],
            "Добро пожаловать в ОренКод",
            "Демонстрационный контур. Все персональные данные вымышлены.",
            "demo-welcome",
        )
        recalculate(db, year)
        db.commit()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--demo", action="store_true")
    seed(parser.parse_args().demo)
