"""Module registry (docs/04 sections 4 and 6).

Each module under `app.modules.<name>` exposes `MANIFEST` in its `module.py`. The registry
discovers them, checks that declared dependencies exist and have no cycles, and mounts the
routers under /api/v1. Per-tenant enable/disable (`tenant_modules`) is enforced by
app.core.access.policy on every request.
"""

import importlib
import pkgutil
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from types import ModuleType

from fastapi import APIRouter, FastAPI


@dataclass(frozen=True)
class ModuleManifest:
    name: str
    depends_on: tuple[str, ...] = ()
    core: bool = False  # core modules cannot be switched off (docs/02)
    routers: tuple[APIRouter, ...] = ()
    permissions: tuple[str, ...] = ()  # "module.resource.action" codes this module defines
    # Default grants per role template key (docs/03 section 4), e.g. {"manager": ("x.y.view",)}.
    # Owner and co-owner get every permission automatically.
    role_templates: dict[str, tuple[str, ...]] = field(default_factory=dict)
    nav: tuple[str, ...] = ()  # navigation entry keys for /me/capabilities
    settings_schema: type | None = None
    extra: dict[str, object] = field(default_factory=dict)


class ManifestError(RuntimeError):
    pass


def discover(package: ModuleType) -> list[ModuleManifest]:
    manifests = []
    for info in pkgutil.iter_modules(package.__path__):
        if not info.ispkg:
            continue
        mod = importlib.import_module(f"{package.__name__}.{info.name}.module")
        manifest = getattr(mod, "MANIFEST", None)
        if not isinstance(manifest, ModuleManifest):
            raise ManifestError(f"{info.name}/module.py must define MANIFEST: ModuleManifest")
        if manifest.name != info.name:
            raise ManifestError(f"{info.name}: MANIFEST.name is {manifest.name!r}")
        manifests.append(manifest)
    return sort_by_dependency(manifests)


def sort_by_dependency(manifests: Iterable[ModuleManifest]) -> list[ModuleManifest]:
    """Topological order (dependencies first); raises on unknown dependencies or cycles."""
    by_name = {m.name: m for m in manifests}
    ordered: list[ModuleManifest] = []
    state: dict[str, str] = {}  # "visiting" | "done"

    def visit(name: str, path: tuple[str, ...]) -> None:
        if state.get(name) == "done":
            return
        if state.get(name) == "visiting":
            raise ManifestError(f"dependency cycle: {' -> '.join((*path, name))}")
        if name not in by_name:
            raise ManifestError(f"{path[-1]} depends on unknown module {name!r}")
        state[name] = "visiting"
        for dep in by_name[name].depends_on:
            visit(dep, (*path, name))
        state[name] = "done"
        ordered.append(by_name[name])

    for name in sorted(by_name):
        visit(name, ())
    return ordered


def mount(
    app: FastAPI,
    manifests: Iterable[ModuleManifest],
    include: Callable[[FastAPI, APIRouter], None],
) -> None:
    """Module routers declare their full paths (/api/v1/<module>/...)."""
    for manifest in manifests:
        for router in manifest.routers:
            include(app, router)
