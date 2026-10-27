from app.models import User


def test_own_and_guardian_consents_are_readable_and_downloadable(env):
    client, _, h, users = env
    response = client.get("/api/my/documents", headers=h["athlete"])
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    records = response.json()
    assert {r["id"] for r in records} == {"personal", "guardian"}
    for record in records:
        assert record["subject_name"] == users["athlete"]["full_name"]
        assert record["version"] == users["athlete"]["consent_version"]
        assert record["accepted_at"] and record["text"]
        detail = client.get(f"/api/my/documents/{record['id']}", headers=h["athlete"])
        assert detail.json() == record
        pdf = client.get(f"/api/my/documents/{record['id']}.pdf", headers=h["athlete"])
        assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF-")
        assert pdf.headers["content-type"] == "application/pdf"
        assert pdf.headers["cache-control"] == "no-store"
    guardian = next(r for r in records if r["id"] == "guardian")
    assert guardian["accepted_by"] == users["athlete"]["guardian_name"]


def test_documents_require_login_and_never_accept_another_user_id(env):
    client, _, h, users = env
    for path in ["", "/personal", "/personal.pdf", "/guardian", "/guardian.pdf"]:
        assert client.get("/api/my/documents" + path).status_code in {401, 403}
    # A supplied foreign ID must never select someone else's record.
    response = client.get(
        "/api/my/documents/personal",
        params={"user_id": users["athlete"]["id"]},
        headers=h["admin"],
    )
    assert response.json()["subject_name"] == users["admin"]["full_name"]
    assert users["athlete"]["guardian_name"] not in response.text
    assert client.get("/api/my/documents/guardian", headers=h["admin"]).status_code == 404
    assert client.get("/api/my/documents/guardian.pdf", headers=h["admin"]).status_code == 404
    assert client.get("/api/my/documents/unknown.pdf", headers=h["athlete"]).status_code == 404


def test_unknown_consent_version_does_not_fabricate_text(env):
    client, factory, h, users = env
    with factory() as db:
        db.get(User, users["athlete"]["id"]).consent_version = "legacy-unknown"
        db.commit()
    doc = client.get("/api/my/documents/personal", headers=h["athlete"]).json()
    assert doc["version"] == "legacy-unknown" and doc["text"] is None
    assert client.get("/api/my/documents/personal.pdf", headers=h["athlete"]).status_code == 200


def test_birth_date_is_available_only_in_authorized_profile_detail(env):
    client, _, h, users = env
    aid = users["athlete"]["athlete_id"]
    response = client.get(f"/api/athletes/{aid}", headers=h["athlete"])
    assert response.json()["birth_date"] == users["athlete"]["birth_date"]
    assert client.get(f"/api/athletes/{aid}", headers=h["judge"]).status_code == 403
    assert client.get(f"/api/athletes/{aid}").status_code in {401, 403}
    listed = client.get("/api/athletes", headers=h["admin"]).json()
    assert all("birth_date" not in athlete for athlete in listed)
