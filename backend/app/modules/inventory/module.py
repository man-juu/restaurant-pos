from app.core.invariants import register_invariant
from app.core.modules import ModuleManifest
from app.core.notifications.service import register_scanner
from app.core.subledger import register_subledger
from app.modules.catalog.interface import set_cost_source
from app.modules.inventory import permissions
from app.modules.inventory.alert_scan import scan_stock
from app.modules.inventory.doc_router import router as doc_router
from app.modules.inventory.import_router import router as import_router
from app.modules.inventory.invariants import (
    average_not_negative,
    balances_match_movements,
    transfers_net_zero,
)
from app.modules.inventory.level_router import router as level_router
from app.modules.inventory.location_router import router as location_router
from app.modules.inventory.planning_router import router as planning_router
from app.modules.inventory.queries import stock_value_total, tenant_unit_costs
from app.modules.inventory.report_router import router as report_router
from app.modules.inventory.router import router

# Recipe costing (FR-CAT-007) uses the moving average costs kept here.
set_cost_source(tenant_unit_costs)
# FR-INV-012: stock alerts run in the alerts job.
register_scanner(scan_stock)
# Gate 3: the stock ledger's value should match the inventory account.
register_subledger("inventory", "inventory", "stock_value", stock_value_total)


# docs/05 ledger invariants, checked nightly.
register_invariant("I-1 balances = movements", balances_match_movements)
register_invariant("I-2 average >= 0", average_not_negative)
register_invariant("I-4 transfers net zero", transfers_net_zero)

MANIFEST = ModuleManifest(
    name="inventory",
    depends_on=("catalog",),
    routers=(
        router,
        doc_router,
        import_router,
        level_router,
        location_router,
        planning_router,
        report_router,
    ),
    permissions=permissions.ALL,
    role_templates=permissions.ROLE_TEMPLATES,
    nav=("inventory",),
)
