from app.core.modules import ModuleManifest
from app.modules.sales import permissions
from app.modules.sales.pos_router import router as pos_router
from app.modules.sales.report_router import router as report_router
from app.modules.sales.router import router
from app.modules.sales.shift_router import router as shift_router

MANIFEST = ModuleManifest(
    name="sales",
    depends_on=("inventory", "catalog"),
    routers=(router, report_router, pos_router, shift_router),
    permissions=permissions.ALL,
    role_templates=permissions.ROLE_TEMPLATES,
    nav=("sales", "pos"),
)
