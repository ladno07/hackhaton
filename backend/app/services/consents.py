"""Extracts from recorded registration consents, never signed-form substitutes."""

from fastapi import HTTPException
from app.config import settings
from app.services.documents import OfficialDocument, export_document

CONSENT_TEXTS = {
    "2026-01": {
        "personal": "Я согласен на обработку данных профиля, заявок и результатов "
        "Федерацией для ведения спортивного учёта (версия 2026-01).",
        "guardian": "Законный представитель согласен на обработку данных несовершеннолетнего.",
    }
}


def consent_records(user):
    records = []
    for kind, accepted_at in [
        ("personal", user.consent_at),
        ("guardian", user.guardian_consent_at),
    ]:
        if not accepted_at:
            continue
        records.append({
            "id": kind,
            "title": "Согласие на обработку персональных данных"
            if kind == "personal" else "Согласие законного представителя",
            "version": user.consent_version,
            "accepted_at": accepted_at,
            "subject_name": user.full_name,
            "birth_date": user.birth_date,
            "accepted_by": user.full_name if kind == "personal" else user.guardian_name,
            "text": CONSENT_TEXTS.get(user.consent_version, {}).get(kind),
            "operator": settings.fsp_name,
            "note": "Выписка из сохранённой записи согласия: версия и дата принятия. "
            "ФИО и дата рождения приведены по текущей учётной записи. "
            "Согласие зафиксировано отметкой при регистрации; выписка не является "
            "сканом подписанного бланка и не содержит электронной подписи.",
        })
    return records


def consent_record(user, kind):
    record = next((r for r in consent_records(user) if r["id"] == kind), None)
    if record is None:
        raise HTTPException(404, "Запись согласия не найдена")
    return record


def consent_pdf(record):
    doc = OfficialDocument(
        kind="Выписка",
        title="из записи согласия на обработку персональных данных",
        headers=["Сведения", "Значение"],
        rows=[
            ["Вид согласия", record["title"]],
            ["Версия", record["version"]],
            ["Дата и время принятия (UTC)", record["accepted_at"].strftime("%d.%m.%Y %H:%M:%S")],
            ["Спортсмен / пользователь", record["subject_name"]],
            ["Дата рождения", record["birth_date"].strftime("%d.%m.%Y")],
            ["Кем принято", record["accepted_by"] or "Не указано"],
            ["Оператор", record["operator"]],
        ],
        dated=record["accepted_at"].date(),
        intro=[record["text"] or "Текст этой версии согласия в системе не сохранён. "
               "Доступны только сведения о факте принятия."],
        outro=[record["note"]],
    )
    return export_document(doc, "pdf")
