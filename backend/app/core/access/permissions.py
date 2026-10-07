"""Permission registry and default role templates (docs/03 sections 3 to 5, FR-IDN-010).

Permissions are `module.resource.action`. Core permissions are defined here; each module adds
its own through `ModuleManifest.permissions` and `role_templates`. The code is the source of
truth; tenant roles are copies of these templates and can be edited per tenant.
"""

from collections.abc import Iterable
from dataclasses import dataclass, field

from app.core.modules import ModuleManifest

# Modules that are always on (docs/02 module map: Core rows). Their permissions never fail
# the module-enabled check.
CORE_MODULES = frozenset({"tenant", "audit", "identity", "subscription", "catalog", "imports"})

CORE_PERMISSIONS: dict[str, str] = {
    "tenant.user.manage": "Invite, edit and deactivate users; assign roles",
    "tenant.settings.configure": "Outlets, tax, payment methods and other settings",
    "tenant.settings.view": "See tax, service charge, payment methods and numbering",
    "tenant.module.configure": "Switch modules on or off within the plan",
    "tenant.subscription.view": "See subscription and billing information",
    "tenant.ownership.transfer": "Transfer ownership, assign the owner role, delete the tenant",
    "tenant.outlet.view": "See outlets",
    "tenant.data.export": "Export tenant data",
    "audit.log.view": "See the audit log",
}


@dataclass(frozen=True)
class RoleTemplate:
    key: str
    name: str  # default display name; tenants can rename their copy
    scope: str  # "all" or "outlets" (docs/03 section 3 default scope)
    requires_mfa: bool = False
    all_permissions: bool = False  # owner and co-owner
    exclude: frozenset[str] = frozenset()
    grants: frozenset[str] = field(default_factory=frozenset)


# Core grants per template; modules add theirs via role_templates.
_CORE_TEMPLATES = (
    RoleTemplate("owner", "Owner", "all", requires_mfa=True, all_permissions=True),
    RoleTemplate(
        "co_owner",
        "Co-owner",
        "all",
        requires_mfa=True,
        all_permissions=True,
        # docs/03: co-owner cannot delete the tenant or transfer ownership; subscription is R.
        exclude=frozenset({"tenant.ownership.transfer"}),
    ),
    RoleTemplate(
        "manager",
        "Manager",
        "outlets",
        grants=frozenset(
            {"tenant.outlet.view", "tenant.settings.view", "audit.log.view", "tenant.data.export"}
        ),
    ),
    RoleTemplate(
        "cashier",
        "Cashier",
        "outlets",
        grants=frozenset({"tenant.outlet.view", "tenant.settings.view"}),
    ),
    RoleTemplate("waiter", "Waiter", "outlets", grants=frozenset({"tenant.outlet.view"})),
    RoleTemplate("kitchen", "Kitchen", "outlets", grants=frozenset({"tenant.outlet.view"})),
    RoleTemplate("warehouse", "Warehouse", "outlets", grants=frozenset({"tenant.outlet.view"})),
    RoleTemplate("purchaser", "Purchaser", "all", grants=frozenset({"tenant.outlet.view"})),
    RoleTemplate(
        "accountant",
        "Accountant",
        "all",
        grants=frozenset(
            {"tenant.outlet.view", "tenant.settings.view", "audit.log.view", "tenant.data.export"}
        ),
    ),
    RoleTemplate(
        "viewer", "Viewer", "all", grants=frozenset({"tenant.outlet.view", "audit.log.view"})
    ),
)


class PermissionError_(ValueError):
    pass


@dataclass(frozen=True)
class Registry:
    permissions: frozenset[str]
    templates: dict[str, frozenset[str]]  # template key -> granted permission codes
    template_info: dict[str, RoleTemplate]

    def module_of(self, permission: str) -> str:
        return permission.split(".", 1)[0]

    def is_known(self, permission: str) -> bool:
        return permission in self.permissions


def _module_permissions(manifests: list[ModuleManifest]) -> set[str]:
    codes: set[str] = set()
    for m in manifests:
        for code in m.permissions:
            if code.split(".", 1)[0] != m.name or code.count(".") != 2:
                raise PermissionError_(
                    f"{m.name}: permission {code!r} must be '{m.name}.resource.action'"
                )
            codes.add(code)
    return codes


def build_registry(manifests: Iterable[ModuleManifest]) -> Registry:
    manifests = list(manifests)
    codes = set(CORE_PERMISSIONS) | _module_permissions(manifests)
    info = {t.key: t for t in _CORE_TEMPLATES}
    templates: dict[str, frozenset[str]] = {}
    for t in _CORE_TEMPLATES:
        if t.all_permissions:
            templates[t.key] = frozenset(codes - t.exclude)
            continue
        granted = set(t.grants)
        for m in manifests:
            for key, perms in m.role_templates.items():
                if key not in info:
                    raise PermissionError_(f"{m.name}: unknown role template {key!r}")
                if key == t.key:
                    granted.update(perms)
        unknown = granted - codes
        if unknown:
            raise PermissionError_(f"template {t.key}: unknown permissions {sorted(unknown)}")
        templates[t.key] = frozenset(granted)
    return Registry(frozenset(codes), templates, info)
