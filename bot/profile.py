"""The user's own website profile, with an explicit field allowlist excluding RUSADA."""
from datetime import date
from sqlalchemy import select
from app.models import (
    Athlete, AthleteCoach, AthleteDiscipline, Coach, CoachDiscipline, Discipline,
    Judge, JudgeCategory, JudgeDiscipline, Organization, SportsRank,
)
from bot.schedule import roles_for


def display_date(value):
    return value.strftime("%d.%m.%Y") if value else "Не указано"


def profile_text(db, user, role, role_names):
    lines = ["Личный кабинет", f"Роль: {role_names[role]}", "", f"ФИО: {user.full_name}",
             f"Email: {user.email}", f"Дата рождения: {display_date(user.birth_date)}",
             "Пол: " + {"male": "Мужской", "female": "Женский"}.get(user.sex, "Не указан")]
    lines.append("Доступные роли: " + ", ".join(role_names[r] for r in sorted(roles_for(db, user.id))))
    athlete = db.scalar(select(Athlete).where(Athlete.user_id == user.id)) if role in ("athlete", "admin") else None
    if athlete:
        org = db.get(Organization, athlete.organization_id) if athlete.organization_id else None
        lines.extend(["", f"Муниципалитет: {athlete.municipality}",
                      f"Организация: {org.name if org else 'Без организации'}",
                      f"Этап подготовки: {athlete.training_stage or 'Не указан'}",
                      f"Согласие на обработку данных: {display_date(user.consent_at)} (версия {user.consent_version})"])
        if user.guardian_name:
            lines.extend([f"Законный представитель: {user.guardian_name}",
                          f"Согласие представителя: {display_date(user.guardian_consent_at)}"])
        lines.extend(["", "Дисциплины и годы занятий:"])
        enrollments = db.scalars(select(AthleteDiscipline).where(AthleteDiscipline.athlete_id == athlete.id)).all()
        for entry in enrollments:
            discipline = db.get(Discipline, entry.discipline_id)
            lines.append(f"• {discipline.short_name}: {entry.start_year} — {entry.end_year or 'по настоящее время'}")
        if not enrollments:
            lines.append("Не указаны")
        ranks = db.scalars(select(SportsRank).where(SportsRank.athlete_id == athlete.id,
                           SportsRank.expires_on >= date.today()).order_by(SportsRank.assigned_on.desc())).all()
        lines.extend(["", "Действующие разряды:"])
        for rank in ranks:
            discipline = db.get(Discipline, rank.discipline_id)
            lines.append(f"• {rank.name} · {discipline.short_name}, до {display_date(rank.expires_on)}")
        if not ranks:
            lines.append("Нет действующих разрядов")
        coaches = db.execute(select(Coach, AthleteCoach).join(AthleteCoach, AthleteCoach.coach_id == Coach.id).where(
            AthleteCoach.athlete_id == athlete.id, AthleteCoach.status == "active", Coach.archived_at.is_(None))).all()
        lines.extend(["", "Тренеры:"])
        for coach, relation in coaches:
            discipline = db.get(Discipline, relation.discipline_id)
            lines.append(f"• {coach.user.full_name} · {discipline.short_name}")
        if not coaches:
            lines.append("Нет активных привязок")
    elif role in ("coach", "judge"):
        model, enrollment_model, owner_column = (Coach, CoachDiscipline, CoachDiscipline.coach_id) if role == "coach" else (Judge, JudgeDiscipline, JudgeDiscipline.judge_id)
        card = db.scalar(select(model).where(model.user_id == user.id))
        if card:
            org = db.get(Organization, card.organization_id) if card.organization_id else None
            lines.extend(["", f"Муниципалитет: {card.municipality}", f"Организация: {org.name if org else 'Без организации'}",
                          f"Телефон: {card.phone or 'Не указан'}", f"Контактный email: {card.contact_email or 'Не указан'}",
                          f"Квалификация: {card.qualification or 'Не указана'}", f"Опыт с: {card.experience_since or 'Не указан'}"])
            disciplines = db.scalars(select(Discipline).join(enrollment_model, enrollment_model.discipline_id == Discipline.id).where(owner_column == card.id)).all()
            lines.append("Дисциплины: " + (", ".join(d.short_name for d in disciplines) or "Не указаны"))
            if card.about:
                lines.append("О себе: " + card.about[:500])
            if role == "judge":
                categories = db.scalars(select(JudgeCategory).where(JudgeCategory.judge_id == card.id,
                                       JudgeCategory.expires_on >= date.today())).all()
                lines.extend(["", "Действующие категории:"])
                lines.extend(f"• {c.name}, до {display_date(c.expires_on)}" for c in categories)
                if not categories:
                    lines.append("Нет действующих категорий")
    return "\n".join(lines)[:3900]
