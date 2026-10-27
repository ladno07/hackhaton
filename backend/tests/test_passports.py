"""Profiles are authenticated; personal participation certificates are private."""

from datetime import date
from sqlalchemy import select
from app.models import (
    Athlete,
    AthleteCoach,
    Coach,
    Competition,
    CompetitionResult,
    ProtocolVersion,
    PassportPublication,
    PublicProtocolProof,
)
from app.services.passports import VISIBILITY_DEFAULTS
from test_competition_teams import ok
from test_workflows import closed_comp


def own_result(env):
    client, factory, h, users = env
    with factory() as db:
        result = db.scalar(
            select(CompetitionResult)
            .join(Competition, Competition.id == CompetitionResult.competition_id)
            .where(
                CompetitionResult.athlete_id == users["athlete"]["athlete_id"],
                Competition.state == "published",
            )
        )
        assert result
        return client, factory, h, users, result.id


def test_profile_requires_login_and_excludes_private_fields(env):
    client, factory, h, users = env
    aid = users["athlete"]["athlete_id"]
    assert client.get(f"/api/athlete-profiles/{aid}").status_code in {401, 403}
    for role in ["athlete", "coach", "judge", "admin"]:
        response = client.get(f"/api/athlete-profiles/{aid}", headers=h[role])
        data = ok(response)
        assert data["full_name"] == users["athlete"]["full_name"] and data["results"]
        assert response.headers["cache-control"] == "no-store"

        def check(value):
            if isinstance(value, dict):
                assert not set(value) & {
                    "id",
                    "athlete_id",
                    "user_id",
                    "email",
                    "phone",
                    "birth_date",
                    "age",
                    "guardian_name",
                    "guardian_consent_at",
                    "rusada_certificate",
                    "suspension_reason",
                    "order_number",
                    "proof_hash",
                    "verify_path",
                    "certificate",
                    "fingerprint",
                }
                for child in value.values():
                    check(child)
            elif isinstance(value, list):
                for child in value:
                    check(child)

        check(data)
    assert (
        client.get("/api/athlete-profiles/999999", headers=h["athlete"]).status_code
        == 404
    )


def test_visibility_is_owned_persistent_and_enforced_for_other_viewers(env):
    client, factory, h, users = env
    aid = users["athlete"]["athlete_id"]
    defaults = ok(client.get("/api/my/profile-visibility", headers=h["athlete"]))
    assert defaults == VISIBILITY_DEFAULTS
    hidden = {key: False for key in defaults}
    ok(client.put("/api/my/profile-visibility", headers=h["athlete"], json=hidden))
    assert ok(client.get("/api/my/profile-visibility", headers=h["athlete"])) == hidden
    data = ok(client.get(f"/api/athlete-profiles/{aid}", headers=h["judge"]))
    assert data["full_name"] == users["athlete"]["full_name"]
    for key in ["results", "ratings", "ranks", "disciplines", "team"]:
        assert data[key] == []
    for key in ["organization", "municipality", "training_stage", "rusada"]:
        assert data[key] is None
    assert all(value is None for value in data["stats"].values())
    shown = {key: True for key in defaults}
    ok(client.put("/api/my/profile-visibility", headers=h["athlete"], json=shown))
    data = ok(client.get(f"/api/athlete-profiles/{aid}", headers=h["coach"]))
    assert (
        data["results"]
        and data["ratings"]
        and data["ranks"]
        and data["organization"]
        and data["municipality"]
        and data["training_stage"]
    )
    assert data["disciplines"][0]["start_year"] and data["rusada"]["completed_on"]
    assert "certificate" not in str(data["rusada"])
    for role in ["coach", "judge", "admin"]:
        assert (
            client.put(
                "/api/my/profile-visibility", headers=h[role], json=shown
            ).status_code
            == 403
        )
    assert (
        client.put(
            "/api/my/profile-visibility",
            headers=h["athlete"],
            json={**shown, "athlete_id": 999},
        ).status_code
        == 422
    )
    with factory() as db:
        cfg = db.get(PassportPublication, aid)
        assert not cfg.enabled and cfg.slug is None


def test_old_public_links_are_closed_even_when_old_config_exists(env):
    client, factory, h, users, rid = own_result(env)
    slug = "p-" + "x" * 32
    digest = "a" * 64
    with factory() as db:
        db.add(
            PassportPublication(
                athlete_id=users["athlete"]["athlete_id"], enabled=True, slug=slug
            )
        )
        version = db.scalar(
            select(ProtocolVersion)
            .join(Competition, Competition.id == ProtocolVersion.competition_id)
            .where(Competition.state == "published")
        )
        db.add(
            PublicProtocolProof(
                digest=digest,
                athlete_id=users["athlete"]["athlete_id"],
                protocol_version_id=version.id,
                publication_slug=slug,
                payload={"full_name": "SECRET-OLD-DATA"},
            )
        )
        db.commit()
    urls = [
        f"/api/public/passports/{slug}" + suffix
        for suffix in ["", "/page", "/qr.svg", "/portfolio.pdf"]
    ] + [
        f"/api/public/protocols/{digest}" + suffix
        for suffix in ["", "/page", "/qr.svg", "/extract.pdf", "/certificate.pdf"]
    ]
    for url in urls:
        for headers in [{}, h["athlete"]]:
            response = client.get(url, headers=headers)
            assert (
                response.status_code == 404 and "SECRET-OLD-DATA" not in response.text
            )
            assert response.headers["cache-control"] == "no-store"
    assert (
        client.put(
            "/api/my/passport",
            headers=h["athlete"],
            json={"enabled": True, "consent": True},
        ).status_code
        == 410
    )


def test_certificate_is_available_without_publication_even_for_minor(env):
    client, factory, h, users, rid = own_result(env)
    data = ok(client.get(f"/api/results/{rid}/certificate", headers=h["athlete"]))
    assert data["entry"]["full_name"] == users["athlete"]["full_name"]
    assert data["certificate_number"] == f"FSP-CERT-{rid}-V{data['version']}"
    assert data["path"] == f"/certificates/{rid}?version={data['version']}"
    response = client.get(f"/api/results/{rid}/certificate.pdf", headers=h["athlete"])
    assert response.status_code == 200 and response.content.startswith(b"%PDF-")
    assert response.headers["cache-control"] == "no-store"
    assert ok(client.get("/api/results", headers=h["athlete"]))[0][
        "can_download_certificate"
    ]
    with factory() as db:
        assert db.get(PassportPublication, users["athlete"]["athlete_id"]) is None


def test_certificate_unauthorized_and_unrelated_users_are_denied(env):
    client, factory, h, users, rid = own_result(env)
    login = ok(
        client.post(
            "/api/auth/login",
            json={"email": "athlete17@demo.example", "password": "DemoPass2026!"},
        )
    )
    outsider = {
        "Authorization": "Bearer " + login["access_token"],
        "X-Active-Role": "athlete",
    }
    for suffix in ["", ".pdf"]:
        path = f"/api/results/{rid}/certificate{suffix}"
        assert client.get(path).status_code in {401, 403}
        for headers in [outsider, h["judge"], h["coach"]]:
            assert client.get(path, headers=headers).status_code == 403
        assert client.get(path, headers=h["admin"]).status_code == 200
    profile = ok(
        client.get(
            f"/api/athlete-profiles/{users['athlete']['athlete_id']}", headers=outsider
        )
    )
    assert profile["results"]  # seeing a profile never grants access to its documents
    assert (
        client.get(f"/api/results/{rid}/certificate.pdf", headers=outsider).status_code
        == 403
    )


def test_coach_certificate_access_tracks_active_link_and_discipline(env):
    client, factory, h, users = env
    with factory() as db:
        coach = db.scalar(select(Coach).where(Coach.user_id == users["coach"]["id"]))
        link = db.scalar(
            select(AthleteCoach).where(
                AthleteCoach.coach_id == coach.id,
                AthleteCoach.status == "active",
                AthleteCoach.discipline_id == 1,
            )
        )
        result = db.scalar(
            select(CompetitionResult)
            .join(Competition, Competition.id == CompetitionResult.competition_id)
            .where(
                CompetitionResult.athlete_id == link.athlete_id,
                Competition.discipline_id == 1,
                Competition.state == "published",
            )
        )
        rid = result.id
        linkid = link.id
    for suffix in ["", ".pdf"]:
        assert (
            client.get(
                f"/api/results/{rid}/certificate{suffix}", headers=h["coach"]
            ).status_code
            == 200
        )
    with factory() as db:
        link = db.get(AthleteCoach, linkid)
        link.status = "paused"
        db.add(
            AthleteCoach(
                coach_id=link.coach_id,
                athlete_id=link.athlete_id,
                discipline_id=2,
                status="active",
            )
        )
        db.commit()
    assert (
        client.get(f"/api/results/{rid}/certificate", headers=h["coach"]).status_code
        == 403
    )
    assert (
        client.get(
            f"/api/results/{rid}/certificate.pdf", headers=h["coach"]
        ).status_code
        == 403
    )
    row = next(
        r for r in ok(client.get("/api/results", headers=h["coach"])) if r["id"] == rid
    )
    assert not row["can_download_certificate"]


def test_certificate_keeps_historical_version_when_protocol_changes(env):
    client, factory, h, users, rid = own_result(env)
    old = ok(client.get(f"/api/results/{rid}/certificate", headers=h["athlete"]))
    with factory() as db:
        cid = db.get(CompetitionResult, rid).competition_id
    comp = ok(client.get(f"/api/competitions/{cid}", headers=h["admin"]))
    rows = [
        {key: r[key] for key in ["athlete_id", "place", "score", "team_name"]}
        for r in comp["results"]
    ]
    for row in rows:
        row["score"] += 2
    ok(
        client.put(
            f"/api/competitions/{cid}/results",
            headers=h["admin"],
            json={"results": rows, "reason": "Уточнение результата"},
        )
    )
    latest = ok(client.get(f"/api/results/{rid}/certificate", headers=h["athlete"]))
    historic = ok(
        client.get(
            f"/api/results/{rid}/certificate?version={old['version']}",
            headers=h["athlete"],
        )
    )
    assert (
        latest["version"] == old["version"] + 1
        and latest["entry"]["score"] == old["entry"]["score"] + 2
    )
    assert (
        not historic["is_current"]
        and historic["entry"]["score"] == old["entry"]["score"]
    )
    assert historic["certificate_number"] != latest["certificate_number"]
    assert (
        ok(
            client.get(
                "/api/public/certificates/" + old["verification_path"].rsplit("/", 1)[1]
            )
        )["status"]
        == "replaced"
    )
    assert (
        ok(
            client.get(
                "/api/public/certificates/"
                + latest["verification_path"].rsplit("/", 1)[1]
            )
        )["status"]
        == "confirmed"
    )
    assert (
        client.get(
            f"/api/results/{rid}/certificate.pdf?version={old['version']}",
            headers=h["athlete"],
        ).status_code
        == 200
    )


def test_unpublished_results_and_invalid_versions_have_no_certificate(env):
    client, factory, h, users = env
    cid, ids = closed_comp(client, h, factory, 1)
    with factory() as db:
        result = CompetitionResult(
            competition_id=cid, athlete_id=ids[0], place=1, score=10
        )
        db.add(result)
        db.commit()
        rid = result.id
    assert (
        client.get(f"/api/results/{rid}/certificate", headers=h["admin"]).status_code
        == 409
    )
    assert (
        client.get(
            f"/api/results/{rid}/certificate.pdf", headers=h["admin"]
        ).status_code
        == 409
    )
    client, factory, h, users, rid = own_result(env)
    assert (
        client.get(
            f"/api/results/{rid}/certificate?version=999", headers=h["athlete"]
        ).status_code
        == 404
    )
    assert (
        client.get(
            f"/api/results/{rid}/certificate?version=0", headers=h["athlete"]
        ).status_code
        == 422
    )


def test_certificate_qr_targets_minimal_public_check(env, monkeypatch):
    client, _, h, _, rid = own_result(env)
    import app.routers.passports as router

    seen = []
    monkeypatch.setattr(
        router,
        "pdf_document",
        lambda data, url, **kwargs: seen.append((data, url, kwargs)) or b"%PDF-test",
    )
    assert (
        client.get(
            f"/api/results/{rid}/certificate.pdf",
            headers={**h["athlete"], "Host": "evil.invalid"},
        ).status_code
        == 200
    )
    from app.config import settings

    data, url, kwargs = seen[0]
    assert (
        url == settings.public_base_url + data["verification_path"]
        and "/check-certificate/" in url
    )
    assert kwargs["private_access"] and "/verify/" not in url and "/p/" not in url


def test_public_certificate_is_minimal_anonymous_and_not_a_document_permission(env):
    client, _, h, _, rid = own_result(env)
    private = ok(client.get(f"/api/results/{rid}/certificate", headers=h["athlete"]))
    token = private["verification_path"].rsplit("/", 1)[1]
    response = client.get("/api/public/certificates/" + token)
    data = ok(response)
    assert set(data) == {
        "certificate_number",
        "status",
        "competition_title",
        "version",
        "published_at",
    }
    assert (
        data["status"] == "confirmed"
        and data["certificate_number"] == private["certificate_number"]
    )
    assert data["competition_title"] == private["competition"]["title"]
    assert private["entry"]["full_name"] not in response.text
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert "noindex" in response.headers["x-robots-tag"]
    for path in [
        f"/api/results/{rid}/certificate",
        f"/api/results/{rid}/certificate.pdf",
    ]:
        assert client.get(path, params={"token": token}).status_code in {401, 403}
        assert (
            client.get(path, headers={"Authorization": "Bearer " + token}).status_code
            == 401
        )
    replacement = token[:-1] + ("0" if token[-1] != "0" else "1")
    for invalid in [
        replacement,
        str(rid),
        "FSP-CERT-1-V1",
        "0.1." + "a" * 64,
        "9" * 100 + ".1." + "a" * 64,
    ]:
        assert client.get("/api/public/certificates/" + invalid).status_code == 404


def test_public_certificate_reports_withdrawn_results_without_personal_data(env):
    client, factory, h, _, rid = own_result(env)
    data = ok(client.get(f"/api/results/{rid}/certificate", headers=h["athlete"]))
    token = data["verification_path"].rsplit("/", 1)[1]
    with factory() as db:
        comp = db.get(Competition, db.get(CompetitionResult, rid).competition_id)
        comp.state = "closed"
        db.commit()
    check = ok(client.get("/api/public/certificates/" + token))
    assert check["status"] == "invalid"
    assert check["competition_title"] is None and check["published_at"] is None
    assert data["entry"]["full_name"] not in str(check)
