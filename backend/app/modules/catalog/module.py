from app.core.modules import ModuleManifest
from app.modules.catalog import permissions
from app.modules.catalog.router import router

MANIFEST = ModuleManifest(
    name="catalog",
    core=True,
    routers=(router,),
    permissions=permissions.ALL,
    role_templates=permissions.ROLE_TEMPLATES,
    nav=("catalog",),
)
