from pathlib import PurePosixPath
from urllib.parse import quote
from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from app.db import get_db
from app.models import Athlete, LessonAttendance, TrainingLesson, TrainingMaterial, now
from app.schemas.training import MaterialLinkIn
from app.security import Actor, allow
from app.services.common import own, require, audit
from app.services.training_materials import MAX_FILE_SIZE, MAX_MATERIALS, lesson_materials, material_view
from app.services.training_schedule import roster, lesson_notice
from app.routers.training import group_access

router = APIRouter(tags=["Материалы занятий"])
read = allow("admin", "coach", "athlete", "ministry")
write = allow("admin", "coach")

ZIP = (b"PK\x03\x04", b"PK\x05\x06")
BINARY_TYPES = {
    ".pdf": ("application/pdf", (b"%PDF-",)),
    ".docx": ("application/vnd.openxmlformats-officedocument.wordprocessingml.document", ZIP),
    ".xlsx": ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", ZIP),
    ".pptx": ("application/vnd.openxmlformats-officedocument.presentationml.presentation", ZIP),
    ".zip": ("application/zip", ZIP),
    ".png": ("image/png", (b"\x89PNG\r\n\x1a\n",)),
    ".jpg": ("image/jpeg", (b"\xff\xd8\xff",)),
    ".jpeg": ("image/jpeg", (b"\xff\xd8\xff",)),
}
TEXT_EXTENSIONS = {".txt", ".md", ".csv", ".json", ".py", ".cpp", ".c", ".h", ".hpp", ".java", ".js", ".ts", ".sql", ".ipynb", ".css", ".html"}


def access(db, actor, lesson_id, writing=False):
    lesson = require(db, TrainingLesson, lesson_id)
    group_access(db, actor, lesson.group_id, writing)
    if actor.role == "athlete":
        athlete = own(db, Athlete, actor)
        if athlete.id not in roster(db, lesson.group_id, lesson.held_on) and not db.scalar(select(LessonAttendance.id).where(
            LessonAttendance.lesson_id == lesson.id, LessonAttendance.athlete_id == athlete.id,
        )):
            raise HTTPException(403, "Материалы вне вашего периода обучения недоступны")
    if writing and lesson.status == "cancelled":
        raise HTTPException(409, "Материалы отменённого занятия доступны только для чтения")
    return lesson


def capacity(db, lesson_id):
    count = db.scalar(select(func.count()).select_from(TrainingMaterial).where(
        TrainingMaterial.lesson_id == lesson_id, TrainingMaterial.removed_at.is_(None),
    ))
    if count >= MAX_MATERIALS:
        raise HTTPException(409, f"К занятию можно добавить до {MAX_MATERIALS} материалов")


def changed(db, actor, lesson, material, action):
    audit(db, actor, action, material, {"lesson_id": lesson.id, "title": material.title, "kind": material.kind})
    lesson_notice(db, lesson, "Обновлены материалы к занятию", f"materials-{material.id}-{now().isoformat()}")


@router.get("/training-lessons/{lesson_id}/materials")
def materials(lesson_id: int, include_removed: bool = False, actor: Actor = Depends(read), db: Session = Depends(get_db)):
    access(db, actor, lesson_id)
    if include_removed and actor.role not in ("admin", "coach"):
        raise HTTPException(403, "История удалённых материалов доступна тренеру и федерации")
    return lesson_materials(db, lesson_id, include_removed)


@router.post("/training-lessons/{lesson_id}/materials/links", status_code=201)
def add_link(lesson_id: int, data: MaterialLinkIn, actor: Actor = Depends(write), db: Session = Depends(get_db)):
    lesson = access(db, actor, lesson_id, True)
    capacity(db, lesson_id)
    material = TrainingMaterial(lesson_id=lesson_id, kind="link", title=data.title, url=str(data.url), created_by=actor.user.id)
    db.add(material)
    changed(db, actor, lesson, material, "Ссылка к занятию")
    return material_view(material)


@router.post("/training-lessons/{lesson_id}/materials/files", status_code=201)
async def add_file(lesson_id: int, file: UploadFile = File(...), title: str = Form("", max_length=200),
                   actor: Actor = Depends(write), db: Session = Depends(get_db)):
    lesson = access(db, actor, lesson_id, True)
    capacity(db, lesson_id)
    filename = PurePosixPath((file.filename or "").replace("\\", "/")).name
    filename = "".join(c for c in filename if ord(c) >= 32 and ord(c) != 127).strip()
    if not filename or len(filename) > 255:
        raise HTTPException(422, "Имя файла должно содержать от 1 до 255 символов")
    ext = PurePosixPath(filename).suffix.lower()
    if ext not in BINARY_TYPES and ext not in TEXT_EXTENSIONS:
        raise HTTPException(422, "Допустимы PDF, DOCX, XLSX, PPTX, ZIP, PNG, JPG, текст и исходный код")
    content = await file.read(MAX_FILE_SIZE + 1)
    if not content:
        raise HTTPException(422, "Файл пустой")
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(413, "Размер файла не должен превышать 10 МБ")
    if ext in BINARY_TYPES:
        mime, signatures = BINARY_TYPES[ext]
        if not content.startswith(signatures):
            raise HTTPException(422, "Содержимое файла не соответствует расширению")
    else:
        try:
            content.decode("utf-8-sig")
        except UnicodeDecodeError:
            raise HTTPException(422, "Текстовые файлы и исходный код должны быть в UTF-8")
        mime = "text/plain; charset=utf-8"
    material = TrainingMaterial(lesson_id=lesson_id, kind="file", title=title.strip() or filename[:200],
                                filename=filename, content_type=mime, size=len(content), data=content, created_by=actor.user.id)
    db.add(material)
    changed(db, actor, lesson, material, "Файл к занятию")
    return material_view(material)


@router.get("/training-materials/{material_id}/download")
def download_material(material_id: int, actor: Actor = Depends(read), db: Session = Depends(get_db)):
    material = require(db, TrainingMaterial, material_id)
    access(db, actor, material.lesson_id)
    if material.removed_at or material.kind != "file":
        raise HTTPException(404, "Файл недоступен")
    suffix = PurePosixPath(material.filename).suffix.lower()
    return Response(material.data, media_type=material.content_type, headers={
        "Content-Disposition": f"attachment; filename=\"lesson-material-{material.id}{suffix}\"; filename*=UTF-8''{quote(material.filename, safe='')}",
        "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff",
    })


@router.delete("/training-materials/{material_id}", status_code=204)
def remove_material(material_id: int, actor: Actor = Depends(write), db: Session = Depends(get_db)):
    material = require(db, TrainingMaterial, material_id)
    lesson = access(db, actor, material.lesson_id, True)
    if material.removed_at is None:
        material.removed_at = now()
        changed(db, actor, lesson, material, "Удаление материала занятия")


@router.post("/training-materials/{material_id}/restore")
def restore_material(material_id: int, actor: Actor = Depends(write), db: Session = Depends(get_db)):
    material = require(db, TrainingMaterial, material_id)
    lesson = access(db, actor, material.lesson_id, True)
    if material.removed_at:
        capacity(db, lesson.id)
        material.removed_at = None
        changed(db, actor, lesson, material, "Восстановление материала занятия")
    return material_view(material)
