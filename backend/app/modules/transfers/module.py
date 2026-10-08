from app.core.modules import ModuleManifest
from app.modules.transfers import permissions
from app.modules.transfers.router import router

MANIFEST = ModuleManifest(
    name="transfers",
    depends_on=("inventory", "catalog"),
    routers=(router,),
    permissions=permissions.ALL,
    role_templates=permissions.ROLE_TEMPLATES,
    nav=("transfers",),
)
