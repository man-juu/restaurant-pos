from app.core.modules import ModuleManifest
from app.modules.catalog import permissions
from app.modules.catalog.bom_router import router as bom_router
from app.modules.catalog.router import router

MANIFEST = ModuleManifest(
    name="catalog",
    core=True,
    routers=(router, bom_router),
    permissions=permissions.ALL,
    role_templates=permissions.ROLE_TEMPLATES,
    nav=("catalog",),
)
