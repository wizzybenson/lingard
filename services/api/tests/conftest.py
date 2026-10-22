import asyncio
import io
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass

import av
import httpx
import numpy as np
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
            _env_file=None,
            env="test",
            database_url=url,
            database_schema=schema,
            redis_url=None,
            # Never the developer's running services, even when another test has loaded .env into the environment.
            pronunciation_url=None,
            object_store_url=None,
            voicebox_url=None,
            elevenlabs_api_key=None,
            openai_api_key=None,
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


def _m4a(seconds: float = 1.0) -> bytes:
    """AAC in MP4 at 44.1 kHz, as iOS and Android record."""
    buffer = io.BytesIO()
    with av.open(buffer, "w", format="mp4") as container:
        stream = container.add_stream("aac", rate=44_100)
        stream.layout = "mono"
        samples = (0.3 * np.sin(2 * np.pi * 220 * np.arange(int(44_100 * seconds)) / 44_100)).astype(np.float32)
        frame = av.AudioFrame.from_ndarray(samples.reshape(1, -1), format="fltp", layout="mono")
        frame.sample_rate = 44_100
        for packet in stream.encode(frame):
            container.mux(packet)
        for packet in stream.encode(None):
            container.mux(packet)
    return buffer.getvalue()


@pytest.fixture
def m4a() -> Callable[[float], bytes]:
    return _m4a
