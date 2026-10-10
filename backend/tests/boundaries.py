"""Module boundary check (docs/04 module rule 1, NFR-011).

A module may import only `app.core` and the modules it declares in `depends_on`. The manifest
is the single source of truth, so no import-linter contract has to be written per module.
Lives in tests/ because grimp (from import-linter) is a dev dependency.
"""

from collections.abc import Iterable

import grimp

from app.core.modules import ModuleManifest


def find_violations(
    package: str, manifests: Iterable[ModuleManifest], modules_pkg: str = "modules"
) -> list[str]:
    graph = grimp.build_graph(package, include_external_packages=False)
    base = f"{package}.{modules_pkg}."
    violations = []
    for manifest in manifests:
        allowed = {manifest.name, *manifest.depends_on}
        own = f"{base}{manifest.name}"
        for importer in sorted(graph.find_descendants(own) | {own}):
            for imported in sorted(graph.find_modules_directly_imported_by(importer)):
                if not imported.startswith(base):
                    continue
                target = imported[len(base) :].split(".")[0]
                if target not in allowed:
                    violations.append(
                        f"{manifest.name} imports undeclared module {target} "
                        f"({importer} -> {imported})"
                    )
    return violations
