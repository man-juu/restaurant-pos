from app.core.modules import ModuleManifest

MANIFEST = ModuleManifest(name="inventory", depends_on=("catalog",))
