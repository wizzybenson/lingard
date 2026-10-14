"""FastAPI application factory. API is versioned under ``/v1``; OpenAPI is generated for the TS client."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from lingard_api.routes import admin, auth, economy, glance, learning, me, sessions, speech, studio, voice, world
from lingard_api.settings import Settings, get_settings
from lingard_api.state import AppState


def create_app(settings: Settings | None = None, state: AppState | None = None) -> FastAPI:
    config = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.lingard = state or AppState.build(config)
        if app.state.lingard.interactive is None:
            await app.state.lingard.start()
        try:
            yield
        finally:
            await app.state.lingard.close()

    app = FastAPI(title="Lingard API", version="1", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.cors_origins,
        allow_methods=["*"],
        allow_headers=["Authorization", "Content-Type"],
    )
    for module in (auth, me, admin, world, sessions, learning, economy, voice, glance, speech, studio):
        app.include_router(module.router)

    # Location artwork is original public content (tools/content_cli/art.py), so it needs no sign-in.
    app.mount("/v1/art", StaticFiles(directory=config.content_root / "art"), name="art")

    @app.get("/v1/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


load_dotenv()  # exports .env so provider SDKs that read os.environ (e.g. ANTHROPIC_API_KEY) see it
app = create_app()
