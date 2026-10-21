from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update

from lingard_db.models import AuditLog, User

PIN = "613470"


async def test_sign_in_and_generic_errors(api) -> None:  # type: ignore[no-untyped-def]
    await api.admin_token("Founder", PIN)
    wrong = await api.sign_in("Founder", "730264")
    unknown = await api.sign_in("Nobody", "730264")
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json()["detail"] == unknown.json()["detail"]
    ok = await api.sign_in("FOUNDER", PIN)
    assert ok.status_code == 200 and ok.json()["role"] == "admin"


async def test_lockout_escalates_then_requires_admin_reset(api) -> None:  # type: ignore[no-untyped-def]
    api.settings.rate_limit_per_name_per_minute = 1000  # isolate lockout from rate limiting
    api.settings.rate_limit_per_ip_per_minute = 1000
    admin = await api.admin_token()
    created = await api.client.post("/v1/admin/users", json={"display_name": "Amina"}, headers=api.bearer(admin))
    learner_id, one_time = created.json()["user_id"], created.json()["one_time_pin"]

    async def fail_five() -> None:
        for _ in range(5):
            assert (await api.sign_in("Amina", "730264" if one_time != "730264" else "195837")).status_code == 401

    async def expire_lock() -> None:
        async with api.state.sessions() as db:
            await db.execute(
                update(User)
                .where(User.name_key == "amina")
                .values(locked_until=datetime.now(UTC) - timedelta(seconds=1))
            )
            await db.commit()

    for expected_minutes in (1, 5, 30):
        await fail_five()
        async with api.state.sessions() as db:
            user = (await db.execute(select(User).where(User.name_key == "amina"))).scalar_one()
            remaining = user.locked_until - datetime.now(UTC)
            assert timedelta(minutes=expected_minutes - 1) < remaining <= timedelta(minutes=expected_minutes)
        assert (await api.sign_in("Amina", one_time)).status_code == 401  # correct PIN still refused while locked
        await expire_lock()

    await fail_five()
    async with api.state.sessions() as db:
        assert (await db.execute(select(User.requires_admin_reset).where(User.name_key == "amina"))).scalar_one()
    assert (await api.sign_in("Amina", one_time)).status_code == 401

    reset = await api.client.post(f"/v1/admin/users/{learner_id}/reset-pin", headers=api.bearer(admin))
    new_pin = reset.json()["one_time_pin"]
    signed = await api.sign_in("Amina", new_pin)
    assert signed.status_code == 200 and signed.json()["pin_change_required"] is True
    token = signed.json()["access_token"]
    assert (await api.client.get("/v1/me", headers=api.bearer(token))).status_code == 403
    changed = await api.client.post(
        "/v1/auth/change-pin", json={"current_pin": new_pin, "new_pin": "195837"}, headers=api.bearer(token)
    )
    assert changed.status_code == 204
    assert (await api.client.get("/v1/me", headers=api.bearer(token))).status_code == 403, "the old token still holds"
    renewed = await api.client.post("/v1/auth/refresh", json={"refresh_token": signed.json()["refresh_token"]})
    assert renewed.json()["pin_change_required"] is False, "the app renews this session's token after the change"
    assert (await api.client.get("/v1/me", headers=api.bearer(renewed.json()["access_token"]))).status_code == 200
    fresh = await api.sign_in("Amina", "195837")
    assert fresh.json()["pin_change_required"] is False
    assert (await api.client.get("/v1/me", headers=api.bearer(fresh.json()["access_token"]))).status_code == 200

    async with api.state.sessions() as db:
        actions = [a for a in (await db.execute(select(AuditLog.action))).scalars()]
        details = " ".join(str(d) for d in (await db.execute(select(AuditLog.detail))).scalars())
    assert {"lockout", "lockout_admin_reset_required", "pin_reset_by_admin", "pin_changed"} <= set(actions)
    for secret in (PIN, one_time, new_pin, "195837"):
        assert secret not in details


async def test_refresh_rotation_and_reuse_detection(api) -> None:  # type: ignore[no-untyped-def]
    await api.admin_token()
    first = (await api.sign_in("Founder", PIN)).json()
    rotated = await api.client.post("/v1/auth/refresh", json={"refresh_token": first["refresh_token"]})
    assert rotated.status_code == 200
    second = rotated.json()
    assert second["refresh_token"] != first["refresh_token"] and second["session_id"] == first["session_id"]
    replay = await api.client.post("/v1/auth/refresh", json={"refresh_token": first["refresh_token"]})
    assert replay.status_code == 401
    after = await api.client.post("/v1/auth/refresh", json={"refresh_token": second["refresh_token"]})
    assert after.status_code == 401, "reuse of an old token revokes the whole device session"
    assert (await api.client.get("/v1/me", headers=api.bearer(second["access_token"]))).status_code == 401


async def test_refresh_requires_pin_after_reverify_window(api) -> None:  # type: ignore[no-untyped-def]
    from lingard_db.models import DeviceSession

    await api.admin_token()
    pair = (await api.sign_in("Founder", PIN)).json()
    async with api.state.sessions() as db:
        await db.execute(update(DeviceSession).values(pin_verified_at=datetime.now(UTC) - timedelta(days=31)))
        await db.commit()
    response = await api.client.post("/v1/auth/refresh", json={"refresh_token": pair["refresh_token"]})
    assert response.status_code == 401 and "PIN" in response.json()["detail"]


async def test_rate_limit_per_name(api) -> None:  # type: ignore[no-untyped-def]
    statuses = [(await api.sign_in("Ghost", "730264")).status_code for _ in range(11)]
    assert statuses[:10] == [401] * 10 and statuses[10] == 429


async def test_invites_single_use_and_name_uniqueness(api) -> None:  # type: ignore[no-untyped-def]
    admin = await api.admin_token("Ernest", PIN)
    invite = (await api.client.post("/v1/admin/invites", json={}, headers=api.bearer(admin))).json()["code"]
    weak = await api.client.post(
        "/v1/auth/redeem-invite", json={"invite_code": invite, "display_name": "Sami", "pin": "123456"}
    )
    assert weak.status_code == 422
    taken = await api.client.post(
        "/v1/auth/redeem-invite", json={"invite_code": invite, "display_name": "ＥＲＮＥＳＴ", "pin": "730264"}
    )
    assert taken.status_code == 409
    ok = await api.client.post(
        "/v1/auth/redeem-invite", json={"invite_code": invite, "display_name": "Sami", "pin": "730264"}
    )
    assert ok.status_code == 201 and ok.json()["role"] == "learner"
    again = await api.client.post(
        "/v1/auth/redeem-invite", json={"invite_code": invite, "display_name": "Lina", "pin": "195837"}
    )
    assert again.status_code == 400
    learner = ok.json()["access_token"]
    assert (await api.client.get("/v1/admin/users", headers=api.bearer(learner))).status_code == 403


async def test_change_pin_revokes_other_devices_and_ownership(api) -> None:  # type: ignore[no-untyped-def]
    await api.admin_token()
    phone = (await api.sign_in("Founder", PIN, "phone")).json()
    laptop = (await api.sign_in("Founder", PIN, "laptop")).json()
    sessions = await api.client.get("/v1/auth/sessions", headers=api.bearer(phone["access_token"]))
    assert {s["device_label"] for s in sessions.json()} >= {"phone", "laptop"}
    await api.client.post(
        "/v1/auth/change-pin", json={"current_pin": PIN, "new_pin": "195837"}, headers=api.bearer(phone["access_token"])
    )
    assert (await api.client.get("/v1/me", headers=api.bearer(laptop["access_token"]))).status_code == 401
    assert (await api.client.get("/v1/me", headers=api.bearer(phone["access_token"]))).status_code == 200


async def test_learner_cannot_revoke_someone_elses_session(api) -> None:  # type: ignore[no-untyped-def]
    admin = await api.admin_token()
    created = (
        await api.client.post("/v1/admin/users", json={"display_name": "Lina"}, headers=api.bearer(admin))
    ).json()
    learner = (await api.sign_in("Lina", created["one_time_pin"])).json()
    admin_session = (await api.sign_in("Founder", PIN)).json()["session_id"]
    response = await api.client.delete(
        f"/v1/auth/sessions/{admin_session}", headers=api.bearer(learner["access_token"])
    )
    assert response.status_code in (403, 404)


async def test_curriculum_review_admin_flow(api) -> None:  # type: ignore[no-untyped-def]
    from lingard_curriculum.seed import load_seed, seed_graph

    await seed_graph(api.state.curriculum, load_seed(api.settings.content_root, "fr"))
    admin = await api.admin_token()
    nodes = await api.client.get(
        "/v1/admin/curriculum", params={"language": "fr", "kind": "grammar", "band": 7}, headers=api.bearer(admin)
    )
    assert any(n["key"] == "fr.grammar.si_imparfait" for n in nodes.json())
    off = await api.client.post(
        "/v1/admin/curriculum/fr.grammar.si_imparfait/review", params={"reviewed": False}, headers=api.bearer(admin)
    )
    assert off.json()["reviewed"] is False
    playable = await api.state.curriculum.nodes("fr", kinds=["grammar"], band=7)
    assert "fr.grammar.si_imparfait" not in {n.key for n in playable}


WEB = {"X-Lingard-Client": "web"}


async def test_web_refresh_token_is_an_httponly_cookie(api) -> None:  # type: ignore[no-untyped-def]
    await api.admin_token()
    signed_in = await api.client.post("/v1/auth/sign-in", json={"display_name": "Founder", "pin": PIN}, headers=WEB)
    assert signed_in.status_code == 200 and signed_in.json()["refresh_token"] is None
    cookie = signed_in.headers["set-cookie"].lower()
    assert "lingard_refresh=" in cookie and "httponly" in cookie and "samesite=strict" in cookie
    assert "path=/v1/auth" in cookie

    # a reload: no body, only the cookie the browser kept
    first = api.client.cookies.get("lingard_refresh")
    reloaded = await api.client.post("/v1/auth/refresh", headers=WEB)
    assert reloaded.status_code == 200 and reloaded.json()["refresh_token"] is None
    assert api.client.cookies.get("lingard_refresh") not in (None, first), "the cookie rotates like the token"
    access = reloaded.json()["access_token"]
    assert (await api.client.get("/v1/me", headers=api.bearer(access))).status_code == 200

    signed_out = await api.client.post("/v1/auth/sign-out", headers={**WEB, **api.bearer(access)})
    assert signed_out.status_code == 204 and api.client.cookies.get("lingard_refresh") is None
    assert (await api.client.post("/v1/auth/refresh", headers=WEB)).status_code == 401


async def test_cookie_alone_cannot_refresh(api) -> None:  # type: ignore[no-untyped-def]
    """Without the custom header (which a cross-site page can't send past CORS) the cookie is ignored."""
    await api.admin_token()
    await api.client.post("/v1/auth/sign-in", json={"display_name": "Founder", "pin": PIN}, headers=WEB)
    assert api.client.cookies.get("lingard_refresh")
    assert (await api.client.post("/v1/auth/refresh")).status_code == 401


async def test_failed_web_refresh_clears_the_cookie(api) -> None:  # type: ignore[no-untyped-def]
    await api.admin_token()
    await api.client.post("/v1/auth/sign-in", json={"display_name": "Founder", "pin": PIN}, headers=WEB)
    api.client.cookies.clear()
    api.client.cookies.set("lingard_refresh", "x" * 40)
    failed = await api.client.post("/v1/auth/refresh", headers=WEB)
    cleared = failed.headers["set-cookie"].lower()
    assert failed.status_code == 401 and "lingard_refresh=" in cleared
    assert "max-age=0" in cleared and "path=/v1/auth" in cleared


async def test_cors_allows_credentials_and_the_client_header(api) -> None:  # type: ignore[no-untyped-def]
    preflight = await api.client.options(
        "/v1/auth/refresh",
        headers={
            "Origin": "http://localhost:8081",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "x-lingard-client",
        },
    )
    assert preflight.headers["access-control-allow-credentials"] == "true"
    assert "x-lingard-client" in preflight.headers["access-control-allow-headers"].lower()
    evil = await api.client.options(
        "/v1/auth/refresh",
        headers={
            "Origin": "https://evil.example",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "x-lingard-client",
        },
    )
    assert "access-control-allow-origin" not in evil.headers


async def test_operator_reset_pin_replaces_it_and_signs_out_devices(api) -> None:  # type: ignore[no-untyped-def]
    await api.admin_token("Founder", "613470")
    await api.state.auth.operator_reset_pin("founder", "502817")
    assert (await api.sign_in("Founder", "613470")).status_code == 401
    assert (await api.sign_in("Founder", "502817")).status_code == 200
    async with api.state.sessions() as db:
        actions = (await db.execute(select(AuditLog.action))).scalars().all()
    assert "pin_reset_by_operator" in actions
