from sqlalchemy import select
from app.models import TrainingMaterial

MAX_FILE_SIZE = 10 * 1024 * 1024
MAX_MATERIALS = 20


def material_view(material):
    # Binary content is never included in lesson/agenda JSON responses.
    return {key: getattr(material, key) for key in (
        "id", "lesson_id", "kind", "title", "url", "filename", "content_type",
        "size", "created_at", "removed_at",
    )}


def lesson_materials(db, lesson_id, include_removed=False):
    query = select(TrainingMaterial).where(TrainingMaterial.lesson_id == lesson_id)
    if not include_removed:
        query = query.where(TrainingMaterial.removed_at.is_(None))
    return [material_view(m) for m in db.scalars(query.order_by(TrainingMaterial.created_at, TrainingMaterial.id))]
