"""NFR-011: module manifests, dependency order and import boundaries."""

import pytest

import app.modules
from app.core.modules import ManifestError, ModuleManifest, discover, sort_by_dependency
from tests.boundaries import find_violations


def test_dependencies_come_first() -> None:
    ordered = sort_by_dependency(
        [
            ModuleManifest("purchasing", depends_on=("inventory",)),
            ModuleManifest("inventory", depends_on=("catalog",)),
            ModuleManifest("catalog"),
        ]
    )
    assert [m.name for m in ordered] == ["catalog", "inventory", "purchasing"]


def test_unknown_dependency_is_rejected() -> None:
    with pytest.raises(ManifestError, match="unknown module 'catalog'"):
        sort_by_dependency([ModuleManifest("inventory", depends_on=("catalog",))])


def test_dependency_cycle_is_rejected() -> None:
    with pytest.raises(ManifestError, match="cycle"):
        sort_by_dependency(
            [ModuleManifest("a", depends_on=("b",)), ModuleManifest("b", depends_on=("a",))]
        )


def test_app_modules_respect_declared_dependencies() -> None:
    assert find_violations("app", discover(app.modules)) == []


def test_undeclared_cross_module_import_is_detected() -> None:
    """The acceptance check for slice 0.2: a deliberate cross-module import must fail."""
    import tests.fakeapp.modules as fake

    violations = find_violations("tests", discover(fake), modules_pkg="fakeapp.modules")
    assert len(violations) == 1
    assert violations[0].startswith("sales imports undeclared module inventory")
