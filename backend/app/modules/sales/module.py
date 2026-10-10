from app.core.modules import ModuleManifest
from app.core.subledger import register_subledger
from app.modules.sales import permissions
from app.modules.sales.offline_router import router as offline_router
from app.modules.sales.platform_import_router import router as platform_import_router
from app.modules.sales.pos_actions_router import router as pos_actions_router
from app.modules.sales.pos_router import router as pos_router
from app.modules.sales.receipt_router import router as receipt_router
from app.modules.sales.report_router import router as report_router
from app.modules.sales.router import router
from app.modules.sales.shift_router import router as shift_router
from app.modules.sales.wholesale import open_receivables_total
from app.modules.sales.wholesale_router import router as wholesale_router

# Gate 3: open wholesale invoices should match accounts receivable.
register_subledger("sales", "receivable", "open_invoices", open_receivables_total)

MANIFEST = ModuleManifest(
    name="sales",
    depends_on=("inventory", "catalog"),
    routers=(
        router,
        report_router,
        pos_router,
        offline_router,
        platform_import_router,
        pos_actions_router,
        receipt_router,
        shift_router,
        wholesale_router,
    ),
    permissions=permissions.ALL,
    role_templates=permissions.ROLE_TEMPLATES,
    limit_units=permissions.LIMIT_UNITS,
    role_limits=permissions.ROLE_LIMITS,
    nav=("pos", "sales"),
    nav_permissions={"pos": permissions.ORDER_CREATE, "sales": permissions.DAY_VIEW},
)
