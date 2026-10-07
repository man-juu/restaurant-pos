"""Optional modules, their dependencies and per-profile defaults (docs/02 module map,
docs/01 section 3). Module code packages register later; the catalog lets the admin console
and tenants switch modules on with dependency checks before the code exists."""

from app.core.errors import AppError

OPTIONAL_MODULES: dict[str, tuple[str, ...]] = {
    "inventory": (),
    "purchasing": ("inventory",),
    "production": ("inventory",),
    "transfers": ("inventory",),
    "sales": (),
    "tables": ("sales",),
    "kitchen": ("sales",),
    "finance": (),
    "reports": (),
    "notifications": (),
}

PROFILE_DEFAULTS: dict[str, tuple[str, ...]] = {
    "restaurant": ("sales", "tables", "kitchen", "inventory", "purchasing", "finance", "reports"),
    "cloud_kitchen": ("sales", "inventory", "purchasing", "production", "finance", "reports"),
    "central_kitchen_group": (
        "inventory",
        "production",
        "transfers",
        "purchasing",
        "finance",
        "reports",
    ),
    "hybrid": ("sales", "inventory", "purchasing", "finance", "reports"),
}


class ModuleDependencyError(AppError):
    status_code, code = 422, "module_dependency_missing"


def validate_module_set(modules: set[str]) -> None:
    """FR-TEN-003: a module cannot be on unless its dependencies are on."""
    unknown = modules - OPTIONAL_MODULES.keys()
    if unknown:
        raise ModuleDependencyError("unknown_module", details={"modules": sorted(unknown)})
    missing = {f"{m}->{dep}" for m in modules for dep in OPTIONAL_MODULES[m] if dep not in modules}
    if missing:
        raise ModuleDependencyError(details={"missing": sorted(missing)})
