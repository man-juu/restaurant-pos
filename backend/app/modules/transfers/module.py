from app.core.demand import register_demand
from app.core.modules import ModuleManifest
from app.modules.transfers import permissions
from app.modules.transfers.demand import open_requests
from app.modules.transfers.router import router

# The sending kitchen's prep list counts open requests (FR-PRD-008).
register_demand("transfers", open_requests)

MANIFEST = ModuleManifest(
    name="transfers",
    depends_on=("inventory", "catalog"),
    routers=(router,),
    permissions=permissions.ALL,
    role_templates=permissions.ROLE_TEMPLATES,
    nav=("transfers",),
)
