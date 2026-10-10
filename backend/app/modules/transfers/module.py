from app.core.demand import register_demand
from app.core.modules import ModuleManifest
from app.core.periodic import register_task
from app.modules.transfers import permissions, standing
from app.modules.transfers.demand import open_requests
from app.modules.transfers.router import router
from app.modules.transfers.standing_router import router as standing_router

# The sending kitchen's prep list counts open requests (FR-PRD-008).
register_demand("transfers", open_requests)
# FR-TRF-005: the worker turns standing orders into requests.
register_task("transfers", standing.run)

MANIFEST = ModuleManifest(
    name="transfers",
    depends_on=("inventory", "catalog"),
    routers=(standing_router, router),  # literal paths before /{transfer_id}
    permissions=permissions.ALL,
    role_templates=permissions.ROLE_TEMPLATES,
    nav=("transfers",),
)
