from datetime import date
from sqlalchemy import func, select
from app.models import AuditLog, IndicatorDocument
from tests.test_ministry import ministry_login

PDF = b"%PDF-1.4\n% confirming document\n%%EOF"


def test_registry_indicators_have_sources(env):
    client, factory, headers, users = env
    year = date.today().year
    res = client.get(
        f"/api/indicators?start_year={year - 1}&end_year={year}", headers=headers["admin"]
    )
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["years"] == [year - 1, year]
    keys = {r["key"] for r in data["registry"]}
    assert {"population", "ranked", "competitions", "judges"} <= keys
    assert all(r["source"] for r in data["registry"])
    population = next(r for r in data["registry"] if r["key"] == "population")
    totals = client.get(
        f"/api/reports/population?start_year={year - 1}&end_year={year}",
        headers=headers["admin"],
    ).json()["totals"]
    assert [v["value"] for v in population["values"]] == [t["count"] for t in totals]
    # demo: last year has an entered indicator with a statistical form attached
    form = next(e for e in data["entered"] if "1-ФК" in e["name"])
    assert form["year"] == year - 1 and form["documents"]


def test_entered_indicator_with_documents(env):
    client, factory, headers, users = env
    year = date.today().year - 1
    body = {
        "year": year,
        "name": "Тренеров с профильным образованием",
        "value": 12,
        "unit": "чел.",
        "source": "Отчёты организаций за год",
    }
    res = client.post("/api/indicators", json=body, headers=headers["admin"])
    assert res.status_code == 201, res.text
    ind = res.json()
    assert ind["documents"] == [] and ind["comment"] == ""

    no_source = client.post(
        "/api/indicators", json={**body, "source": ""}, headers=headers["admin"]
    )
    assert no_source.status_code == 422
    future = client.post(
        "/api/indicators", json={**body, "year": year + 5}, headers=headers["admin"]
    )
    assert future.status_code == 422

    url = f"/api/indicators/{ind['id']}/documents"
    up = client.post(
        url, files={"file": ("Отчёт клуба.pdf", PDF, "application/pdf")}, headers=headers["admin"]
    )
    assert up.status_code == 201, up.text
    doc = up.json()
    assert doc["filename"] == "Отчёт клуба.pdf" and doc["size"] == len(PDF)

    fake = client.post(
        url, files={"file": ("scan.png", PDF, "image/png")}, headers=headers["admin"]
    )
    assert fake.status_code == 422
    exe = client.post(
        url, files={"file": ("run.exe", b"MZ", "application/octet-stream")}, headers=headers["admin"]
    )
    assert exe.status_code == 422

    edit = client.put(
        f"/api/indicators/{ind['id']}", json={**body, "value": 14}, headers=headers["admin"]
    )
    assert edit.status_code == 200 and edit.json()["value"] == 14
    assert len(edit.json()["documents"]) == 1

    # ministry reads and downloads, but cannot change anything
    h = ministry_login(client)
    file = client.get(f"/api/indicator-documents/{doc['id']}", headers=h)
    assert file.status_code == 200 and file.content == PDF
    assert "filename*=UTF-8''" in file.headers["content-disposition"]
    assert client.post("/api/indicators", json=body, headers=h).status_code == 403
    assert client.delete(f"/api/indicator-documents/{doc['id']}", headers=h).status_code == 403
    # other roles do not see indicators at all
    assert client.get("/api/indicators", headers=headers["coach"]).status_code == 403
    assert (
        client.get(f"/api/indicator-documents/{doc['id']}", headers=headers["athlete"]).status_code
        == 403
    )

    assert client.delete(f"/api/indicators/{ind['id']}", headers=headers["admin"]).status_code == 204
    with factory() as db:
        assert db.get(IndicatorDocument, doc["id"]) is None
        actions = set(
            db.scalars(
                select(AuditLog.action).where(AuditLog.entity == "development_indicators")
            )
        )
    assert {
        "Добавление показателя развития",
        "Прикрепление документа к показателю",
        "Изменение показателя развития",
        "Удаление показателя развития",
    } <= actions


def test_indicators_export(env):
    client, factory, headers, users = env
    year = date.today().year
    for fmt in ("pdf", "docx", "xlsx"):
        res = client.get(
            f"/api/exports/indicators.{fmt}?start_year={year - 1}&end_year={year}",
            headers=headers["admin"],
        )
        assert res.status_code == 200, (fmt, res.text)
        assert len(res.content) > 1000
    long = client.get(
        f"/api/indicators?start_year={year - 40}&end_year={year}", headers=headers["admin"]
    )
    assert long.status_code == 422
