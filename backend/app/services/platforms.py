"""Protocol from a testing system: standings of Codeforces, Yandex Contest
and CTFd are fetched, logins are matched to athletes, places are recounted
among the competition's participants."""

import hashlib
import secrets
from dataclasses import dataclass, field
from urllib.parse import urlsplit
import httpx
from fastapi import HTTPException
from sqlalchemy import select
from app.config import settings
from app.models import *
from app.schemas import ImportRowIn
from app.services.athlete_ids import parse_athlete_id, public_athlete_id
from app.services.integrations import athlete_data, check_url

PLATFORMS = {
    "codeforces": "Codeforces",
    "yandex_contest": "Яндекс Контест",
    "ctfd": "CTFd",
}
CODEFORCES_API = "https://codeforces.com/api"
# ids of gym contests start here; only they accept a signed request
CODEFORCES_GYM = 100000
YANDEX_API = "https://api.contest.yandex.net/api/public/v2"
YANDEX_PAGE = 100
MAX_PAGES = 100
MAX_LOGIN = 100


# --- logins in profiles -----------------------------------------------------


def login_key(value):
    return value.strip().lower()


def logins(db, athlete_id):
    return {
        x.platform: x.login
        for x in db.scalars(
            select(AthletePlatformLogin).where(AthletePlatformLogin.athlete_id == athlete_id)
        )
    }


def save_login(db, athlete_id, platform, login):
    """Sets or, with an empty value, removes the athlete's login; a login
    belongs to one athlete only."""
    login, key = login.strip(), login_key(login)
    if len(login) > MAX_LOGIN:
        raise HTTPException(422, f"Логин на {PLATFORMS[platform]} длиннее {MAX_LOGIN} символов")
    current = db.scalar(
        select(AthletePlatformLogin).where(
            AthletePlatformLogin.athlete_id == athlete_id,
            AthletePlatformLogin.platform == platform,
        )
    )
    if not key:
        if current:
            db.delete(current)
        return
    other = db.scalar(
        select(AthletePlatformLogin.athlete_id).where(
            AthletePlatformLogin.platform == platform,
            AthletePlatformLogin.login_key == key,
        )
    )
    if other and other != athlete_id:
        raise HTTPException(
            409, f"Логин «{login}» на {PLATFORMS[platform]} уже привязан к другому спортсмену"
        )
    if current:
        current.login, current.login_key = login, key
    else:
        db.add(AthletePlatformLogin(athlete_id=athlete_id, platform=platform, login=login, login_key=key))
    db.flush()


# --- adapters ---------------------------------------------------------------


@dataclass
class PlatformRow:
    """One line of the standings; a team line carries the logins of its members."""

    logins: list
    name: str
    place: int
    score: float


@dataclass
class Standings:
    title: str
    url: str
    rows: list


def get(url, params, headers):
    with httpx.Client(timeout=10, follow_redirects=False) as client:
        return client.get(url, params=params, headers=headers)


def request(platform, url, params=None, headers=None):
    try:
        response = get(url, params or {}, {"User-Agent": "OrenCode/1.0", **(headers or {})})
    except httpx.HTTPError:
        raise HTTPException(502, f"{PLATFORMS[platform]} не ответил, попробуйте позже")
    try:
        data = response.json()
    except ValueError:
        data = None
    return response.status_code, data


def failed(platform, status):
    name = PLATFORMS[platform]
    if status in (401, 403):
        raise HTTPException(422, f"{name} отказал в доступе: проверьте токен и права на контест")
    if status == 404:
        raise HTTPException(422, f"Контест на {name} не найден")
    raise HTTPException(502, f"{name} ответил кодом {status}")


def number(value):
    try:
        return float(str(value).replace(",", ".").replace(" ", "") or 0)
    except ValueError:
        raise HTTPException(502, f"Непонятные баллы в таблице площадки: «{value}»")


def contest_number(platform, contest):
    if not contest.isdigit():
        raise HTTPException(422, f"Номер контеста на {PLATFORMS[platform]} — число, например 2050")
    return contest


def codeforces_sign(method, params):
    """apiSig of Codeforces for closed contests and groups."""
    params = {**params, "apiKey": settings.codeforces_api_key, "time": str(int(now().timestamp()))}
    rand = f"{secrets.randbelow(900000) + 100000}"
    query = "&".join(f"{k}={v}" for k, v in sorted(params.items()))
    text = f"{rand}/{method}?{query}#{settings.codeforces_api_secret}"
    return {**params, "apiSig": rand + hashlib.sha512(text.encode()).hexdigest()}


def codeforces(contest, token):
    contest = contest_number("codeforces", contest)
    # regular contests are served only to an anonymous request with no other
    # parameters; it lists official participants only
    params = {"contestId": contest}
    gym = int(contest) >= CODEFORCES_GYM
    if gym and settings.codeforces_api_key and settings.codeforces_api_secret:
        params = codeforces_sign("contest.standings", params)
    status, data = request("codeforces", f"{CODEFORCES_API}/contest.standings", params)
    # errors come as 400 with {"status": "FAILED", "comment": ...}
    if isinstance(data, dict) and data.get("status") == "FAILED":
        raise HTTPException(422, f"Codeforces: {data.get('comment') or 'ошибка запроса'}")
    if status != 200 or not isinstance(data, dict):
        failed("codeforces", status)
    result = data["result"]
    info = result.get("contest", {})
    if info.get("phase") != "FINISHED":
        raise HTTPException(
            422, f"Контест на Codeforces ещё не завершён (фаза {info.get('phase', '—')})"
        )
    rows = []
    for r in result.get("rows", []):
        party = r["party"]
        handles = [m["handle"] for m in party.get("members", [])]
        rows.append(
            PlatformRow(
                logins=handles,
                name=party.get("teamName") or ", ".join(handles),
                place=int(r["rank"]),
                score=number(r.get("points", 0)),
            )
        )
    return Standings(
        title=info.get("name") or f"Контест {contest}",
        url=f"https://codeforces.com/{'gym' if gym else 'contest'}/{contest}/standings",
        rows=rows,
    )


def yandex_contest(contest, token):
    contest = contest_number("yandex_contest", contest)
    token = token or settings.yandex_contest_token
    if not token:
        raise HTTPException(
            422, "Для Яндекс Контеста нужен OAuth-токен: укажите его или задайте YANDEX_CONTEST_TOKEN"
        )
    headers = {"Authorization": f"OAuth {token}"}
    base = f"{YANDEX_API}/contests/{contest}"
    status, info = request("yandex_contest", base, headers=headers)
    if status != 200 or not isinstance(info, dict):
        failed("yandex_contest", status)
    rows = []
    for page in range(1, MAX_PAGES + 1):
        status, data = request(
            "yandex_contest",
            base + "/standings",
            {"page": page, "pageSize": YANDEX_PAGE, "forJudge": "false"},
            headers,
        )
        if status != 200 or not isinstance(data, dict):
            failed("yandex_contest", status)
        chunk = data.get("rows", [])
        for r in chunk:
            who = r.get("participantInfo", {})
            rows.append(
                PlatformRow(
                    logins=[who["login"]] if who.get("login") else [],
                    name=who.get("name") or who.get("login") or "",
                    place=int(r["placeFrom"]),
                    score=number(r.get("score", 0)),
                )
            )
        if len(chunk) < YANDEX_PAGE:
            break
    return Standings(
        title=info.get("name") or f"Контест {contest}",
        url=f"https://contest.yandex.ru/contest/{contest}/standings/",
        rows=rows,
    )


def ctfd(contest, token):
    base = contest.strip().rstrip("/")
    parts = urlsplit(base)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise HTTPException(422, "Укажите адрес площадки CTFd, например https://ctf.example.org")
    try:
        check_url(base, lookup=True)
    except ValueError:
        raise HTTPException(422, "Адрес CTFd указывает на внутреннюю сеть")
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Token {token}"
    status, data = request("ctfd", base + "/api/v1/scoreboard", headers=headers)
    if status != 200 or not isinstance(data, dict) or not data.get("success"):
        failed("ctfd", status)
    rows = []
    for r in data.get("data", []):
        members = [m["name"] for m in r.get("members") or []]
        rows.append(
            PlatformRow(
                # in team mode the members are matched, the team by its name
                logins=members or [r["name"]],
                name=r["name"],
                place=int(r["pos"]),
                score=number(r.get("score", 0)),
            )
        )
    return Standings(title=parts.hostname, url=base + "/scoreboard", rows=rows)


ADAPTERS = {"codeforces": codeforces, "yandex_contest": yandex_contest, "ctfd": ctfd}


def fetch(platform, contest, token=None):
    standings = ADAPTERS[platform](contest.strip(), token)
    if not standings.rows:
        raise HTTPException(422, "Таблица результатов контеста пуста")
    return standings


# --- matching ---------------------------------------------------------------


@dataclass
class Match:
    rows: list = field(default_factory=list)
    matched: list = field(default_factory=list)
    unmatched: list = field(default_factory=list)
    # approved participants absent from the table: left out of the protocol
    missing: list = field(default_factory=list)
    conflicts: list = field(default_factory=list)
    # logins bound by hand that were used: login -> athlete id
    bound: dict = field(default_factory=dict)

    @property
    def ready(self):
        return bool(self.rows) and not self.conflicts


def recount(places):
    """Places among the competition's participants by the "1, 1, 3" rule."""
    return [1 + sum(other < place for other in places) for place in places]


def match(db, comp, platform, standings, bindings):
    approved = list(
        db.scalars(
            select(CompetitionApplication.athlete_id).where(
                CompetitionApplication.competition_id == comp.id,
                CompetitionApplication.status == "approved",
            )
        )
    )
    registry = dict(
        db.execute(
            select(AthletePlatformLogin.login_key, AthletePlatformLogin.athlete_id).where(
                AthletePlatformLogin.platform == platform
            )
        ).all()
    )
    hand = {}
    for login, athlete_id in bindings.items():
        key = login_key(login)
        if athlete_id not in approved:
            raise HTTPException(422, f"Логин «{login}» можно привязать только к одобренному участнику")
        if registry.get(key, athlete_id) != athlete_id:
            raise HTTPException(
                409, f"Логин «{login}» уже привязан к спортсмену {public_athlete_id(registry[key])}"
            )
        hand[key] = athlete_id

    def athlete_of(login):
        key = login_key(login)
        if key in hand:
            return hand[key]
        if key in registry:
            return registry[key]
        try:
            return parse_athlete_id(login)
        except HTTPException:
            return None

    result = Match()
    found = []  # (row, subject id, logins that matched)
    if comp.entry_mode == "team":
        teams = {
            t.id: t
            for t in db.scalars(
                select(CompetitionTeam).where(
                    CompetitionTeam.competition_id == comp.id,
                    CompetitionTeam.status == "approved",
                )
            )
        }
        member_team = dict(
            db.execute(
                select(CompetitionTeamMember.athlete_id, CompetitionTeamMember.team_id).where(
                    CompetitionTeamMember.competition_id == comp.id,
                    CompetitionTeamMember.status == "accepted",
                    CompetitionTeamMember.team_id.in_(teams),
                )
            ).all()
        )
        by_name = {t.name.strip().lower(): t.id for t in teams.values()}
        for r in standings.rows:
            used = [l for l in r.logins if member_team.get(athlete_of(l))]
            ids = {member_team[athlete_of(l)] for l in used}
            if not ids and r.name.strip().lower() in by_name:
                ids = {by_name[r.name.strip().lower()]}
            if len(ids) > 1:
                result.conflicts.append(f"«{r.name}»: участники из разных команд соревнования")
            elif ids:
                found.append((r, ids.pop(), used))
            else:
                result.unmatched.append(unmatched_view(r, "Команда не допущена к соревнованию"))
        expected = set(teams)
    else:
        for r in standings.rows:
            hits = [(l, athlete_of(l)) for l in r.logins + [r.name]]
            ids = {a for _, a in hits if a in approved}
            if len(ids) > 1:
                result.conflicts.append(f"«{r.name}»: в одной строке несколько участников соревнования")
            elif ids:
                athlete_id = ids.pop()
                found.append((r, athlete_id, [l for l, a in hits if a == athlete_id and l in r.logins]))
            else:
                known = any(a for _, a in hits if a and db.get(Athlete, a))
                result.unmatched.append(
                    unmatched_view(r, "Нет одобренной заявки" if known else "Логин не найден в реестре")
                )
        expected = set(approved)
    seen = {}
    for r, subject, _ in found:
        if subject in seen:
            name = teams[subject].name if comp.entry_mode == "team" else public_athlete_id(subject)
            result.conflicts.append(f"{name}: несколько строк в таблице («{seen[subject]}», «{r.name}»)")
        seen.setdefault(subject, r.name)
        if r.score < 0:
            result.conflicts.append(f"«{r.name}»: отрицательные баллы {r.score}")
    places = recount([r.place for r, _, _ in found])
    for (r, subject, used), place in zip(found, places):
        login = used[0] if used else (r.logins[0] if r.logins else "")
        for l in used:
            if login_key(l) in hand:
                result.bound[l] = hand[login_key(l)]
        if comp.entry_mode == "team":
            result.rows.append(ImportRowIn(team=str(subject), place=place, score=max(r.score, 0)))
            who = {"team_id": subject, "full_name": teams[subject].name}
        else:
            result.rows.append(ImportRowIn(athlete=str(subject), place=place, score=max(r.score, 0)))
            who = athlete_data(db, subject)
        result.matched.append(
            {**who, "login": login, "platform_name": r.name, "platform_place": r.place,
             "place": place, "score": r.score}
        )
    result.matched.sort(key=lambda m: (m["place"], m["full_name"]))
    if comp.entry_mode == "team":
        result.missing = [
            {"team_id": t, "full_name": teams[t].name} for t in expected if t not in seen
        ]
    else:
        result.missing = [
            {"id": a, **athlete_data(db, a)} for a in expected if a not in seen
        ]
    result.missing.sort(key=lambda m: m["full_name"])
    # rows of a published protocol stay (ranks and appeals refer to them), so
    # a participant already in it has to be found again
    in_protocol = set(
        db.scalars(
            select(CompetitionResult.athlete_id).where(CompetitionResult.competition_id == comp.id)
        )
    )
    for m in result.missing:
        if comp.entry_mode == "team":
            m["in_protocol"] = any(member_team.get(a) == m["team_id"] for a in in_protocol)
        else:
            m["in_protocol"] = m["id"] in in_protocol
        if m["in_protocol"]:
            result.conflicts.append(
                f"{m['full_name']}: уже в протоколе, но не найден в таблице — "
                "укажите логин или привяжите строку"
            )
    return result


def unmatched_view(row, reason):
    return {
        "login": row.logins[0] if row.logins else row.name,
        "name": row.name,
        "platform_place": row.place,
        "score": row.score,
        "reason": reason,
    }
