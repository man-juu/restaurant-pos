from app.core.modules import ModuleManifest
from app.core.subledger import register_subledger
from app.modules.purchasing import permissions
from app.modules.purchasing.bill_router import router as bill_router
from app.modules.purchasing.bills import payables_total
from app.modules.purchasing.order_router import router as order_router
from app.modules.purchasing.reorder_router import router as reorder_router
from app.modules.purchasing.report_router import router as report_router
from app.modules.purchasing.return_router import router as return_router
from app.modules.purchasing.router import router

# Gate 3: open bills plus goods received on account should match accounts payable.
register_subledger("purchasing", "payable", "owed_to_vendors", payables_total)

MANIFEST = ModuleManifest(
    name="purchasing",
    depends_on=("inventory", "catalog"),
    routers=(router, order_router, reorder_router, report_router, return_router, bill_router),
    permissions=permissions.ALL,
    role_templates=permissions.ROLE_TEMPLATES,
    nav=("purchasing",),
)
