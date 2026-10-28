from collections import defaultdict
from datetime import date
from sqlalchemy import select
from app.models import Athlete, TrainingGroup, GroupEnrollment, TrainingLesson, LessonAttendance, Organization, Discipline
from app.services.common import age_at
from app.services.standards import SHORT


def training_dynamics(db, start_year, end_year, organization_id=None, discipline_id=None,
                      municipality="", min_age=0, max_age=100):
    buckets = defaultdict(lambda: {"athletes": set(), "groups": set(), "lessons": set(),
                                    "present": 0, "confirmed": 0, "minutes": 0})

    def key_for(group, athlete, year):
        if (organization_id and group.organization_id != organization_id
                or discipline_id and group.discipline_id != discipline_id
                or municipality.lower() not in athlete.municipality.lower()
                or not min_age <= age_at(athlete.user.birth_date, date(year, 12, 31)) <= max_age):
            return None
        return (year, db.get(Organization, group.organization_id).name,
                db.get(Discipline, group.discipline_id).short_name, SHORT[group.stage])

    for enrollment, group, athlete in db.execute(select(GroupEnrollment, TrainingGroup, Athlete)
            .join(TrainingGroup, TrainingGroup.id == GroupEnrollment.group_id)
            .join(Athlete, Athlete.id == GroupEnrollment.athlete_id)):
        for year in range(max(start_year, enrollment.start_date.year),
                          min(end_year, (enrollment.end_date or date.today()).year) + 1):
            key = key_for(group, athlete, year)
            if key:
                buckets[key]["athletes"].add(athlete.id)
                buckets[key]["groups"].add(group.id)
    for attendance, lesson, group, athlete in db.execute(
        select(LessonAttendance, TrainingLesson, TrainingGroup, Athlete)
        .join(TrainingLesson, TrainingLesson.id == LessonAttendance.lesson_id)
        .join(TrainingGroup, TrainingGroup.id == TrainingLesson.group_id)
        .join(Athlete, Athlete.id == LessonAttendance.athlete_id)
        .where(TrainingLesson.status == "completed", TrainingLesson.held_on >= date(start_year, 1, 1), TrainingLesson.held_on <= date(end_year, 12, 31))
    ):
        key = key_for(group, athlete, lesson.held_on.year)
        if key:
            bucket = buckets[key]
            bucket["lessons"].add(lesson.id)
            if attendance.status == "present":
                bucket["present"] += 1
                if attendance.confirmed_at:
                    bucket["confirmed"] += 1
                    bucket["minutes"] += lesson.duration_minutes
    return {
        "headers": ["Год", "Организация", "Дисциплина", "Этап", "Группы", "Спортсмены", "Занятия", "Посещения", "Подтверждены", "Подтв. человеко-часы"],
        "rows": [[*key, len(b["groups"]), len(b["athletes"]), len(b["lessons"]), b["present"], b["confirmed"], round(b["minutes"] / 60, 2)]
                 for key, b in sorted(buckets.items())],
        "source": "Зачисления считаются по пересечению с годом, занятия — по дате проведения. Посещения — отметки «присутствовал»; подтверждённые человеко-часы учитывают только подтверждения спортсменов. Внутри строки спортсмен и занятие считаются один раз; строки разных группировок не следует суммировать как уникальную численность. Муниципалитет — текущий, возраст — на 31 декабря.",
    }
