"""Explicit, idempotent D3 demo. Does not reset existing groups or attendance."""
from datetime import date, time, timedelta
from sqlalchemy import select
from app.db import SessionLocal
from app.models import User, Athlete, Coach, CoachDiscipline, Organization, TrainingGroup, GroupEnrollment, TrainingLesson, LessonAttendance, TrainingMaterial
from app.security import Actor
from app.routers.training import add_enrollment
from app.services.standards import stage_of


def seed_training_demo(db):
    admin = db.scalar(select(User).where(User.email == "admin@demo.example"))
    athlete = db.scalar(select(Athlete).join(User).where(User.email == "athlete@demo.example"))
    coach = db.scalar(select(Coach).join(User).where(User.email == "coach@demo.example"))
    if not admin or not athlete or not coach or not coach.organization_id:
        raise ValueError("Сначала загрузите демонстрационные аккаунты: python -m app.seed --demo")
    org = db.get(Organization, coach.organization_id)
    if athlete.organization_id != org.id or not stage_of(athlete):
        raise ValueError("Демо-профили изменены: организация спортсмена должна совпадать с тренером, этап должен быть указан")
    name = "Демо · Алгоритмы — учебная группа"
    existing = db.scalar(select(TrainingGroup).where(TrainingGroup.organization_id == org.id, TrainingGroup.name == name))
    if existing:
        seed_schedule_demo(db, admin, existing)
        seed_correspondence_demo(db, admin, existing)
        return existing.id
    program = "Демо · Подготовка по алгоритмическому программированию"
    org.programs = list(dict.fromkeys([*(org.programs or []), program]))
    if not db.get(CoachDiscipline, (coach.id, 1)):
        db.add(CoachDiscipline(coach_id=coach.id, discipline_id=1))
    group = TrainingGroup(organization_id=org.id, discipline_id=1, coach_id=coach.id,
                          name=name, stage=stage_of(athlete), program=program, capacity=20)
    db.add(group)
    db.flush()
    add_enrollment(db, Actor(admin, "admin"), group, athlete, date.today() - timedelta(days=2), "ДЕМО-УТ-01")
    lesson = TrainingLesson(group_id=group.id, held_on=date.today() - timedelta(days=1),
                            topic="Демо · Разбор алгоритмов и задач", duration_minutes=90, created_by=coach.user_id)
    db.add(lesson)
    db.flush()
    db.add(LessonAttendance(lesson_id=lesson.id, athlete_id=athlete.id, status="present", marked_by=coach.user_id))
    db.flush()
    seed_schedule_demo(db, admin, group)
    seed_correspondence_demo(db, admin, group)
    return group.id


def seed_schedule_demo(db, admin, group):
    from app.schemas.training import LessonIn
    from app.routers.training import create_lesson
    title = "Демо · Практика алгоритмов: графы и поиск"
    if db.scalar(select(TrainingLesson.id).where(TrainingLesson.group_id == group.id, TrainingLesson.topic == title)):
        return
    create_lesson(group.id, LessonIn(
        held_on=date.today() + timedelta(days=1), start_time=time(18, 0), timezone="Asia/Yekaterinburg",
        topic=title, duration_minutes=90, format="onsite",
        location="Демо · Оренбург, учебный центр «Код Оренбурга», аудитория 12",
        instructions="Возьмите ноутбук и зарядное устройство. Перед занятием повторите поиск в ширину и глубину. Это демонстрационное расписание; адрес учебного центра вымышленный.",
    ), Actor(admin, "admin"), db)


def seed_correspondence_demo(db, admin, group):
    from app.config import settings
    from app.schemas.training import LessonIn
    from app.routers.training import create_lesson
    title = "Демо · Заочное задание: обход графа"
    if db.scalar(select(TrainingLesson.id).where(TrainingLesson.group_id == group.id, TrainingLesson.topic == title)):
        return
    lesson = create_lesson(group.id, LessonIn(
        held_on=date.today(), due_on=date.today() + timedelta(days=7), format="correspondence",
        topic=title, duration_minutes=60,
        instructions="Скачайте файл с заданием, изучите справочник по ссылке и самостоятельно выполните упражнения. Это демонстрационное задание.",
    ), Actor(admin, "admin"), db)
    content = "# Заочное задание: обход графа\n\n1. Опишите представление графа списками смежности.\n2. Реализуйте поиск в ширину и проверьте на своём примере.\n3. Подготовьте короткое объяснение работы алгоритма.\n\nДемонстрационные учебные материалы.\n".encode("utf-8")
    db.add_all([
        TrainingMaterial(lesson_id=lesson["id"], kind="file", title="Задание по графам", filename="zadanie-grafy.md", content_type="text/plain; charset=utf-8", size=len(content), data=content, created_by=admin.id),
        TrainingMaterial(lesson_id=lesson["id"], kind="link", title="Справочник понятий платформы", url=settings.public_base_url.rstrip("/") + "/glossary", created_by=admin.id),
    ])
    db.flush()


if __name__ == "__main__":
    with SessionLocal() as session:
        group_id = seed_training_demo(session)
        session.commit()
        print(f"Демо Д3 готово: группа {group_id}. Откройте /training.")
