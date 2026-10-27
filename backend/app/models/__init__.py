from datetime import date, datetime, time, timezone
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
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
    roles: Mapped[list["Role"]] = relationship(secondary="user_roles", lazy="selectin")


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
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=now
    )


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
