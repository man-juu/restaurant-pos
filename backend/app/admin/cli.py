"""Admin command line (run inside the API container or a venv with ADMIN_DATABASE_URL set).

    python -m app.admin.cli create-admin you@example.com "Your Name" super_admin
    python -m app.admin.cli subscription-job
    python -m app.admin.cli alerts-job
    python -m app.admin.cli invariants-job   # nightly ledger checks (docs/05 I-1 to I-4)
    python -m app.admin.cli sync-roles   # after a release with new modules or permissions

The first super admin can only be created here: there is deliberately no sign-up endpoint.
The daily subscription job is scheduled by the worker/cron in slice 0.8.
"""

import argparse
import asyncio
import getpass
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import create_async_engine

from app.admin.alerts_job import active_tenants, record_failures, run_alerts, run_invariants
from app.admin.models import AdminUser
from app.admin.service import run_subscription_job, sync_roles
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


async def _scan(job: str) -> None:
    """List tenants with the platform role, run the job as the app role, record failures."""
    settings = get_settings()
    admin = create_async_engine(str(settings.admin_database_url))
    async with create_sessionmaker(admin)() as db:
        tenants = await active_tenants(db)
    engine = create_async_engine(str(settings.database_url))  # the app role: RLS applies
    run = run_alerts if job == "alerts" else run_invariants
    failed = await run(tenants, create_sessionmaker(engine))
    await engine.dispose()
    if failed:
        async with create_sessionmaker(admin)() as db, db.begin():
            await record_failures(db, job, failed)
    await admin.dispose()
    print(f"{job} job done: {len(tenants)} tenant(s), {len(failed)} with problems.")


async def _sync_roles() -> None:
    """Give existing tenants the permissions of modules released after they were created."""
    settings = get_settings()
    engine = create_async_engine(str(settings.admin_database_url))
    async with create_sessionmaker(engine)() as db, db.begin():
        added = await sync_roles(db)
    await engine.dispose()
    print(f"Role sync done: {added} permission grant(s) added.")


def main() -> None:
    parser = argparse.ArgumentParser(prog="app.admin.cli")
    sub = parser.add_subparsers(dest="command", required=True)
    create = sub.add_parser("create-admin")
    create.add_argument("email")
    create.add_argument("name")
    create.add_argument("role", choices=["super_admin", "support"])
    sub.add_parser("subscription-job")
    sub.add_parser("alerts-job")
    sub.add_parser("invariants-job")
    sub.add_parser("sync-roles")
    args = parser.parse_args()
    if args.command == "create-admin":
        asyncio.run(_create_admin(args.email, args.name, args.role))
    elif args.command == "alerts-job":
        asyncio.run(_scan("alerts"))
    elif args.command == "invariants-job":
        asyncio.run(_scan("invariants"))
    elif args.command == "sync-roles":
        asyncio.run(_sync_roles())
    else:
        asyncio.run(_job())


if __name__ == "__main__":
    main()
