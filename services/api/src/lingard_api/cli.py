"""Operator commands: ``python -m lingard_api.cli {migrate,seed,bootstrap-admin,reset-pin}``."""

from __future__ import annotations

import argparse
import asyncio
import getpass

from dotenv import load_dotenv

from lingard_api.auth.pin import WeakPinError
from lingard_api.auth.provider import AuthError
from lingard_api.settings import Settings
from lingard_api.state import AppState
from lingard_curriculum.seed import load_seed, seed_graph
from lingard_db.migrate import migrate as run_migrations


def migrate(settings: Settings, revision: str = "head") -> None:
    run_migrations(settings.database_url, settings.database_schema, revision)


async def seed(settings: Settings) -> dict[str, int]:
    state = AppState.build(settings)
    try:
        counts = {}
        for language in ("fr", "en"):
            counts[language] = await seed_graph(state.curriculum, load_seed(settings.content_root, language))
        return counts
    finally:
        await state.close()


async def bootstrap_admin(settings: Settings, name: str, pin: str) -> str:
    state = AppState.build(settings)
    try:
        return str(await state.auth.bootstrap_admin(name, pin))
    finally:
        await state.close()


async def reset_pin(settings: Settings, name: str, pin: str) -> str:
    state = AppState.build(settings)
    try:
        return str(await state.auth.operator_reset_pin(name, pin))
    finally:
        await state.close()


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(prog="lingard-api")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("migrate")
    sub.add_parser("seed")
    boot = sub.add_parser("bootstrap-admin")
    boot.add_argument("--name", required=True)
    reset = sub.add_parser("reset-pin", help="set a user's PIN (prompted, never echoed) and sign out their devices")
    reset.add_argument("--name", required=True)
    args = parser.parse_args()
    settings = Settings()
    if args.command == "migrate":
        migrate(settings)
    elif args.command == "seed":
        print(asyncio.run(seed(settings)))
    elif args.command == "reset-pin":
        pin = getpass.getpass("New PIN (6 digits): ")
        if getpass.getpass("Repeat it: ") != pin:
            raise SystemExit("PINs differ; nothing changed")
        try:
            print("PIN reset for:", asyncio.run(reset_pin(settings, args.name, pin)))
        except (WeakPinError, AuthError) as exc:
            raise SystemExit(f"Nothing changed: {exc}") from None
    else:
        pin = getpass.getpass("Admin PIN (6 digits): ")
        print("admin created:", asyncio.run(bootstrap_admin(settings, args.name, pin)))


if __name__ == "__main__":
    main()
