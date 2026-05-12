import httpx
import pytest

from smartervote_mcp.client import RacesApiClient, compact_options


@pytest.mark.asyncio
async def test_races_api_client_adds_auth_headers(monkeypatch):
    seen = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        seen["authorization"] = request.headers.get("authorization")
        seen["admin_key"] = request.headers.get("x-admin-key")
        return httpx.Response(200, json={"ok": True})

    class PatchedAsyncClient(httpx.AsyncClient):
        def __init__(self, *args, **kwargs):
            kwargs["transport"] = httpx.MockTransport(handler)
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", PatchedAsyncClient)
    client = RacesApiClient(base_url="http://races.test/", bearer_token="jwt", admin_key="key")

    assert await client.get("/health") == {"ok": True}
    assert seen == {"authorization": "Bearer jwt", "admin_key": "key"}


@pytest.mark.asyncio
async def test_races_api_client_raises_useful_error(monkeypatch):
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"detail": "Race not found"})

    class PatchedAsyncClient(httpx.AsyncClient):
        def __init__(self, *args, **kwargs):
            kwargs["transport"] = httpx.MockTransport(handler)
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", PatchedAsyncClient)
    client = RacesApiClient(base_url="http://races.test")

    with pytest.raises(RuntimeError, match="races-api 404 for GET /races/missing: Race not found"):
        await client.get("/races/missing")


def test_compact_options_keeps_false_and_drops_none():
    assert compact_options(cheap_mode=False, note=None, goal="refresh") == {"cheap_mode": False, "goal": "refresh"}
