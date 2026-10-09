from app.core.modules import ModuleManifest
from app.modules.sales import permissions
from app.modules.sales.router import router

MANIFEST = ModuleManifest(
    name="sales",
    depends_on=("inventory", "catalog"),
    routers=(router,),
    permissions=permissions.ALL,
    role_templates=permissions.ROLE_TEMPLATES,
    nav=("sales",),
)
