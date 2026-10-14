"""Learner-side LiveKit access tokens (publish microphone, subscribe to the NPC)."""

from __future__ import annotations

from datetime import timedelta

from livekit import api


def mint_learner_token(api_key: str, api_secret: str, room: str, identity: str, name: str) -> str:
    grants = api.VideoGrants(
        room_join=True, room=room, can_publish=True, can_subscribe=True, can_publish_sources=["microphone"]
    )
    return (
        api.AccessToken(api_key, api_secret)
        .with_identity(identity)
        .with_name(name)
        .with_grants(grants)
        .with_ttl(timedelta(minutes=45))
        .to_jwt()
    )
