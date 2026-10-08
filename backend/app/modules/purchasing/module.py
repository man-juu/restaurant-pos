from app.core.modules import ModuleManifest
from app.modules.purchasing import permissions
from app.modules.purchasing.router import router

MANIFEST = ModuleManifest(
    name="purchasing",
    depends_on=("inventory", "catalog"),
    routers=(router,),
    permissions=permissions.ALL,
    role_templates=permissions.ROLE_TEMPLATES,
    nav=("purchasing",),
)
