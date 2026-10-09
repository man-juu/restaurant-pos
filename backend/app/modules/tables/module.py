from app.core.modules import ModuleManifest
from app.modules.tables import events, permissions
from app.modules.tables.router import router

events.register()

MANIFEST = ModuleManifest(
    name="tables",
    depends_on=("sales", "inventory"),
    routers=(router,),
    permissions=permissions.ALL,
    role_templates=permissions.ROLE_TEMPLATES,
    nav=("tables",),
)
