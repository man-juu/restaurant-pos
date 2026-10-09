from app.core.modules import ModuleManifest
from app.modules.finance import permissions
from app.modules.finance.router import router

MANIFEST = ModuleManifest(
    name="finance",
    depends_on=("sales", "inventory"),
    routers=(router,),
    permissions=permissions.ALL,
    role_templates=permissions.ROLE_TEMPLATES,
    nav=("finance",),
)
