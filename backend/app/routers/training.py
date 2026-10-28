"""D3: federation enrollment, coach journal, athlete confirmation."""
from datetime import date, timedelta
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.db import get_db
from app.models import (
    Athlete, AthleteDiscipline, Coach, CoachDiscipline, Discipline, Organization,
    TrainingGroup, GroupEnrollment, TrainingLesson, LessonAttendance, Notification, now,
)
from app.schemas.training import GroupIn, EnrollmentIn, TransferIn, EndIn, LessonIn, AttendanceIn, LessonCancelIn
from app.security import Actor, allow
from app.services.common import row, require, own, active_card, audit, transfer
from app.services.athlete_ids import parse_athlete_id, public_athlete_id
from app.services.standards import STAGES, stage_of
from app.services.documents import OfficialDocument
from app.routers.reports import download
from app.services.training_schedule import (
    interval, lesson_view, roster, check_conflicts, lesson_notice, enrollment_notice, coach_assignment_notice,
)
from app.services.training_materials import lesson_materials

router = APIRouter(tags=["Организации, группы и занятия"])
read = allow("admin", "coach", "athlete", "ministry")


def group_access(db, actor, group_id, write=False):
    group = db.scalar(select(TrainingGroup).where(TrainingGroup.id == group_id).with_for_update()) if write else db.get(TrainingGroup, group_id)
    if group is None:
        raise HTTPException(404, "Группа не найдена")
    if actor.role == "coach":
        if active_card(db, Coach, actor).id != group.coach_id:
            raise HTTPException(403, "Группа другого тренера")
    elif actor.role == "athlete":
        if write or not db.scalar(select(GroupEnrollment.id).where(
            GroupEnrollment.group_id == group.id,
            GroupEnrollment.athlete_id == own(db, Athlete, actor).id,
        )):
            raise HTTPException(403, "Нет доступа к группе")
    elif actor.role not in (("admin",) if write else ("admin", "ministry")):
        raise HTTPException(403, "Нет доступа к группе")
    if write and group.archived:
        raise HTTPException(409, "Группа в архиве")
    return group


def group_view(db, group):
    active = db.scalars(select(GroupEnrollment).where(
        GroupEnrollment.group_id == group.id, GroupEnrollment.end_date.is_(None),
    )).all()
    return {**row(group), "organization": require(db, Organization, group.organization_id).name,
            "discipline": require(db, Discipline, group.discipline_id).short_name,
            "coach": require(db, Coach, group.coach_id).user.full_name,
            "stage_name": STAGES[group.stage], "enrolled_count": len(active)}


def enrollment_view(db, obj):
    athlete = require(db, Athlete, obj.athlete_id)
    return {**row(obj), "full_name": athlete.user.full_name,
            "public_id": public_athlete_id(athlete.id)}


def validate_group(db, data):
    org = require(db, Organization, data.organization_id)
    require(db, Discipline, data.discipline_id)
    coach = require(db, Coach, data.coach_id)
    if coach.archived_at or coach.organization_id != org.id:
        raise HTTPException(422, "Выберите действующего тренера этой организации")
    if not db.get(CoachDiscipline, (coach.id, data.discipline_id)):
        raise HTTPException(422, "Тренер не ведёт выбранную дисциплину")
    if data.program not in org.programs:
        raise HTTPException(422, "Сначала добавьте программу в карточку организации")


@router.get("/training-groups")
def groups(actor: Actor = Depends(read), db: Session = Depends(get_db)):
    query = select(TrainingGroup).order_by(TrainingGroup.archived, TrainingGroup.name)
    if actor.role == "coach":
        query = query.where(TrainingGroup.coach_id == own(db, Coach, actor).id)
    if actor.role == "athlete":
        query = query.where(TrainingGroup.id.in_(select(GroupEnrollment.group_id).where(
            GroupEnrollment.athlete_id == own(db, Athlete, actor).id)))
    return [group_view(db, g) for g in db.scalars(query)]


@router.post("/training-groups", status_code=201)
def create_group(data: GroupIn, actor: Actor = Depends(allow("admin")), db: Session = Depends(get_db)):
    validate_group(db, data)
    obj = TrainingGroup(**data.model_dump())
    db.add(obj)
    audit(db, actor, "Создание учебной группы", obj)
    coach_assignment_notice(db, obj)
    return group_view(db, obj)


@router.put("/training-groups/{group_id}")
def edit_group(group_id: int, data: GroupIn, actor: Actor = Depends(allow("admin")), db: Session = Depends(get_db)):
    obj = group_access(db, actor, group_id, True)
    old_coach_id = obj.coach_id
    validate_group(db, data)
    if db.scalar(select(GroupEnrollment.id).where(GroupEnrollment.group_id == obj.id).limit(1)):
        if any(getattr(obj, k) != getattr(data, k) for k in ("organization_id", "discipline_id", "stage")):
            raise HTTPException(409, "Организация, дисциплина и этап группы с историей не меняются; создайте новую группу")
    if data.capacity < group_view(db, obj)["enrolled_count"]:
        raise HTTPException(409, "Вместимость меньше текущего состава")
    for key, value in data.model_dump().items():
        setattr(obj, key, value)
    audit(db, actor, "Изменение учебной группы", obj)
    if obj.coach_id != old_coach_id:
        for lesson in db.scalars(select(TrainingLesson).where(TrainingLesson.group_id == obj.id, TrainingLesson.status == "planned")):
            check_conflicts(db, obj, lesson)
        coach_assignment_notice(db, obj)
    return group_view(db, obj)


@router.post("/training-groups/{group_id}/archive")
def archive_group(group_id: int, actor: Actor = Depends(allow("admin")), db: Session = Depends(get_db)):
    group = group_access(db, actor, group_id, True)
    if group_view(db, group)["enrolled_count"]:
        raise HTTPException(409, "Сначала переведите или отчислите спортсменов")
    if db.scalar(select(TrainingLesson.id).where(TrainingLesson.group_id == group.id, TrainingLesson.status == "planned").limit(1)):
        raise HTTPException(409, "Сначала завершите или отмените запланированные занятия")
    group.archived = True
    audit(db, actor, "Архив учебной группы", group)
    return group_view(db, group)


@router.get("/training-groups/{group_id}")
def group_detail(group_id: int, actor: Actor = Depends(read), db: Session = Depends(get_db)):
    group = group_access(db, actor, group_id)
    query = select(GroupEnrollment).where(GroupEnrollment.group_id == group.id).order_by(GroupEnrollment.start_date, GroupEnrollment.id)
    if actor.role == "athlete":
        query = query.where(GroupEnrollment.athlete_id == own(db, Athlete, actor).id)
    return {**group_view(db, group), "enrollments": [enrollment_view(db, e) for e in db.scalars(query)]}


def add_enrollment(db, actor, group, athlete, start, order):
    if start > date.today() or start < athlete.user.birth_date:
        raise HTTPException(422, "Дата зачисления должна быть между датой рождения и сегодняшним днём")
    if athlete.suspended_until and athlete.suspended_until >= start:
        raise HTTPException(409, "Спортсмен отстранён на дату зачисления")
    discipline = db.get(AthleteDiscipline, (athlete.id, group.discipline_id))
    if not discipline or not discipline.start_year <= start.year <= (discipline.end_year or 2100):
        raise HTTPException(422, "Дисциплина спортсмена не действует на дату зачисления")
    stage = stage_of(athlete)
    if stage != group.stage and not (stage is None and group.stage == "np"):
        raise HTTPException(409, "Этап спортсмена не совпадает с группой. Сначала оформите аттестацию и перевод на этап")
    periods = db.scalars(select(GroupEnrollment).join(TrainingGroup).where(
        GroupEnrollment.athlete_id == athlete.id,
        TrainingGroup.discipline_id == group.discipline_id,
    )).all()
    if any(p.end_date is None or p.end_date >= start for p in periods):
        raise HTTPException(409, "По этой дисциплине уже есть группа или пересечение с историей")
    if group_view(db, group)["enrolled_count"] >= group.capacity:
        raise HTTPException(409, "В группе нет свободных мест")
    # Organization is a single current affiliation. Require a deliberate profile
    # transfer first instead of silently closing unrelated discipline groups.
    if athlete.organization_id != group.organization_id:
        raise HTTPException(409, "Сначала оформите переход спортсмена в эту организацию в профиле")
    from app.services.common import memberships
    org_periods = memberships(db, athlete.id)
    if not any(p.organization_id == group.organization_id and p.start_date <= start
               and (p.end_date is None or p.end_date >= start) for p in org_periods):
        raise HTTPException(409, "На дату зачисления спортсмен не состоял в организации")
    if stage is None:
        athlete.training_stage = STAGES["np"]
    obj = GroupEnrollment(group_id=group.id, athlete_id=athlete.id, start_date=start,
                          order_number=order, created_by=actor.user.id)
    db.add(obj)
    for lesson in db.scalars(select(TrainingLesson).where(TrainingLesson.group_id == group.id, TrainingLesson.held_on >= start, TrainingLesson.status == "completed")):
        db.add(LessonAttendance(lesson_id=lesson.id, athlete_id=athlete.id))
    audit(db, actor, "Зачисление в учебную группу", obj)
    for lesson in db.scalars(select(TrainingLesson).where(TrainingLesson.group_id == group.id, TrainingLesson.status == "planned", TrainingLesson.held_on >= start)):
        check_conflicts(db, group, lesson)
    enrollment_notice(db, obj, "Вы зачислены в учебную группу")
    return obj


@router.post("/training-groups/{group_id}/enrollments", status_code=201)
def enroll(group_id: int, data: EnrollmentIn, actor: Actor = Depends(allow("admin")), db: Session = Depends(get_db)):
    group = group_access(db, actor, group_id, True)
    athlete = db.scalar(select(Athlete).where(Athlete.id == parse_athlete_id(data.athlete_public_id)).with_for_update(of=Athlete))
    if not athlete:
        raise HTTPException(404, "Спортсмен с таким ID не найден")
    return enrollment_view(db, add_enrollment(db, actor, group, athlete, data.start_date, data.order_number))


def close_enrollment(db, obj, end, order):
    if obj.end_date is not None:
        raise HTTPException(409, "Зачисление уже завершено")
    if not obj.start_date <= end <= date.today():
        raise HTTPException(422, "Дата завершения вне периода зачисления")
    recorded = db.scalar(select(LessonAttendance.id).join(TrainingLesson).where(
        TrainingLesson.group_id == obj.group_id, LessonAttendance.athlete_id == obj.athlete_id,
        TrainingLesson.held_on > end,
    ).limit(1))
    if recorded:
        raise HTTPException(409, "После этой даты уже есть записи журнала; выберите более позднюю дату")
    obj.end_date, obj.end_order_number = end, order


@router.post("/group-enrollments/{enrollment_id}/transfer", status_code=201)
def move(enrollment_id: int, data: TransferIn, actor: Actor = Depends(allow("admin")), db: Session = Depends(get_db)):
    target = group_access(db, actor, data.target_group_id, True)
    obj = require(db, GroupEnrollment, enrollment_id)
    athlete = db.scalar(select(Athlete).where(Athlete.id == obj.athlete_id).with_for_update(of=Athlete))
    source = require(db, TrainingGroup, obj.group_id)
    if source.id == target.id or source.discipline_id != target.discipline_id:
        raise HTTPException(422, "Выберите другую группу той же дисциплины")
    close_enrollment(db, obj, data.on - timedelta(days=1), data.order_number)
    db.flush()
    if source.organization_id != target.organization_id:
        transfer(db, athlete, target.organization_id, data.on)
    new = add_enrollment(db, actor, target, athlete, data.on, data.order_number)
    audit(db, actor, "Перевод между учебными группами", obj, {"target_group_id": target.id, "on": data.on.isoformat()})
    enrollment_notice(db, obj, "Обучение в прежней группе завершено: перевод")
    return enrollment_view(db, new)


@router.post("/group-enrollments/{enrollment_id}/end")
def end(enrollment_id: int, data: EndIn, actor: Actor = Depends(allow("admin")), db: Session = Depends(get_db)):
    obj = require(db, GroupEnrollment, enrollment_id)
    db.scalar(select(Athlete).where(Athlete.id == obj.athlete_id).with_for_update(of=Athlete))
    close_enrollment(db, obj, data.on, data.order_number)
    audit(db, actor, "Отчисление из учебной группы", obj)
    enrollment_notice(db, obj, "Обучение в группе завершено")
    return enrollment_view(db, obj)


def journal(db, actor, group):
    lessons = db.scalars(select(TrainingLesson).where(TrainingLesson.group_id == group.id).order_by(TrainingLesson.held_on.desc(), TrainingLesson.id.desc())).all()
    athlete_id = own(db, Athlete, actor).id if actor.role == "athlete" else None
    result = []
    for lesson in lessons:
        query = select(LessonAttendance).where(LessonAttendance.lesson_id == lesson.id).order_by(LessonAttendance.id)
        if athlete_id:
            query = query.where(LessonAttendance.athlete_id == athlete_id)
        attendance = [{**row(a), "full_name": require(db, Athlete, a.athlete_id).user.full_name,
                       "public_id": public_athlete_id(a.athlete_id)} for a in db.scalars(query)]
        if not athlete_id or attendance or athlete_id in roster(db, group.id, lesson.held_on):
            result.append({**lesson_view(lesson), "attendance": attendance, "materials": lesson_materials(db, lesson.id)})
    return result


@router.get("/training-groups/{group_id}/lessons")
def lessons(group_id: int, actor: Actor = Depends(read), db: Session = Depends(get_db)):
    return journal(db, actor, group_access(db, actor, group_id))


@router.post("/training-groups/{group_id}/lessons", status_code=201)
def create_lesson(group_id: int, data: LessonIn, actor: Actor = Depends(allow("admin", "coach")), db: Session = Depends(get_db)):
    group = group_access(db, actor, group_id, True)
    participants = roster(db, group.id, data.held_on)
    if not participants:
        raise HTTPException(409, "На эту дату в группе нет зачисленных спортсменов")
    values = data.model_dump()
    values["meeting_url"] = str(data.meeting_url) if data.meeting_url else None
    obj = TrainingLesson(group_id=group.id, created_by=actor.user.id,
                         status="planned" if data.start_time or data.format == "correspondence" else "completed", **values)
    check_conflicts(db, group, obj)
    db.add(obj)
    db.flush()
    if obj.status == "completed":
        for athlete_id in participants:
            db.add(LessonAttendance(lesson_id=obj.id, athlete_id=athlete_id))
    audit(db, actor, "Планирование занятия" if obj.status == "planned" else "Запись занятия в журнал", obj)
    if obj.status == "planned":
        lesson_notice(db, obj, "Назначено занятие", "planned")
    return lesson_view(obj)


def editable_lesson(db, actor, lesson_id):
    obj = db.scalar(select(TrainingLesson).where(TrainingLesson.id == lesson_id).with_for_update())
    if obj is None:
        raise HTTPException(404, "Занятие не найдено")
    group = group_access(db, actor, obj.group_id, True)
    if obj.status != "planned":
        raise HTTPException(409, "Изменять можно только запланированное занятие")
    return obj, group


@router.put("/training-lessons/{lesson_id}")
def reschedule(lesson_id: int, data: LessonIn, actor: Actor = Depends(allow("admin", "coach")), db: Session = Depends(get_db)):
    obj, group = editable_lesson(db, actor, lesson_id)
    if data.start_time is None and data.format != "correspondence":
        raise HTTPException(422, "Укажите время начала занятия")
    if not roster(db, group.id, data.held_on):
        raise HTTPException(409, "На новую дату нет зачисленных спортсменов")
    old_recipients = roster(db, group.id, obj.held_on)
    values = data.model_dump()
    values["meeting_url"] = str(data.meeting_url) if data.meeting_url else None
    # Validate before mutating the persistent row to keep the old schedule intact.
    proposal = TrainingLesson(id=obj.id, group_id=group.id, **values)
    check_conflicts(db, group, proposal)
    for key, value in values.items():
        setattr(obj, key, value)
    obj.revision += 1
    audit(db, actor, "Изменение расписания занятия", obj, data.model_dump(mode="json"))
    lesson_notice(db, obj, "Изменилось занятие: проверьте время и место", "rescheduled")
    # People who are no longer in the new roster also need to know it was moved.
    from app.services.notifications import notify
    removed = old_recipients - roster(db, group.id, obj.held_on)
    key = f"training-membership:{obj.id}:{obj.revision}"
    notify(db, [db.get(Athlete, aid).user_id for aid in removed], "Занятие перенесено за пределы вашего периода обучения", group.name, key)
    for n in db.scalars(select(Notification).where(Notification.event_key == key)):
        n.telegram_context = {"roles": ["athlete"], "path": f"/training?group={group.id}"}
    return lesson_view(obj)


@router.post("/training-lessons/{lesson_id}/cancel")
def cancel_lesson(lesson_id: int, data: LessonCancelIn, actor: Actor = Depends(allow("admin", "coach")), db: Session = Depends(get_db)):
    obj, _ = editable_lesson(db, actor, lesson_id)
    obj.status, obj.cancellation_reason = "cancelled", data.reason
    obj.revision += 1
    audit(db, actor, "Отмена занятия", obj, {"reason": data.reason})
    lesson_notice(db, obj, "Занятие отменено", "cancelled")
    return lesson_view(obj)


@router.post("/training-lessons/{lesson_id}/complete")
def complete_lesson(lesson_id: int, actor: Actor = Depends(allow("admin", "coach")), db: Session = Depends(get_db)):
    obj, group = editable_lesson(db, actor, lesson_id)
    _, end = interval(obj)
    if obj.format == "correspondence":
        from zoneinfo import ZoneInfo
        if now().astimezone(ZoneInfo(obj.timezone)).date() < obj.held_on:
            raise HTTPException(409, "Заочное занятие ещё не началось")
    elif end is None or now() < end:
        raise HTTPException(409, "Завершить занятие можно после времени окончания")
    participants = roster(db, group.id, obj.held_on)
    if not participants:
        raise HTTPException(409, "На дату занятия нет зачисленных спортсменов. Отмените занятие")
    if obj.format != "correspondence":
        for athlete_id in participants:
            db.add(LessonAttendance(lesson_id=obj.id, athlete_id=athlete_id))
    obj.status = "completed"
    obj.revision += 1
    audit(db, actor, "Занятие проведено", obj)
    return lesson_view(obj)


@router.get("/training-schedule")
def upcoming_lessons(actor: Actor = Depends(read), db: Session = Depends(get_db)):
    if actor.role == "coach":
        active_card(db, Coach, actor)
    result = []
    for group_data in groups(actor, db):
        if group_data["archived"]:
            continue
        group = db.get(TrainingGroup, group_data["id"])
        for lesson in journal(db, actor, group):
            if lesson["status"] == "planned":
                result.append({**lesson, "group_name": group.name, "coach": group_data["coach"]})
    return sorted(result, key=lambda l: (l["phase"] in ("awaiting_completion", "deadline_passed"), l["due_on"] or l["held_on"], str(l["start_time"] or "")))


@router.patch("/lesson-attendance/{attendance_id}")
def mark(attendance_id: int, data: AttendanceIn, actor: Actor = Depends(allow("admin", "coach")), db: Session = Depends(get_db)):
    obj = db.scalar(select(LessonAttendance).where(LessonAttendance.id == attendance_id).with_for_update())
    if obj is None:
        raise HTTPException(404, "Отметка не найдена")
    lesson = require(db, TrainingLesson, obj.lesson_id)
    group_access(db, actor, lesson.group_id, True)
    if lesson.status != "completed":
        raise HTTPException(409, "Посещаемость отмечается после завершения занятия")
    if obj.confirmed_at:
        raise HTTPException(409, "Подтверждённая спортсменом отметка не изменяется")
    if obj.status == data.status and not obj.dispute_reason:
        return row(obj)
    obj.status, obj.marked_by = data.status, actor.user.id
    obj.dispute_reason = None
    audit(db, actor, "Отметка посещения занятия", obj, {"status": data.status})
    if data.status != "unmarked":
        from app.services.notifications import notify
        key = f"training-attendance:{obj.id}:{now().isoformat()}"
        user_id = require(db, Athlete, obj.athlete_id).user_id
        notify(db, [user_id], "Подтвердите отметку посещения", lesson.topic, key)
        db.scalar(select(Notification).where(Notification.user_id == user_id, Notification.event_key == key)).telegram_context = {"roles": ["athlete"], "path": f"/training?group={lesson.group_id}", "attendance_id": obj.id, "status": obj.status}
    return row(obj)


@router.post("/lesson-attendance/{attendance_id}/confirm")
def confirm(attendance_id: int, actor: Actor = Depends(allow("athlete")), db: Session = Depends(get_db)):
    obj = db.scalar(select(LessonAttendance).where(LessonAttendance.id == attendance_id).with_for_update())
    if obj is None:
        raise HTTPException(404, "Отметка не найдена")
    if obj.athlete_id != own(db, Athlete, actor).id:
        raise HTTPException(403, "Можно подтвердить только свою отметку")
    if obj.status == "unmarked":
        raise HTTPException(409, "Дождитесь отметки тренера")
    if obj.dispute_reason:
        raise HTTPException(409, "Дождитесь ответа тренера на запрос исправления")
    if not obj.confirmed_at:
        obj.confirmed_at = now()
        audit(db, actor, "Подтверждение посещения занятия", obj)
    return row(obj)


@router.post("/lesson-attendance/{attendance_id}/dispute")
def dispute_attendance(attendance_id: int, data: LessonCancelIn, actor: Actor = Depends(allow("athlete")), db: Session = Depends(get_db)):
    obj = db.scalar(select(LessonAttendance).where(LessonAttendance.id == attendance_id).with_for_update())
    if obj is None:
        raise HTTPException(404, "Отметка не найдена")
    if obj.athlete_id != own(db, Athlete, actor).id:
        raise HTTPException(403, "Можно запросить исправление только своей отметки")
    if obj.confirmed_at or obj.status == "unmarked":
        raise HTTPException(409, "Запрос исправления доступен для неподтверждённой отметки тренера")
    obj.dispute_reason = data.reason
    lesson = require(db, TrainingLesson, obj.lesson_id)
    group = require(db, TrainingGroup, lesson.group_id)
    coach = require(db, Coach, group.coach_id)
    from app.services.notifications import notify
    key = f"training-dispute:{obj.id}:{now().isoformat()}"
    notify(db, [coach.user_id], "Спортсмен просит исправить посещаемость", f"{group.name}\n{lesson.topic}\n{data.reason}", key)
    db.scalar(select(Notification).where(Notification.event_key == key, Notification.user_id == coach.user_id)).telegram_context = {"roles": ["coach"], "path": f"/training?group={group.id}", "attendance_id": obj.id}
    audit(db, actor, "Запрос исправления посещаемости", obj, {"reason": data.reason})
    return row(obj)


@router.get("/exports/training-groups/{group_id}.{fmt}")
def export_journal(group_id: int, fmt: str, actor: Actor = Depends(read), db: Session = Depends(get_db)):
    group = group_access(db, actor, group_id)
    return download(OfficialDocument(
        kind="Журнал", title=f"занятий группы «{group.name}»", dated=date.today(),
        meta=[("Организация", require(db, Organization, group.organization_id).name),
              ("Этап", STAGES[group.stage]), ("Программа", group.program)],
        headers=["Дата", "Тема", "Минуты", "Спортсмен", "FSP ID", "Посещение", "Подтверждение"],
        rows=[[lesson["held_on"].isoformat(), lesson["topic"], lesson["duration_minutes"],
               a["full_name"], a["public_id"],
               {"present": "Присутствовал", "absent": "Отсутствовал", "unmarked": "Не отмечено"}[a["status"]],
               a["confirmed_at"].isoformat() if a["confirmed_at"] else "Не подтверждено"]
              for lesson in journal(db, actor, group) if lesson["status"] == "completed" for a in lesson["attendance"]],
    ), fmt, "training-journal")
