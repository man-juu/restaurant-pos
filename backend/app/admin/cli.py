"""Admin command line (run inside the API container or a venv with ADMIN_DATABASE_URL set).

    python -m app.admin.cli create-admin you@example.com "Your Name" super_admin
    python -m app.admin.cli subscription-job

The first super admin can only be created here: there is deliberately no sign-up endpoint.
The daily subscription job is scheduled by the worker/cron in slice 0.8.
"""

import argparse
import asyncio
import getpass
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import create_async_engine

from app.admin.models import AdminUser
from app.admin.service import run_subscription_job
from app.core.config import get_settings
from app.core.db import create_sessionmaker
from app.core.identity.passwords import hash_password, validate_new_password


async def _create_admin(email: str, name: str, role: str) -> None:
    password = getpass.getpass("Password (min 12 characters): ")
    validate_new_password(password, privileged=True, email=email)
    settings = get_settings()
    engine = create_async_engine(str(settings.admin_database_url))
    async with create_sessionmaker(engine)() as db, db.begin():
        db.add(
            AdminUser(
                email=email, name=name, role=role, password_hash=await hash_password(password)
            )
        )
    await engine.dispose()
    print(f"Created {role} {email}. Sign in to set up two-factor authentication.")


async def _job() -> None:
    settings = get_settings()
    engine = create_async_engine(str(settings.admin_database_url))
    async with create_sessionmaker(engine)() as db, db.begin():
        changes = await run_subscription_job(db, datetime.now(UTC))
    await engine.dispose()
    print(f"Subscription job done: {len(changes)} state change(s).")


def main() -> None:
    parser = argparse.ArgumentParser(prog="app.admin.cli")
    sub = parser.add_subparsers(dest="command", required=True)
    create = sub.add_parser("create-admin")
    create.add_argument("email")
    create.add_argument("name")
    create.add_argument("role", choices=["super_admin", "support"])
    sub.add_parser("subscription-job")
    args = parser.parse_args()
    if args.command == "create-admin":
        asyncio.run(_create_admin(args.email, args.name, args.role))
    else:
        asyncio.run(_job())


if __name__ == "__main__":
    main()
