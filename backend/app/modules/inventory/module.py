from app.core.modules import ModuleManifest
from app.core.notifications.service import register_scanner
from app.modules.catalog.interface import set_cost_source
from app.modules.inventory import permissions
from app.modules.inventory.alert_scan import scan_stock
from app.modules.inventory.doc_router import router as doc_router
from app.modules.inventory.import_router import router as import_router
from app.modules.inventory.level_router import router as level_router
from app.modules.inventory.queries import tenant_unit_costs
from app.modules.inventory.router import router

# Recipe costing (FR-CAT-007) uses the moving average costs kept here.
set_cost_source(tenant_unit_costs)
# FR-INV-012: stock alerts run in the alerts job.
register_scanner(scan_stock)

MANIFEST = ModuleManifest(
    name="inventory",
    depends_on=("catalog",),
    routers=(router, doc_router, import_router, level_router),
    permissions=permissions.ALL,
    role_templates=permissions.ROLE_TEMPLATES,
    nav=("inventory",),
)
