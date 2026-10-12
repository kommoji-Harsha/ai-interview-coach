import pytest


@pytest.mark.asyncio
async def test_create_session(client, auth_headers):
    resp = await client.post(
        "/api/v1/sessions",
        json={
            "resume_text": "Experienced Python developer...",
            "jd_text": "Looking for a senior backend engineer...",
            "config": {"difficulty": "medium", "max_turns": 5},
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["status"] == "active"
    assert "first_question" in data
    assert data["first_question"]["content"]
    assert data["first_question"]["topic"]


@pytest.mark.asyncio
async def test_create_session_unauthorized(client):
    resp = await client.post("/api/v1/sessions", json={})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_respond_to_session(client, auth_headers):
    # Create session
    create_resp = await client.post(
        "/api/v1/sessions",
        json={
            "resume_text": "Experienced developer",
            "jd_text": "Backend role",
        },
        headers=auth_headers,
    )
    assert create_resp.status_code == 201
    session_id = create_resp.json()["id"]

    # Respond
    resp = await client.post(
        f"/api/v1/sessions/{session_id}/respond",
        json={"content": "In my previous role, I worked on distributed systems..."},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["role"] == "interviewer"
    assert data["content"]
    assert "turn_number" in data
    assert "topics_covered" in data
    assert "turns_remaining" in data


@pytest.mark.asyncio
async def test_respond_nonexistent_session(client, auth_headers):
    resp = await client.post(
        "/api/v1/sessions/00000000-0000-0000-0000-000000000000/respond",
        json={"content": "test"},
        headers=auth_headers,
    )
    assert resp.status_code == 404
