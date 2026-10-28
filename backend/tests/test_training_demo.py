from sqlalchemy import select
from app.models import TrainingGroup, TrainingLesson, LessonAttendance, TrainingMaterial
from app.training_demo import seed_training_demo


def test_training_demo_is_idempotent_and_waits_for_athlete_confirmation(env):
    _, factory, _, _ = env
    with factory() as db:
        group_id = seed_training_demo(db)
        db.commit()
        assert seed_training_demo(db) == group_id
        db.commit()
        assert len(db.scalars(select(TrainingGroup)).all()) == 1
        attendance = db.scalars(select(LessonAttendance)).one()
        assert attendance.status == "present"
        assert attendance.confirmed_at is None
        planned = db.scalars(select(TrainingLesson).where(TrainingLesson.status == "planned", TrainingLesson.format != "correspondence")).one()
        assert planned.start_time.hour == 18 and planned.location and planned.instructions
        assignment = db.scalars(select(TrainingLesson).where(TrainingLesson.format == "correspondence")).one()
        assert assignment.due_on and assignment.start_time is None
        assert len(db.scalars(select(TrainingMaterial).where(TrainingMaterial.lesson_id == assignment.id)).all()) == 2
