from datetime import date, time
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from typing import Literal
from pydantic import Field, HttpUrl, model_validator
from app.schemas import Strict


class GroupIn(Strict):
    organization_id: int
    discipline_id: int
    coach_id: int
    name: str = Field(min_length=2, max_length=160)
    stage: Literal["np", "ut", "ssm", "vsm"]
    program: str = Field(min_length=1, max_length=300)
    capacity: int = Field(20, ge=1, le=500)


class EnrollmentIn(Strict):
    athlete_public_id: str = Field(max_length=32)
    start_date: date
    order_number: str = Field(min_length=1, max_length=120)


class TransferIn(Strict):
    target_group_id: int
    on: date
    order_number: str = Field(min_length=1, max_length=120)


class EndIn(Strict):
    on: date
    order_number: str = Field(min_length=1, max_length=120)


class LessonIn(Strict):
    held_on: date
    topic: str = Field(min_length=2, max_length=500)
    duration_minutes: int = Field(ge=1, le=480)
    start_time: time | None = None
    timezone: str = Field("Asia/Yekaterinburg", max_length=80)
    format: Literal["onsite", "online", "hybrid", "correspondence"] = "onsite"
    location: str = Field("", max_length=500)
    meeting_url: HttpUrl | None = None
    instructions: str = Field("", max_length=6000)
    due_on: date | None = None

    @model_validator(mode="after")
    def schedule_details(self):
        try:
            ZoneInfo(self.timezone)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError("Укажите действующий часовой пояс")
        if self.format == "correspondence":
            if self.start_time is not None or self.location or self.meeting_url:
                raise ValueError("Для заочного занятия укажите задание и срок вместо времени, адреса и видеоссылки")
            if self.due_on is None or self.due_on < self.held_on:
                raise ValueError("Срок заочного задания должен быть не раньше даты начала")
            if len(self.instructions.strip()) < 3:
                raise ValueError("Опишите задание для самостоятельной работы")
            return self
        if self.due_on is not None:
            raise ValueError("Срок выполнения используется для заочного формата")
        if self.start_time is not None:
            if self.start_time.tzinfo or self.start_time.second or self.start_time.microsecond:
                raise ValueError("Время начала указывается с точностью до минуты без смещения")
            if self.format in ("onsite", "hybrid") and not self.location:
                raise ValueError("Укажите адрес и кабинет для очного занятия")
            if self.format in ("online", "hybrid") and not self.meeting_url:
                raise ValueError("Укажите ссылку подключения для онлайн-занятия")
        elif self.held_on >= date.today():
            # Historical API clients can still import old journal entries.
            raise ValueError("Для сегодняшнего или будущего занятия укажите время начала")
        return self


class LessonCancelIn(Strict):
    reason: str = Field(min_length=3, max_length=1000)


class MaterialLinkIn(Strict):
    title: str = Field(min_length=1, max_length=200)
    url: HttpUrl = Field(max_length=2000)


class AttendanceIn(Strict):
    status: Literal["present", "absent", "unmarked"]
