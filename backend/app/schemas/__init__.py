from datetime import date, time
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from typing import Literal
from pydantic import BaseModel, ConfigDict, EmailStr, Field, HttpUrl, model_validator

RoleName = Literal["admin", "athlete", "coach", "judge", "ministry"]
Level = Literal["regional", "interregional", "russian_championship", "russian_junior"]
Status = Literal["regional", "interregional", "national"]
RatingClass = Literal["main", "junior", "other"]
Sex = Literal["male", "female"]
Platform = Literal["codeforces", "yandex_contest", "ctfd"]


class CoachChatMessageIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    body: str = Field(min_length=1, max_length=4000)


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Register(Strict):
    email: EmailStr
    password: str = Field(min_length=10, max_length=128)
    full_name: str = Field(min_length=3, max_length=200)
    birth_date: date
    sex: Sex | None = None
    role: Literal["athlete", "coach", "judge"] = "athlete"
    consent: bool
    guardian_name: str | None = Field(None, max_length=200)
    guardian_consent: bool = False

    @model_validator(mode="after")
    def consent_check(self):
        today = date.today()
        age = (
            today.year
            - self.birth_date.year
            - ((today.month, today.day) < (self.birth_date.month, self.birth_date.day))
        )
        if age < 0 or age > 110:
            raise ValueError("Некорректная дата рождения")
        if not self.consent:
            raise ValueError("Необходимо согласие на обработку персональных данных")
        if age < 18 and (not self.guardian_consent or not self.guardian_name):
            raise ValueError("Требуются ФИО и согласие законного представителя")
        if age < 18 and self.role != "athlete":
            raise ValueError("Регистрация тренера и судьи доступна с 18 лет")
        return self


class Login(Strict):
    email: EmailStr
    password: str


class CompetitionIn(Strict):
    title: str = Field(min_length=3, max_length=240)
    discipline_id: int
    type_id: int
    start_date: date
    start_time: time | None = None
    timezone: str = Field("Asia/Yekaterinburg", max_length=80)
    end_date: date
    deadline: date
    location: str = Field(min_length=2, max_length=200)
    format: Literal["onsite", "online", "hybrid"]
    status: Status
    min_age: int = Field(0, ge=0, le=100)
    max_age: int = Field(100, ge=0, le=100)
    age_group_ids: list[int] = Field(default_factory=list, max_length=20)
    calendar_plan: str = Field(min_length=2, max_length=100)
    calendar_number: str = Field(min_length=1, max_length=80)
    regulation_url: HttpUrl | None = None
    entry_mode: Literal["individual", "team"] = "individual"
    team_min: int = Field(2, ge=1, le=50)
    team_max: int = Field(3, ge=1, le=50)
    team_rating: bool = False

    @model_validator(mode="after")
    def dates(self):
        validate_start(self.start_time, self.timezone)
        if (
            self.end_date < self.start_date
            or self.deadline > self.start_date
            or self.min_age > self.max_age
        ):
            raise ValueError("Проверьте даты и возрастные ограничения")
        if self.team_min > self.team_max:
            raise ValueError("Минимальный состав команды больше максимального")
        expected = "Оренбургская область" if self.status == "regional" else "ЕКП"
        if self.calendar_plan != expected:
            raise ValueError(f"Для выбранного статуса календарный план: {expected}")
        return self


def validate_start(start_time, timezone):
    try:
        ZoneInfo(timezone)
    except (ZoneInfoNotFoundError, ValueError):
        raise ValueError("Укажите действующий часовой пояс IANA")
    if start_time and start_time.tzinfo:
        raise ValueError("Время указывается без смещения, с отдельным часовым поясом")


class CompetitionScheduleIn(Strict):
    start_date: date
    end_date: date
    start_time: time | None = None
    timezone: str = Field("Asia/Yekaterinburg", max_length=80)

    @model_validator(mode="after")
    def dates(self):
        validate_start(self.start_time, self.timezone)
        if self.end_date < self.start_date:
            raise ValueError("Дата окончания раньше начала")
        return self


class AgeGroupIn(Strict):
    name: str = Field(min_length=2, max_length=100)
    discipline_id: int | None = None
    sex: Sex | None = None
    min_age: int = Field(ge=0, le=100)
    max_age: int = Field(ge=0, le=100)
    age_rule: Literal["year", "start"] = "year"
    sort_order: int = Field(0, ge=0, le=1000)

    @model_validator(mode="after")
    def ages(self):
        if self.min_age > self.max_age:
            raise ValueError("Минимальный возраст больше максимального")
        return self


class StateIn(Strict):
    state: Literal["draft", "open", "closed"]


class ApplicationIn(Strict):
    athlete_id: int


class Decision(Strict):
    status: Literal["approved", "rejected"]
    comment: str = Field("", max_length=2000)


class ResultIn(Strict):
    athlete_id: int
    place: int = Field(gt=0)
    score: float = Field(ge=0, allow_inf_nan=False)
    team_name: str | None = Field(None, min_length=1, max_length=120)


class TeamResultIn(Strict):
    team_id: int
    place: int = Field(gt=0)
    score: float = Field(ge=0, allow_inf_nan=False)


class ResultsIn(Strict):
    results: list[ResultIn] = Field(default_factory=list, max_length=10000)
    team_results: list[TeamResultIn] = Field(default_factory=list, max_length=1000)

    @model_validator(mode="after")
    def one_mode(self):
        if bool(self.results) == bool(self.team_results):
            raise ValueError("Передайте результаты спортсменов или команд")
        return self


class ProtocolCorrectionIn(ResultsIn):
    reason: str = Field(min_length=5, max_length=2000)


class JudgeIn(Strict):
    judge_id: int
    position: str = Field(min_length=2, max_length=120)


class LinkIn(Strict):
    athlete_id: int
    discipline_id: int


class LinkState(Strict):
    status: Literal["active", "paused", "ended"]


class Enrollment(Strict):
    discipline_id: int
    start_year: int = Field(ge=1970, le=2100)
    end_year: int | None = Field(None, ge=1970, le=2100)

    @model_validator(mode="after")
    def years(self):
        if self.start_year > date.today().year or (
            self.end_year is not None and self.end_year < self.start_year
        ):
            raise ValueError("Проверьте годы занятий")
        return self


class ProfileIn(Strict):
    full_name: str = Field(min_length=3, max_length=200)
    sex: Sex | None = None
    organization_id: int | None = None
    # date of the transfer when organization_id changes; today by default
    organization_since: date | None = None
    municipality: str = Field(min_length=2, max_length=120)
    training_stage: str | None = Field(None, max_length=120)
    rusada_date: date | None = None
    rusada_certificate: HttpUrl | None = None
    disciplines: list[Enrollment]
    # logins on testing systems; an empty value removes the login, a missing
    # key keeps it, a missing field leaves all logins as they are
    platform_logins: dict[Platform, str] | None = None


class StaffCardIn(Strict):
    full_name: str = Field(min_length=3, max_length=200)
    sex: Sex | None = None
    birth_date: date
    organization_id: int | None = None
    municipality: str = Field(min_length=2, max_length=120)
    phone: str | None = Field(None, max_length=30, pattern=r"^\+?[\d\s()\-]{5,30}$")
    contact_email: EmailStr | None = None
    qualification: str | None = Field(None, max_length=200)
    experience_since: int | None = Field(None, ge=1950)
    about: str | None = Field(None, max_length=2000)
    discipline_ids: list[int] = Field(default_factory=list, max_length=50)

    @model_validator(mode="after")
    def staff_check(self):
        today = date.today()
        age = (
            today.year
            - self.birth_date.year
            - ((today.month, today.day) < (self.birth_date.month, self.birth_date.day))
        )
        if age < 18 or age > 110:
            raise ValueError("Тренер и судья — от 18 лет, проверьте дату рождения")
        if self.experience_since and self.experience_since > today.year:
            raise ValueError("Год начала стажа в будущем")
        if len(set(self.discipline_ids)) != len(self.discipline_ids):
            raise ValueError("Дисциплина указана дважды")
        return self


class StaffCreate(StaffCardIn):
    email: EmailStr
    # required only when no user with this email exists yet
    password: str | None = Field(None, min_length=10, max_length=128)


class ArchiveIn(Strict):
    reason: str = Field(min_length=3, max_length=2000)


class RankIn(Strict):
    athlete_id: int | None = None
    result_id: int | None = None
    name: str = Field(min_length=2, max_length=100)
    kind: Literal["assignment", "confirmation"] = "assignment"


class RankDecision(Decision):
    assigned_on: date | None = None
    expires_on: date | None = None
    order_number: str | None = Field(None, max_length=120)

    @model_validator(mode="after")
    def order(self):
        if self.status == "approved" and (
            not self.assigned_on
            or not self.expires_on
            or not self.order_number
            or self.expires_on <= self.assigned_on
            or self.assigned_on > date.today()
        ):
            raise ValueError("Укажите приказ, дату присвоения и срок действия")
        return self


class TeamIn(Strict):
    season: int = Field(ge=2000, le=2100)
    discipline_id: int
    athlete_ids: list[int]


class RuleIn(Strict):
    first: int = Field(ge=0, le=10000)
    second: int = Field(ge=0, le=10000)
    third: int = Field(ge=0, le=10000)


class OrganizationIn(Strict):
    name: str = Field(min_length=2, max_length=200)
    kind: str = Field(min_length=2, max_length=80)
    municipality: str = Field(min_length=2, max_length=120)


class NameIn(Strict):
    name: str = Field(min_length=2, max_length=100)


class CompetitionTypeIn(NameIn):
    rating_class: RatingClass = "other"


class RolesIn(Strict):
    roles: list[RoleName] = Field(min_length=1)


class SuspensionIn(Strict):
    suspended_until: date | None = None
    reason: str = Field(min_length=3, max_length=2000)


class EvskIn(Strict):
    discipline_id: int
    level: Level
    rank_name: str = Field(min_length=1, max_length=100)
    max_place: int = Field(ge=1)
    min_participants: int = Field(ge=1)
    source: str = Field(min_length=10, max_length=2000)


class DeadlineIn(Strict):
    title: str = Field(min_length=3, max_length=240)
    due_on: date
    done: bool = False


class TeamCreateIn(Strict):
    name: str = Field(min_length=2, max_length=120)
    captain_id: int


class TeamMemberIn(Strict):
    athlete_id: int | None = Field(None, gt=0)
    public_id: str | None = Field(None, min_length=10, max_length=14)

    @model_validator(mode="after")
    def one_identifier(self):
        if (self.athlete_id is None) == (self.public_id is None):
            raise ValueError("Укажите один идентификатор спортсмена")
        return self


class TeamResponseIn(Strict):
    status: Literal["accepted", "declined"]


class TeamReviewIn(Strict):
    status: Literal["approved", "returned"]
    comment: str = Field("", max_length=2000)


class TeamReopenIn(Strict):
    reason: str = Field(min_length=5, max_length=2000)


class PassportSettingsIn(Strict):
    enabled: bool
    show_results: bool = True
    show_rating: bool = True
    show_team: bool = True
    show_rusada: bool = False
    consent: bool = False


class ProfileVisibilityIn(Strict):
    show_results: bool = True
    show_rating: bool = True
    show_ranks: bool = True
    show_disciplines: bool = True
    show_organization: bool = True
    show_municipality: bool = True
    show_team: bool = True
    show_rusada: bool = False
    show_training_stage: bool = False
    show_training_years: bool = False


class IndicatorIn(Strict):
    year: int = Field(ge=1970, le=2100)
    name: str = Field(min_length=3, max_length=240)
    value: float = Field(ge=0, le=1e12)
    unit: str = Field("чел.", min_length=1, max_length=40)
    organization_id: int | None = None
    source: str = Field(min_length=5, max_length=2000)
    comment: str = Field("", max_length=2000)

    @model_validator(mode="after")
    def not_future(self):
        if self.year > date.today().year:
            raise ValueError("Показатель не может относиться к будущему году")
        return self


class AwardRuleIn(Strict):
    first: int = Field(ge=0, le=10_000_000)
    second: int = Field(ge=0, le=10_000_000)
    third: int = Field(ge=0, le=10_000_000)


class ViolationIn(Strict):
    athlete_id: int
    competition_id: int | None = None
    kind: Literal["rules", "conduct", "doping", "other"]
    occurred_on: date
    description: str = Field(min_length=5, max_length=2000)
    sanction: Literal["warning", "suspension"]
    suspended_until: date | None = None

    @model_validator(mode="after")
    def sanction_dates(self):
        if self.occurred_on > date.today():
            raise ValueError("Дата нарушения не может быть в будущем")
        if (self.sanction == "suspension") != (self.suspended_until is not None):
            raise ValueError("Срок отстранения указывается только для отстранения")
        if self.suspended_until and self.suspended_until < date.today():
            raise ValueError("Срок отстранения уже истёк")
        return self


class AppealIn(Strict):
    subject: Literal["result", "violation"]
    result_id: int | None = None
    violation_id: int | None = None
    reason: str = Field(min_length=10, max_length=4000)
    request: str = Field("", max_length=2000)

    @model_validator(mode="after")
    def one_subject(self):
        if (self.result_id is None) != (self.subject == "violation") or (
            self.violation_id is None
        ) != (self.subject == "result"):
            raise ValueError("Укажите строку протокола или нарушение")
        return self


class AppealDecisionIn(Strict):
    status: Literal["upheld", "rejected"]
    decision: str = Field(min_length=5, max_length=4000)
    # corrected protocol for an upheld result appeal; omit to keep the protocol
    correction: ResultsIn | None = None


class AwardStatusIn(Strict):
    status: Literal["candidate", "nominated", "awarded", "rejected"]
    comment: str = Field("", max_length=2000)
    order_number: str | None = Field(None, max_length=120)


Stage = Literal["np", "ut", "ssm", "vsm"]


class StandardIn(Strict):
    stage: Stage
    category: Literal["ofp", "sfp"]
    name: str = Field(min_length=3, max_length=200)
    unit: str = Field(min_length=1, max_length=40)
    better: Literal["higher", "lower"]
    threshold: float = Field(ge=0, le=1_000_000)
    sex: Sex | None = None
    discipline_id: int | None = None
    source: str = Field("", max_length=2000)
    sort_order: int = Field(0, ge=0, le=10_000)


class StandardResultIn(Strict):
    standard_id: int
    value: float = Field(ge=0, le=1_000_000)
    tested_on: date
    comment: str = Field("", max_length=2000)

    @model_validator(mode="after")
    def not_future(self):
        if self.tested_on > date.today():
            raise ValueError("Дата сдачи не может быть в будущем")
        return self


class StageTransferIn(Strict):
    to_stage: Stage
    decided_on: date
    order_number: str = Field(min_length=1, max_length=120)
    comment: str = Field("", max_length=2000)

    @model_validator(mode="after")
    def not_future(self):
        if self.decided_on > date.today():
            raise ValueError("Дата приказа не может быть в будущем")
        return self


ApiScope = Literal["competitions:read", "applications:read", "results:read", "results:write"]
WebhookEvent = Literal["competition.published", "application.approved", "protocol.published"]


class ApiTokenIn(Strict):
    name: str = Field(min_length=3, max_length=120)
    scopes: list[ApiScope] = Field(min_length=1, max_length=4)
    expires_on: date | None = None

    @model_validator(mode="after")
    def future(self):
        if self.expires_on and self.expires_on <= date.today():
            raise ValueError("Срок действия должен быть в будущем")
        self.scopes = list(dict.fromkeys(self.scopes))
        return self


def check_webhook_url(value):
    from app.services.integrations import check_url

    check_url(str(value))


class WebhookIn(Strict):
    name: str = Field(min_length=3, max_length=120)
    url: HttpUrl
    events: list[WebhookEvent] = Field(min_length=1, max_length=3)

    @model_validator(mode="after")
    def safe_url(self):
        check_webhook_url(self.url)
        self.events = list(dict.fromkeys(self.events))
        return self


class WebhookPatch(Strict):
    name: str | None = Field(None, min_length=3, max_length=120)
    url: HttpUrl | None = None
    events: list[WebhookEvent] | None = Field(None, min_length=1, max_length=3)
    active: bool | None = None

    @model_validator(mode="after")
    def safe_url(self):
        if self.url is not None:
            check_webhook_url(self.url)
        if self.events is not None:
            self.events = list(dict.fromkeys(self.events))
        return self


class ImportRowIn(Strict):
    """Athlete by FSP-000123 or internal id; team by id or name."""

    athlete: str | None = Field(None, max_length=40, coerce_numbers_to_str=True)
    team: str | None = Field(None, max_length=120, coerce_numbers_to_str=True)
    place: int = Field(gt=0, le=100_000)
    score: float = Field(ge=0, allow_inf_nan=False)
    line: int | None = Field(None, exclude=True)

    @model_validator(mode="after")
    def one_subject(self):
        if not self.athlete and not self.team:
            raise ValueError("Укажите спортсмена или команду")
        return self


class ResultsImportIn(Strict):
    results: list[ImportRowIn] = Field(min_length=1, max_length=10000)
    # required when the protocol is already published: a new version is made
    reason: str | None = Field(None, min_length=5, max_length=2000)


class PlatformImportIn(Strict):
    """Results from a testing system: a contest number on Codeforces or Yandex
    Contest, the address of a CTFd instance."""

    platform: Platform
    contest: str = Field(min_length=1, max_length=300)
    # access token for this request only, never stored
    token: str | None = Field(None, max_length=500)
    # manual matching of logins absent in profiles: login -> athlete id
    bindings: dict[str, int] = Field(default_factory=dict, max_length=1000)
    reason: str | None = Field(None, min_length=5, max_length=2000)
    dry_run: bool = True
