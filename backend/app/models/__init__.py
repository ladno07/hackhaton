from datetime import date, datetime, time, timezone
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    text,
    Integer,
    JSON,
    LargeBinary,
    String,
    Text,
    Time,
    BigInteger,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, declared_attr, mapped_column, relationship
from app.db import Base


def now():
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"
    __table_args__ = (CheckConstraint("sex IS NULL OR sex IN ('male','female')"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(Text)
    full_name: Mapped[str] = mapped_column(String(200))
    birth_date: Mapped[date] = mapped_column(Date)
    sex: Mapped[str | None] = mapped_column(String(10))
    consent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    consent_version: Mapped[str] = mapped_column(String(30), default="2026-01")
    guardian_name: Mapped[str | None] = mapped_column(String(200))
    guardian_consent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    # Stable order: the first role is the default cabinet after login, and
    # admin < athlete < coach < judge < ministry keeps read-only ministry last.
    roles: Mapped[list["Role"]] = relationship(
        secondary="user_roles", lazy="selectin", order_by="Role.id"
    )


class Role(Base):
    __tablename__ = "roles"
    id: Mapped[str] = mapped_column(String(20), primary_key=True)
    name: Mapped[str] = mapped_column(String(100))


class UserRole(Base):
    __tablename__ = "user_roles"
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    role_id: Mapped[str] = mapped_column(ForeignKey("roles.id"), primary_key=True)


class Organization(Base):
    __tablename__ = "organizations"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), unique=True)
    kind: Mapped[str] = mapped_column(String(80), default="Клуб")
    municipality: Mapped[str] = mapped_column(String(120))
    license_number: Mapped[str | None] = mapped_column(String(160))
    license_valid_until: Mapped[date | None] = mapped_column(Date)
    programs: Mapped[list] = mapped_column(JSON, default=list)


class TrainingGroup(Base):
    __tablename__ = "training_groups"
    __table_args__ = (
        UniqueConstraint("organization_id", "name"),
        CheckConstraint("stage IN ('np','ut','ssm','vsm')"),
        CheckConstraint("capacity > 0"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"))
    discipline_id: Mapped[int] = mapped_column(ForeignKey("disciplines.id"))
    coach_id: Mapped[int] = mapped_column(ForeignKey("coaches.id"))
    name: Mapped[str] = mapped_column(String(160))
    stage: Mapped[str] = mapped_column(String(10))
    program: Mapped[str] = mapped_column(String(300))
    capacity: Mapped[int] = mapped_column(Integer, default=20)
    archived: Mapped[bool] = mapped_column(Boolean, default=False)


class GroupEnrollment(Base):
    __tablename__ = "group_enrollments"
    __table_args__ = (CheckConstraint("end_date IS NULL OR end_date >= start_date"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("training_groups.id"), index=True)
    athlete_id: Mapped[int] = mapped_column(ForeignKey("athletes.id"), index=True)
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    order_number: Mapped[str] = mapped_column(String(120))
    end_order_number: Mapped[str | None] = mapped_column(String(120))
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))


class TrainingLesson(Base):
    __tablename__ = "training_lessons"
    __table_args__ = (CheckConstraint("duration_minutes > 0"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("training_groups.id"), index=True)
    held_on: Mapped[date] = mapped_column(Date)
    topic: Mapped[str] = mapped_column(String(500))
    duration_minutes: Mapped[int] = mapped_column(Integer)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    start_time: Mapped[time | None] = mapped_column(Time)
    timezone: Mapped[str] = mapped_column(String(80), default="Asia/Yekaterinburg")
    format: Mapped[str] = mapped_column(String(20), default="onsite")
    location: Mapped[str] = mapped_column(String(500), default="")
    meeting_url: Mapped[str | None] = mapped_column(String(2000))
    instructions: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="completed")
    cancellation_reason: Mapped[str | None] = mapped_column(String(1000))
    revision: Mapped[int] = mapped_column(Integer, default=1)
    due_on: Mapped[date | None] = mapped_column(Date)


class TrainingMaterial(Base):
    __tablename__ = "training_materials"
    __table_args__ = (
        CheckConstraint("kind IN ('file','link')"),
        CheckConstraint("(kind = 'file' AND data IS NOT NULL AND url IS NULL AND filename IS NOT NULL AND size > 0) OR (kind = 'link' AND url IS NOT NULL AND data IS NULL AND filename IS NULL)"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    lesson_id: Mapped[int] = mapped_column(ForeignKey("training_lessons.id"), index=True)
    kind: Mapped[str] = mapped_column(String(10))
    title: Mapped[str] = mapped_column(String(200))
    url: Mapped[str | None] = mapped_column(String(2000))
    filename: Mapped[str | None] = mapped_column(String(255))
    content_type: Mapped[str | None] = mapped_column(String(120))
    size: Mapped[int | None] = mapped_column(Integer)
    data: Mapped[bytes | None] = mapped_column(LargeBinary, deferred=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    removed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class LessonAttendance(Base):
    __tablename__ = "lesson_attendance"
    __table_args__ = (
        UniqueConstraint("lesson_id", "athlete_id"),
        CheckConstraint("status IN ('unmarked','present','absent')"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    lesson_id: Mapped[int] = mapped_column(ForeignKey("training_lessons.id"), index=True)
    athlete_id: Mapped[int] = mapped_column(ForeignKey("athletes.id"), index=True)
    status: Mapped[str] = mapped_column(String(20), default="unmarked")
    marked_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    dispute_reason: Mapped[str | None] = mapped_column(String(1000))


class Discipline(Base):
    __tablename__ = "disciplines"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(150), unique=True)
    short_name: Mapped[str] = mapped_column(String(60))


class Athlete(Base):
    __tablename__ = "athletes"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True)
    organization_id: Mapped[int | None] = mapped_column(ForeignKey("organizations.id"))
    municipality: Mapped[str] = mapped_column(String(120), default="Оренбург")
    training_stage: Mapped[str | None] = mapped_column(String(120))
    rusada_date: Mapped[date | None] = mapped_column(Date)
    rusada_certificate: Mapped[str | None] = mapped_column(Text)
    suspended_until: Mapped[date | None] = mapped_column(Date)
    suspension_reason: Mapped[str | None] = mapped_column(Text)
    user: Mapped[User] = relationship(lazy="joined")


class AthleteDiscipline(Base):
    __tablename__ = "athlete_disciplines"
    __table_args__ = (CheckConstraint("end_year IS NULL OR end_year >= start_year"),)
    athlete_id: Mapped[int] = mapped_column(ForeignKey("athletes.id"), primary_key=True)
    discipline_id: Mapped[int] = mapped_column(
        ForeignKey("disciplines.id"), primary_key=True
    )
    start_year: Mapped[int] = mapped_column(Integer)
    end_year: Mapped[int | None] = mapped_column(Integer)


class AthleteOrganization(Base):
    """Membership period; end_date is inclusive, NULL means the current one."""

    __tablename__ = "athlete_organizations"
    __table_args__ = (CheckConstraint("end_date IS NULL OR end_date >= start_date"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    athlete_id: Mapped[int] = mapped_column(ForeignKey("athletes.id"), index=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"))
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)


class StaffCard:
    """Card of a coach or a judge; an archived card keeps its history."""

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True)
    organization_id: Mapped[int | None] = mapped_column(ForeignKey("organizations.id"))
    municipality: Mapped[str] = mapped_column(String(120), default="Оренбург")
    phone: Mapped[str | None] = mapped_column(String(30))
    contact_email: Mapped[str | None] = mapped_column(String(254))
    qualification: Mapped[str | None] = mapped_column(String(200))
    experience_since: Mapped[int | None] = mapped_column(Integer)
    about: Mapped[str | None] = mapped_column(Text)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    archive_reason: Mapped[str | None] = mapped_column(Text)

    @declared_attr
    def user(cls) -> Mapped[User]:
        return relationship(lazy="joined")


class Coach(StaffCard, Base):
    __tablename__ = "coaches"


class Judge(StaffCard, Base):
    __tablename__ = "judges"


class CoachDiscipline(Base):
    __tablename__ = "coach_disciplines"
    coach_id: Mapped[int] = mapped_column(ForeignKey("coaches.id"), primary_key=True)
    discipline_id: Mapped[int] = mapped_column(
        ForeignKey("disciplines.id"), primary_key=True
    )


class JudgeDiscipline(Base):
    __tablename__ = "judge_disciplines"
    judge_id: Mapped[int] = mapped_column(ForeignKey("judges.id"), primary_key=True)
    discipline_id: Mapped[int] = mapped_column(
        ForeignKey("disciplines.id"), primary_key=True
    )


class AthleteCoach(Base):
    __tablename__ = "athlete_coaches"
    __table_args__ = (
        UniqueConstraint("athlete_id", "coach_id", "discipline_id"),
        CheckConstraint("status IN ('pending','active','paused','ended')"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    athlete_id: Mapped[int] = mapped_column(ForeignKey("athletes.id"))
    coach_id: Mapped[int] = mapped_column(ForeignKey("coaches.id"))
    discipline_id: Mapped[int] = mapped_column(ForeignKey("disciplines.id"))
    status: Mapped[str] = mapped_column(String(20), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class CoachChatMessage(Base):
    __tablename__ = "coach_chat_messages"
    id: Mapped[int] = mapped_column(primary_key=True)
    link_id: Mapped[int] = mapped_column(ForeignKey("athlete_coaches.id"), index=True)
    sender_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    sender_role: Mapped[str] = mapped_column(String(20))
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class LinkHistory(Base):
    __tablename__ = "link_history"
    id: Mapped[int] = mapped_column(primary_key=True)
    link_id: Mapped[int] = mapped_column(ForeignKey("athlete_coaches.id"))
    actor_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    status: Mapped[str] = mapped_column(String(20))
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class CompetitionType(Base):
    """rating_class: main (чемпионат, кубок), junior (первенство), other."""

    __tablename__ = "competition_types"
    __table_args__ = (CheckConstraint("rating_class IN ('main','junior','other')"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    rating_class: Mapped[str] = mapped_column(String(20), default="other")


class Competition(Base):
    __tablename__ = "competitions"
    __table_args__ = (
        CheckConstraint("end_date >= start_date"),
        CheckConstraint("min_age <= max_age"),
        CheckConstraint(
            "entry_mode IN ('individual','team')", name="ck_comp_entry_mode"
        ),
        CheckConstraint(
            "team_min >= 1 AND team_max >= team_min AND team_max <= 50",
            name="ck_comp_team_size",
        ),
        CheckConstraint("state IN ('draft','open','closed','published')"),
        CheckConstraint("status IN ('regional','interregional','national')"),
        CheckConstraint(
            "rating_level IN ('regional','interregional','russian_championship','russian_junior')"
        ),
        CheckConstraint("format IN ('onsite','online','hybrid')"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(240))
    discipline_id: Mapped[int] = mapped_column(ForeignKey("disciplines.id"))
    type_id: Mapped[int] = mapped_column(ForeignKey("competition_types.id"))
    start_date: Mapped[date] = mapped_column(Date)
    start_time: Mapped[time | None] = mapped_column(Time)
    timezone: Mapped[str] = mapped_column(String(80), default="Asia/Yekaterinburg", server_default="Asia/Yekaterinburg")
    end_date: Mapped[date] = mapped_column(Date)
    deadline: Mapped[date] = mapped_column(Date)
    location: Mapped[str] = mapped_column(String(200))
    format: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20))
    # derived from status + type, see services.ratings.rating_level
    rating_level: Mapped[str] = mapped_column(String(40))
    min_age: Mapped[int] = mapped_column(Integer, default=0)
    max_age: Mapped[int] = mapped_column(Integer, default=100)
    calendar_plan: Mapped[str] = mapped_column(String(100))
    calendar_number: Mapped[str] = mapped_column(String(80))
    regulation_url: Mapped[str | None] = mapped_column(Text)
    state: Mapped[str] = mapped_column(String(20), default="draft")
    revision: Mapped[int] = mapped_column(Integer, default=0)
    entry_mode: Mapped[str] = mapped_column(
        String(20), default="individual", server_default="individual"
    )
    team_min: Mapped[int] = mapped_column(Integer, default=2, server_default="2")
    team_max: Mapped[int] = mapped_column(Integer, default=3, server_default="3")
    team_rating: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false")
    )


class AgeGroup(Base):
    """Age group from the sport's rules; discipline_id NULL means all disciplines."""

    __tablename__ = "age_groups"
    __table_args__ = (
        CheckConstraint("min_age <= max_age"),
        CheckConstraint("sex IS NULL OR sex IN ('male','female')"),
        CheckConstraint("age_rule IN ('year','start')"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    discipline_id: Mapped[int | None] = mapped_column(ForeignKey("disciplines.id"))
    sex: Mapped[str | None] = mapped_column(String(10))
    min_age: Mapped[int] = mapped_column(Integer)
    max_age: Mapped[int] = mapped_column(Integer)
    # year: age reached in the calendar year of the start; start: age on start date
    age_rule: Mapped[str] = mapped_column(String(10), default="year")
    sort_order: Mapped[int] = mapped_column(Integer, default=0)


class CompetitionAgeGroup(Base):
    __tablename__ = "competition_age_groups"
    competition_id: Mapped[int] = mapped_column(
        ForeignKey("competitions.id", ondelete="CASCADE"), primary_key=True
    )
    age_group_id: Mapped[int] = mapped_column(
        ForeignKey("age_groups.id"), primary_key=True
    )


class CompetitionRegulation(Base):
    __tablename__ = "competition_regulations"
    competition_id: Mapped[int] = mapped_column(
        ForeignKey("competitions.id", ondelete="CASCADE"), primary_key=True
    )
    filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(120))
    size: Mapped[int] = mapped_column(Integer)
    data: Mapped[bytes] = mapped_column(LargeBinary, deferred=True)
    uploaded_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class CompetitionApplication(Base):
    __tablename__ = "competition_applications"
    __table_args__ = (
        UniqueConstraint("competition_id", "athlete_id"),
        CheckConstraint("status IN ('pending','approved','rejected')"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    competition_id: Mapped[int] = mapped_column(ForeignKey("competitions.id"))
    athlete_id: Mapped[int] = mapped_column(ForeignKey("athletes.id"))
    age_group_id: Mapped[int | None] = mapped_column(ForeignKey("age_groups.id"))
    submitted_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    status: Mapped[str] = mapped_column(String(20), default="pending")
    comment: Mapped[str | None] = mapped_column(Text)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class CompetitionJudge(Base):
    __tablename__ = "competition_judges"
    competition_id: Mapped[int] = mapped_column(
        ForeignKey("competitions.id"), primary_key=True
    )
    judge_id: Mapped[int] = mapped_column(ForeignKey("judges.id"), primary_key=True)
    position: Mapped[str] = mapped_column(String(120))


class CompetitionResult(Base):
    """Places may be shared ("1, 1, 3"); team members share place and score."""

    __tablename__ = "competition_results"
    __table_args__ = (
        UniqueConstraint("competition_id", "athlete_id"),
        CheckConstraint("place > 0"),
        CheckConstraint("score >= 0"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    competition_id: Mapped[int] = mapped_column(ForeignKey("competitions.id"))
    athlete_id: Mapped[int] = mapped_column(ForeignKey("athletes.id"))
    place: Mapped[int] = mapped_column(Integer)
    score: Mapped[float] = mapped_column(Float)
    team_name: Mapped[str | None] = mapped_column(String(120))


class ProtocolVersion(Base):
    """Snapshot of a published protocol; version 1 is the first publication."""

    __tablename__ = "protocol_versions"
    __table_args__ = (UniqueConstraint("competition_id", "version"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    competition_id: Mapped[int] = mapped_column(ForeignKey("competitions.id"))
    version: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    reason: Mapped[str] = mapped_column(Text)
    entries: Mapped[list] = mapped_column(JSON)


class SportsRank(Base):
    __tablename__ = "sports_ranks"
    id: Mapped[int] = mapped_column(primary_key=True)
    athlete_id: Mapped[int] = mapped_column(ForeignKey("athletes.id"))
    discipline_id: Mapped[int] = mapped_column(ForeignKey("disciplines.id"))
    name: Mapped[str] = mapped_column(String(100))
    assigned_on: Mapped[date] = mapped_column(Date)
    expires_on: Mapped[date] = mapped_column(Date)
    order_number: Mapped[str] = mapped_column(String(120))
    result_id: Mapped[int] = mapped_column(ForeignKey("competition_results.id"))


class JudgeCategory(Base):
    __tablename__ = "judge_categories"
    id: Mapped[int] = mapped_column(primary_key=True)
    judge_id: Mapped[int] = mapped_column(ForeignKey("judges.id"))
    name: Mapped[str] = mapped_column(String(100))
    assigned_on: Mapped[date] = mapped_column(Date)
    expires_on: Mapped[date] = mapped_column(Date)
    order_number: Mapped[str] = mapped_column(String(120))


class RankApplication(Base):
    __tablename__ = "rank_applications"
    __table_args__ = (
        CheckConstraint(
            "(athlete_id IS NOT NULL AND judge_id IS NULL AND result_id IS NOT NULL) OR (judge_id IS NOT NULL AND athlete_id IS NULL AND result_id IS NULL)"
        ),
        CheckConstraint("status IN ('pending','approved','rejected')"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    athlete_id: Mapped[int | None] = mapped_column(ForeignKey("athletes.id"))
    judge_id: Mapped[int | None] = mapped_column(ForeignKey("judges.id"))
    result_id: Mapped[int | None] = mapped_column(ForeignKey("competition_results.id"))
    submitted_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    name: Mapped[str] = mapped_column(String(100))
    kind: Mapped[str] = mapped_column(String(30), default="assignment")
    status: Mapped[str] = mapped_column(String(20), default="pending")
    comment: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class RatingRule(Base):
    __tablename__ = "rating_rules"
    level: Mapped[str] = mapped_column(String(40), primary_key=True)
    first: Mapped[int] = mapped_column(Integer)
    second: Mapped[int] = mapped_column(Integer)
    third: Mapped[int] = mapped_column(Integer)


class Rating(Base):
    __tablename__ = "ratings"
    __table_args__ = (UniqueConstraint("athlete_id", "discipline_id", "season"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    athlete_id: Mapped[int] = mapped_column(ForeignKey("athletes.id"))
    discipline_id: Mapped[int] = mapped_column(ForeignKey("disciplines.id"))
    season: Mapped[int] = mapped_column(Integer)
    points: Mapped[float] = mapped_column(Float)
    coefficient: Mapped[float] = mapped_column(Float)
    breakdown: Mapped[list] = mapped_column(JSON)


class TeamMember(Base):
    __tablename__ = "team_members"
    season: Mapped[int] = mapped_column(Integer, primary_key=True)
    discipline_id: Mapped[int] = mapped_column(
        ForeignKey("disciplines.id"), primary_key=True
    )
    athlete_id: Mapped[int] = mapped_column(ForeignKey("athletes.id"), primary_key=True)
    selected_by: Mapped[int] = mapped_column(ForeignKey("users.id"))


class EvskRule(Base):
    __tablename__ = "evsk_rules"
    id: Mapped[int] = mapped_column(primary_key=True)
    discipline_id: Mapped[int] = mapped_column(ForeignKey("disciplines.id"))
    level: Mapped[str] = mapped_column(String(40))
    rank_name: Mapped[str] = mapped_column(String(100))
    max_place: Mapped[int] = mapped_column(Integer)
    min_participants: Mapped[int] = mapped_column(Integer)
    source: Mapped[str] = mapped_column(Text)


class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (UniqueConstraint("user_id", "event_key"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String(240))
    body: Mapped[str] = mapped_column(Text)
    event_key: Mapped[str] = mapped_column(String(240))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    mailed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(Text)
    telegram_context: Mapped[dict | None] = mapped_column(JSON)


class TelegramLink(Base):
    __tablename__ = "telegram_links"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True)
    chat_id: Mapped[int | None] = mapped_column(BigInteger, unique=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    role: Mapped[str] = mapped_column(String(20), default="athlete")
    connected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    baseline_id: Mapped[int] = mapped_column(Integer, default=0)
    blocked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class TelegramLinkToken(Base):
    __tablename__ = "telegram_link_tokens"
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    chat_id: Mapped[int | None] = mapped_column(BigInteger)


class TelegramDelivery(Base):
    __tablename__ = "telegram_deliveries"
    __table_args__ = (UniqueConstraint("link_id", "notification_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    link_id: Mapped[int] = mapped_column(ForeignKey("telegram_links.id"))
    notification_id: Mapped[int] = mapped_column(ForeignKey("notifications.id"))
    status: Mapped[str] = mapped_column(String(20), default="pending")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)


class TelegramCodeAttempt(Base):
    __tablename__ = "telegram_code_attempts"
    chat_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    window_started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class TelegramCursor(Base):
    __tablename__ = "telegram_cursor"
    id: Mapped[int] = mapped_column(primary_key=True)
    update_id: Mapped[int] = mapped_column(BigInteger, default=-1)
    send_after: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    active_role: Mapped[str] = mapped_column(String(20))
    action: Mapped[str] = mapped_column(String(120))
    entity: Mapped[str] = mapped_column(String(100))
    entity_id: Mapped[str] = mapped_column(String(100))
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Deadline(Base):
    __tablename__ = "deadlines"
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(240))
    due_on: Mapped[date] = mapped_column(Date)
    done: Mapped[bool] = mapped_column(Boolean, default=False)


class CompetitionTeam(Base):
    __tablename__ = "competition_teams"
    __table_args__ = (
        UniqueConstraint("id", "competition_id"),
        UniqueConstraint("competition_id", "name"),
        CheckConstraint(
            "status IN ('draft','pending','approved','returned','cancelled')"
        ),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    competition_id: Mapped[int] = mapped_column(ForeignKey("competitions.id"))
    name: Mapped[str] = mapped_column(String(120))
    captain_id: Mapped[int] = mapped_column(ForeignKey("athletes.id"))
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    status: Mapped[str] = mapped_column(String(20), default="draft")
    comment: Mapped[str] = mapped_column(Text, default="")
    revision: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class CompetitionTeamMember(Base):
    __tablename__ = "competition_team_members"
    __table_args__ = (
        ForeignKeyConstraint(
            ["team_id", "competition_id"],
            ["competition_teams.id", "competition_teams.competition_id"],
        ),
        UniqueConstraint("team_id", "athlete_id"),
        CheckConstraint("status IN ('invited','accepted','declined')"),
        Index(
            "uq_team_accepted_athlete",
            "competition_id",
            "athlete_id",
            unique=True,
            postgresql_where=text("status = 'accepted'"),
            sqlite_where=text("status = 'accepted'"),
        ),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    team_id: Mapped[int] = mapped_column(Integer)
    competition_id: Mapped[int] = mapped_column(Integer)
    athlete_id: Mapped[int] = mapped_column(ForeignKey("athletes.id"))
    status: Mapped[str] = mapped_column(String(20), default="invited")
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PassportPublication(Base):
    __tablename__ = "passport_publications"
    athlete_id: Mapped[int] = mapped_column(ForeignKey("athletes.id"), primary_key=True)
    slug: Mapped[str | None] = mapped_column(String(64), unique=True)
    enabled: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false")
    )
    show_results: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("true")
    )
    show_rating: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("true")
    )
    show_team: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("true")
    )
    show_rusada: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false")
    )
    show_ranks: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("true")
    )
    show_disciplines: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("true")
    )
    show_organization: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("true")
    )
    show_municipality: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("true")
    )
    show_training_stage: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false")
    )
    show_training_years: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false")
    )
    consent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    consent_version: Mapped[str | None] = mapped_column(String(30))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class PassportGuardianConsent(Base):
    __tablename__ = "passport_guardian_consents"
    __table_args__ = (CheckConstraint("status IN ('pending','approved','rejected')"),)
    athlete_id: Mapped[int] = mapped_column(ForeignKey("athletes.id"), primary_key=True)
    guardian_name: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(20), default="pending")
    filename: Mapped[str] = mapped_column(String(255))
    document: Mapped[bytes] = mapped_column(LargeBinary)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reviewed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    comment: Mapped[str] = mapped_column(Text, default="")


class PublicProtocolProof(Base):
    __tablename__ = "public_protocol_proofs"
    __table_args__ = (UniqueConstraint("publication_slug", "protocol_version_id"),)
    digest: Mapped[str] = mapped_column(String(64), primary_key=True)
    athlete_id: Mapped[int] = mapped_column(ForeignKey("athletes.id"))
    protocol_version_id: Mapped[int] = mapped_column(ForeignKey("protocol_versions.id"))
    publication_slug: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class LoginSession(Base):
    __tablename__ = "login_sessions"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class DevelopmentIndicator(Base):
    """Indicator value entered by the federation; the source is mandatory,
    documents confirm it (statistical forms, reports of organizations)."""

    __tablename__ = "development_indicators"
    id: Mapped[int] = mapped_column(primary_key=True)
    year: Mapped[int] = mapped_column(Integer, index=True)
    name: Mapped[str] = mapped_column(String(240))
    value: Mapped[float] = mapped_column(Float)
    unit: Mapped[str] = mapped_column(String(40))
    organization_id: Mapped[int | None] = mapped_column(ForeignKey("organizations.id"))
    source: Mapped[str] = mapped_column(Text)
    comment: Mapped[str] = mapped_column(Text, default="")
    updated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    documents: Mapped[list["IndicatorDocument"]] = relationship(
        order_by="IndicatorDocument.id",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class IndicatorDocument(Base):
    __tablename__ = "indicator_documents"
    id: Mapped[int] = mapped_column(primary_key=True)
    indicator_id: Mapped[int] = mapped_column(
        ForeignKey("development_indicators.id", ondelete="CASCADE"), index=True
    )
    filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(120))
    size: Mapped[int] = mapped_column(Integer)
    data: Mapped[bytes] = mapped_column(LargeBinary, deferred=True)
    uploaded_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=now
    )


class GovernorAwardRule(Base):
    """Prize amount in rubles for a place at a competition of the rating level;
    0 means the place does not make an athlete a candidate."""

    __tablename__ = "governor_award_rules"
    level: Mapped[str] = mapped_column(String(40), primary_key=True)
    first: Mapped[int] = mapped_column(Integer)
    second: Mapped[int] = mapped_column(Integer)
    third: Mapped[int] = mapped_column(Integer)


class GovernorAward(Base):
    """Decision on a candidate for the year's achievements. A candidate without
    a record has not been put forward yet; amount and basis are fixed when the
    federation includes the athlete in the petition."""

    __tablename__ = "governor_awards"
    __table_args__ = (
        UniqueConstraint("year", "athlete_id"),
        CheckConstraint(
            "status IN ('nominated','awarded','rejected')",
            name="ck_governor_award_status",
        ),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    year: Mapped[int] = mapped_column(Integer, index=True)
    athlete_id: Mapped[int] = mapped_column(ForeignKey("athletes.id"))
    status: Mapped[str] = mapped_column(String(20))
    amount: Mapped[int] = mapped_column(Integer)
    basis: Mapped[dict] = mapped_column(JSON)
    comment: Mapped[str] = mapped_column(Text, default="")
    order_number: Mapped[str | None] = mapped_column(String(120))
    updated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Violation(Base):
    """Violation recorded by the federation. A suspension sanction moves
    athletes.suspended_until; cancelling it restores the remaining one."""

    __tablename__ = "violations"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('rules','conduct','doping','other')", name="ck_violation_kind"
        ),
        CheckConstraint(
            "(sanction = 'warning' AND suspended_until IS NULL) OR "
            "(sanction = 'suspension' AND suspended_until IS NOT NULL)",
            name="ck_violation_sanction",
        ),
        CheckConstraint(
            "status IN ('active','cancelled')", name="ck_violation_status"
        ),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    athlete_id: Mapped[int] = mapped_column(ForeignKey("athletes.id"), index=True)
    competition_id: Mapped[int | None] = mapped_column(ForeignKey("competitions.id"))
    kind: Mapped[str] = mapped_column(String(20))
    occurred_on: Mapped[date] = mapped_column(Date)
    description: Mapped[str] = mapped_column(Text)
    sanction: Mapped[str] = mapped_column(String(20))
    suspended_until: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20), default="active")
    cancel_reason: Mapped[str | None] = mapped_column(Text)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Appeal(Base):
    """Appeal against a protocol line or a violation. An upheld result appeal
    may produce a protocol version; an upheld violation appeal cancels it."""

    __tablename__ = "appeals"
    __table_args__ = (
        CheckConstraint(
            "(subject = 'result' AND result_id IS NOT NULL AND violation_id IS NULL) OR "
            "(subject = 'violation' AND violation_id IS NOT NULL AND result_id IS NULL)",
            name="ck_appeal_subject",
        ),
        CheckConstraint(
            "status IN ('pending','upheld','rejected','withdrawn')",
            name="ck_appeal_status",
        ),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    athlete_id: Mapped[int] = mapped_column(ForeignKey("athletes.id"), index=True)
    subject: Mapped[str] = mapped_column(String(20))
    competition_id: Mapped[int | None] = mapped_column(ForeignKey("competitions.id"))
    result_id: Mapped[int | None] = mapped_column(ForeignKey("competition_results.id"))
    # protocol version the applicant saw when appealing
    protocol_version: Mapped[int | None] = mapped_column(Integer)
    violation_id: Mapped[int | None] = mapped_column(ForeignKey("violations.id"))
    reason: Mapped[str] = mapped_column(Text)
    request: Mapped[str] = mapped_column(Text, default="")
    submitted_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    submitted_role: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), default="pending")
    decision: Mapped[str] = mapped_column(Text, default="")
    decided_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # protocol version created by the decision
    resolution_version: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class TrainingStandard(Base):
    """Norm of general (ofp) or special (sfp) physical training for enrolment
    and transfer to a training stage; NULL sex or discipline means any."""

    __tablename__ = "training_standards"
    __table_args__ = (
        CheckConstraint("stage IN ('np','ut','ssm','vsm')", name="ck_standard_stage"),
        CheckConstraint("category IN ('ofp','sfp')", name="ck_standard_category"),
        CheckConstraint("better IN ('higher','lower')", name="ck_standard_better"),
        CheckConstraint(
            "sex IS NULL OR sex IN ('male','female')", name="ck_standard_sex"
        ),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    stage: Mapped[str] = mapped_column(String(10), index=True)
    category: Mapped[str] = mapped_column(String(10))
    name: Mapped[str] = mapped_column(String(200))
    unit: Mapped[str] = mapped_column(String(40))
    # higher: the result must be at least the threshold; lower: at most
    better: Mapped[str] = mapped_column(String(10))
    threshold: Mapped[float] = mapped_column(Float)
    sex: Mapped[str | None] = mapped_column(String(10))
    discipline_id: Mapped[int | None] = mapped_column(ForeignKey("disciplines.id"))
    source: Mapped[str] = mapped_column(Text, default="")
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class StandardResult(Base):
    """Attempt at a standard; threshold and verdict are fixed on the test date,
    readiness compares against the current threshold."""

    __tablename__ = "standard_results"
    id: Mapped[int] = mapped_column(primary_key=True)
    athlete_id: Mapped[int] = mapped_column(ForeignKey("athletes.id"), index=True)
    standard_id: Mapped[int] = mapped_column(ForeignKey("training_standards.id"))
    value: Mapped[float] = mapped_column(Float)
    tested_on: Mapped[date] = mapped_column(Date)
    threshold: Mapped[float] = mapped_column(Float)
    passed: Mapped[bool] = mapped_column(Boolean)
    comment: Mapped[str] = mapped_column(Text, default="")
    recorded_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    recorded_role: Mapped[str] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class StageTransfer(Base):
    """Enrolment or transfer to a training stage; basis keeps the standards
    and the rank the decision relied on."""

    __tablename__ = "stage_transfers"
    __table_args__ = (
        CheckConstraint("to_stage IN ('np','ut','ssm','vsm')", name="ck_transfer_stage"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    athlete_id: Mapped[int] = mapped_column(ForeignKey("athletes.id"), index=True)
    # training_stage as it was: free text entered before the catalog is kept
    from_stage: Mapped[str | None] = mapped_column(String(120))
    to_stage: Mapped[str] = mapped_column(String(10))
    decided_on: Mapped[date] = mapped_column(Date)
    order_number: Mapped[str] = mapped_column(String(120))
    basis: Mapped[dict] = mapped_column(JSON)
    comment: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class ApiToken(Base):
    """Access token of an external system; only the SHA-256 hash is stored,
    the plain value is shown once on creation."""

    __tablename__ = "api_tokens"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    prefix: Mapped[str] = mapped_column(String(16))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    scopes: Mapped[list] = mapped_column(JSON)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    expires_on: Mapped[date | None] = mapped_column(Date)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Webhook(Base):
    __tablename__ = "webhooks"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    url: Mapped[str] = mapped_column(Text)
    # HMAC-SHA256 key of the X-OrenCode-Signature header
    secret: Mapped[str] = mapped_column(String(80))
    events: Mapped[list] = mapped_column(JSON)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class WebhookDelivery(Base):
    """Outbox row written in the same transaction as the event; the worker
    sends it and retries with a growing pause."""

    __tablename__ = "webhook_deliveries"
    __table_args__ = (
        UniqueConstraint("webhook_id", "event_key"),
        CheckConstraint(
            "status IN ('pending','delivered','failed')", name="ck_webhook_status"
        ),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    webhook_id: Mapped[int] = mapped_column(
        ForeignKey("webhooks.id", ondelete="CASCADE"), index=True
    )
    event: Mapped[str] = mapped_column(String(60))
    event_key: Mapped[str] = mapped_column(String(240))
    payload: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    next_attempt_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=now, index=True
    )
    response_status: Mapped[int | None] = mapped_column(Integer)
    last_error: Mapped[str | None] = mapped_column(Text)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
