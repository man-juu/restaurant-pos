from app.core.modules import ModuleManifest
from app.modules.purchasing import permissions
from app.modules.purchasing.order_router import router as order_router
from app.modules.purchasing.reorder_router import router as reorder_router
from app.modules.purchasing.report_router import router as report_router
from app.modules.purchasing.router import router

MANIFEST = ModuleManifest(
    name="purchasing",
    depends_on=("inventory", "catalog"),
    routers=(router, order_router, reorder_router, report_router),
    permissions=permissions.ALL,
    role_templates=permissions.ROLE_TEMPLATES,
    nav=("purchasing",),
)
