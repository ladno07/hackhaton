import pytest


def test_coach_invites_by_public_id(env):
    client, _, headers, users = env
    athlete_id = users["athlete"]["athlete_id"]
    payload = {"athlete_public_id": f" fsp-{athlete_id:06d} ", "discipline_id": 1}
    response = client.post("/api/links", headers=headers["coach"], json=payload)
    assert response.status_code == 201, response.text
    link = response.json()
    assert link["athlete_id"] == athlete_id
    assert link["status"] == "pending"
    assert client.post("/api/links", headers=headers["coach"], json=payload).status_code == 409
    assert client.patch(
        f"/api/links/{link['id']}", headers=headers["athlete"], json={"status": "active"}
    ).status_code == 200


@pytest.mark.parametrize("public_id, status", [("123", 422), ("", 422), ("FSP-999999", 404)])
def test_invalid_public_id_does_not_create_link(env, public_id, status):
    client, _, headers, _ = env
    before = client.get("/api/links", headers=headers["coach"]).json()
    response = client.post("/api/links", headers=headers["coach"], json={
        "athlete_public_id": public_id, "discipline_id": 1,
    })
    assert response.status_code == status, response.text
    assert client.get("/api/links", headers=headers["coach"]).json() == before
