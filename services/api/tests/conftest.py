import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass

import httpx
import pytest

from lingard_api.cli import migrate
from lingard_api.main import create_app
from lingard_api.settings import Settings
from lingard_api.state import AppState


@dataclass
class Api:
    client: httpx.AsyncClient
    state: AppState
    settings: Settings

    async def admin_token(self, name: str = "Founder", pin: str = "613470") -> str:
        await self.state.auth.bootstrap_admin(name, pin)
        response = await self.client.post("/v1/auth/sign-in", json={"display_name": name, "pin": pin})
        assert response.status_code == 200, response.text
        return str(response.json()["access_token"])

    async def sign_in(self, name: str, pin: str, device: str = "phone") -> httpx.Response:
        return await self.client.post(
            "/v1/auth/sign-in", json={"display_name": name, "pin": pin, "device_label": device}
        )

    @staticmethod
    def bearer(token: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def api(pg_schema_factory) -> AsyncIterator[Api]:  # type: ignore[no-untyped-def]
    async with pg_schema_factory() as (url, schema):
        settings = Settings(
            env="test",
            database_url=url,
            database_schema=schema,
            redis_url=None,
            argon2_time_cost=1,
            argon2_memory_kib=8,
            argon2_parallelism=1,
        )
        await asyncio.to_thread(migrate, settings)
        state = AppState.build(settings)
        await state.start()
        app = create_app(settings, state)
        app.state.lingard = state
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            yield Api(client, state, settings)
        await state.close()
