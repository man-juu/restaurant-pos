"""File-structure rules (CLAUDE.md layout): every module has the standard files, and no source
file grows past MAX_LINES (split by responsibility instead)."""

from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "app"
MODULE_FILES = {
    "models.py",
    "schemas.py",
    "service.py",
    "router.py",
    "events.py",
    "permissions.py",
    "module.py",
}
MAX_LINES = 400


def test_every_module_has_the_standard_files() -> None:
    modules = [p for p in (APP / "modules").iterdir() if (p / "__init__.py").exists()]
    missing = {
        m.name: sorted(MODULE_FILES - {f.name for f in m.iterdir()})
        for m in modules
        if MODULE_FILES - {f.name for f in m.iterdir()}
    }
    assert missing == {}


def test_no_source_file_is_too_long() -> None:
    long_files = {
        str(p.relative_to(APP)): n
        for p in APP.rglob("*.py")
        if (n := len(p.read_text().splitlines())) > MAX_LINES
    }
    assert long_files == {}
