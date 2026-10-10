"""Access control for every route (CLAUDE.md rule 2, docs/03 section 1, docs/06 section 4).

Usage in a router:

    @router.get("/items", dependencies=[...])
    async def list_items(p: Annotated[Principal, Depends(require("catalog.item.view"))]): ...

Checks, in the documented order: session -> tenant membership -> subscription state ->
module enabled -> permission -> outlet scope (via Principal helpers, per object).

Deny by default: `assert_all_routes_declared` runs at start-up and refuses to boot if any
route has neither `require(...)` nor `public()`, so a forgotten check cannot ship.
"""

import uuid
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, FastAPI, Request
from fastapi.routing import APIRoute
from sqlalchemy import text

from app.core.access.permissions import CORE_MODULES, Registry
from app.core.access.subscription import WRITE_BLOCKED, SubscriptionInfo, effective_state
from app.core.errors import AppError, ForbiddenError, NotFoundError
from app.core.identity.deps import SAFE_METHODS, AuthContext, require_session
from app.core.tenancy import tenant_session


class NoActiveTenant(AppError):
    status_code, code = 403, "no_active_tenant"


class PermissionDenied(AppError):
    status_code, code = 403, "permission_denied"


class ModuleDisabled(AppError):
    status_code, code = 403, "module_disabled"


class SubscriptionBlocked(AppError):
    status_code = 403
    code = "subscription_read_only"


@dataclass(frozen=True)
class Principal:
    """Who is calling and what they may do in the active tenant."""

    auth: AuthContext
    tenant_id: uuid.UUID
    membership_id: uuid.UUID
    role_id: uuid.UUID
    permissions: frozenset[str]
    limits: dict[str, int | None]
    all_outlets: bool
    outlet_ids: frozenset[uuid.UUID]
    enabled_modules: frozenset[str]
    subscription_state: str
    subscription: SubscriptionInfo | None
    # Owner's per-outlet module switches (outlet, module) that are OFF, and the module of the
    # route being served: an outlet whose module is off looks like one the caller cannot see.
    modules_off: frozenset[tuple[uuid.UUID, str]] = frozenset()
    tenant_outlets: frozenset[uuid.UUID] = frozenset()
    module: str | None = None

    @property
    def user_id(self) -> uuid.UUID:
        return self.auth.user_id

    def can(self, permission: str) -> bool:
        return permission in self.permissions

    def can_access_outlet(self, outlet_id: uuid.UUID) -> bool:
        if self.module is not None and (outlet_id, self.module) in self.modules_off:
            return False
        return self.all_outlets or outlet_id in self.outlet_ids

    def visible_outlets(self) -> list[uuid.UUID] | None:
        """Outlets this route may cover; None = every outlet of the tenant (no switch off)."""
        if self.all_outlets and not any(m == self.module for _, m in self.modules_off):
            return None
        pool = self.tenant_outlets if self.all_outlets else self.outlet_ids
        return sorted(o for o in pool if self.can_access_outlet(o))

    def require_outlet(self, outlet_id: uuid.UUID) -> None:
        """404, not 403: an out-of-scope outlet looks like one that does not exist."""
        if not self.can_access_outlet(outlet_id):
            raise NotFoundError()


_PRINCIPAL_SQL = text("""
    SELECT m.id AS membership_id, m.role_id, m.scope,
           ARRAY(SELECT rp.permission_code FROM role_permissions rp
                 WHERE rp.role_id = m.role_id ORDER BY rp.permission_code) AS permission_codes,
           ARRAY(SELECT rp.limit_value FROM role_permissions rp
                 WHERE rp.role_id = m.role_id ORDER BY rp.permission_code) AS limit_values,
           ARRAY(SELECT mo.outlet_id FROM membership_outlets mo
                 WHERE mo.membership_id = m.id) AS outlet_ids,
           ARRAY(SELECT tm.module FROM tenant_modules tm WHERE tm.enabled) AS modules,
           ARRAY(SELECT om.outlet_id::text || ':' || om.module
                 FROM outlet_modules_off om) AS modules_off,
           ARRAY(SELECT o.id FROM outlets o) AS tenant_outlets,
           s.plan_type, s.ends_at, s.grace_days, s.reminders_enabled, s.reminder_days, s.suspended
    FROM memberships m
    LEFT JOIN subscriptions s ON s.tenant_id = m.tenant_id
    WHERE m.user_id = :user_id AND m.status = 'active'
""")


async def load_principal(request: Request, auth: AuthContext) -> Principal:
    if auth.tenant_id is None:
        raise NoActiveTenant()
    sessions = request.app.state.sessionmaker
    async with tenant_session(sessions, auth.tenant_id, auth.user_id) as db:
        # One round trip for the whole access picture (runs on every protected request).
        # RLS still scopes every subquery to the current tenant.
        row = (await db.execute(_PRINCIPAL_SQL, {"user_id": auth.user_id})).one_or_none()
    if row is None:
        raise NoActiveTenant()
    grants = list(zip(row.permission_codes or [], row.limit_values or [], strict=True))
    sub_row = row if row.plan_type is not None else None
    sub = (
        SubscriptionInfo(
            plan_type=sub_row.plan_type,
            ends_at=sub_row.ends_at,
            grace_days=sub_row.grace_days,
            reminders_enabled=sub_row.reminders_enabled,
            reminder_days=tuple(sub_row.reminder_days or ()),
            suspended=sub_row.suspended,
        )
        if sub_row
        else None
    )
    return Principal(
        auth=auth,
        tenant_id=auth.tenant_id,
        membership_id=row.membership_id,
        role_id=row.role_id,
        permissions=frozenset(code for code, _ in grants),
        limits=dict(grants),
        all_outlets=row.scope == "all",
        outlet_ids=frozenset(row.outlet_ids or ()),
        enabled_modules=frozenset(row.modules or ()) | CORE_MODULES,
        subscription_state=effective_state(sub, datetime.now(UTC)),
        subscription=sub,
        modules_off=frozenset(_off(x) for x in row.modules_off or ()),
        tenant_outlets=frozenset(row.tenant_outlets or ()),
    )


def _off(pair: str) -> tuple[uuid.UUID, str]:
    outlet, module = pair.split(":", 1)
    return uuid.UUID(outlet), module


def require(permission: str) -> Callable[[Request], Awaitable[Principal]]:
    """Dependency enforcing the full check chain for one permission."""

    async def dependency(request: Request) -> Principal:
        registry: Registry = request.app.state.permission_registry
        auth = await require_session(request)
        principal = await load_principal(request, auth)
        state = principal.subscription_state
        if state == "suspended":
            raise SubscriptionBlocked("tenant_suspended")
        if state in WRITE_BLOCKED and request.method not in SAFE_METHODS:
            raise SubscriptionBlocked()  # FR-SUB-003/004: view and export still work
        module = registry.module_of(permission)
        if module not in principal.enabled_modules:
            raise ModuleDisabled(details={"module": module})
        if not principal.can(permission):
            raise PermissionDenied(details={"permission": permission})
        return replace(principal, module=module)

    dependency.access_rule = ("permission", permission)  # type: ignore[attr-defined]
    return dependency


def require_member() -> Callable[[Request], Awaitable[Principal]]:
    """Signed in with an active tenant, no specific permission (e.g. /me/capabilities)."""

    async def dependency(request: Request) -> Principal:
        principal = await load_principal(request, await require_session(request))
        if principal.subscription_state == "suspended":
            raise SubscriptionBlocked("tenant_suspended")
        return principal

    dependency.access_rule = ("member", None)  # type: ignore[attr-defined]
    return dependency


async def _public() -> None:
    return None


_public.access_rule = ("public", None)  # type: ignore[attr-defined]


def public() -> Callable[[], Awaitable[None]]:
    """Marks a route as intentionally reachable without a permission (sign-in, health).
    Such routes must do their own checks."""
    return _public


def include(app: FastAPI, router: APIRouter, prefix: str = "") -> None:
    """Include a router and remember it, so start-up can verify every route's access rule
    without relying on FastAPI internals (included routes are resolved lazily)."""
    app.include_router(router, prefix=prefix)
    app.state.__dict__.setdefault("included_routers", []).append((prefix, router))


def _walk(dependant: Any) -> list[tuple[str, Any]]:
    found: list[tuple[str, Any]] = []
    stack = [dependant]
    while stack:
        current = stack.pop()
        rule = getattr(current.call, "access_rule", None)
        if rule is not None:
            found.append(rule)
        stack.extend(current.dependencies)
    return found


def _router_rules(router: APIRouter) -> list[tuple[str, Any]]:
    return [
        rule
        for dep in router.dependencies
        if (rule := getattr(dep.dependency, "access_rule", None)) is not None
    ]


def _all_routes(app: FastAPI) -> Iterable[tuple[str, APIRoute, list[tuple[str, Any]]]]:
    """(full path, route, access rules) for every API route of the app."""
    for route in app.router.routes:
        if isinstance(route, APIRoute):  # declared directly on the app
            yield route.path, route, _walk(route.dependant)
    for prefix, router in app.state.__dict__.get("included_routers", []):
        inherited = _router_rules(router)
        for route in router.routes:
            if isinstance(route, APIRoute):
                yield prefix + route.path, route, inherited + _walk(route.dependant)


def undeclared_routes(app: FastAPI, registry: Registry) -> list[str]:
    problems = []
    for path, route, rules in _all_routes(app):
        label = f"{','.join(sorted(route.methods or ()))} {path}"
        if not rules:
            problems.append(f"{label}: no require(...) or public()")
        for kind, permission in rules:
            if kind == "permission" and not registry.is_known(permission):
                problems.append(f"{label}: unknown permission {permission!r}")
    return problems


def assert_all_routes_declared(app: FastAPI, registry: Registry) -> None:
    problems = undeclared_routes(app, registry)
    if problems:
        raise RuntimeError("Routes without an access rule:\n" + "\n".join(problems))


def permissions_by_route(app: FastAPI) -> Iterable[tuple[str, APIRoute, str]]:
    """(full path, route, permission) for every permission-protected route."""
    for path, route, rules in _all_routes(app):
        for kind, permission in rules:
            if kind == "permission":
                yield path, route, permission


__all__ = ["ForbiddenError", "Principal", "public", "require"]
