import pytest


@pytest.mark.asyncio
async def test_health_endpoint(client):
    resp = await client.get("/healthz")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "version" in data
