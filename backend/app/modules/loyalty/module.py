from app.core.modules import ModuleManifest
from app.modules.loyalty import events, permissions
from app.modules.loyalty.router import router

events.register()

MANIFEST = ModuleManifest(
    name="loyalty",
    depends_on=("sales", "catalog"),
    routers=(router,),
    permissions=permissions.ALL,
    role_templates=permissions.ROLE_TEMPLATES,
    nav=("loyalty",),
)
