from app.core.modules import ModuleManifest

MANIFEST = ModuleManifest(name="sales", depends_on=("catalog",))
