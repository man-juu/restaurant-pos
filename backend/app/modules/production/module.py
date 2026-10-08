from app.core.modules import ModuleManifest
from app.modules.production import permissions
from app.modules.production.prep_router import router as prep_router
from app.modules.production.router import router

MANIFEST = ModuleManifest(
    name="production",
    depends_on=("inventory", "catalog"),
    routers=(router, prep_router),
    permissions=permissions.ALL,
    role_templates=permissions.ROLE_TEMPLATES,
    nav=("production",),
)
