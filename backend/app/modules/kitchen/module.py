from app.core.modules import ModuleManifest
from app.modules.kitchen import events, permissions
from app.modules.kitchen.router import router

events.register()

MANIFEST = ModuleManifest(
    name="kitchen",
    depends_on=("sales", "catalog", "inventory"),
    routers=(router,),
    permissions=permissions.ALL,
    role_templates=permissions.ROLE_TEMPLATES,
    nav=("kitchen",),
)
