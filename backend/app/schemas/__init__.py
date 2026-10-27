from datetime import date
from typing import Literal
from pydantic import BaseModel, ConfigDict, EmailStr, Field, HttpUrl, model_validator

RoleName = Literal["admin", "athlete", "coach", "judge", "ministry"]
Level = Literal["regional", "interregional", "russian_championship", "russian_junior"]
Status = Literal["regional", "interregional", "national"]
RatingClass = Literal["main", "junior", "other"]
Sex = Literal["male", "female"]


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


class AwardStatusIn(Strict):
    status: Literal["candidate", "nominated", "awarded", "rejected"]
    comment: str = Field("", max_length=2000)
    order_number: str | None = Field(None, max_length=120)
