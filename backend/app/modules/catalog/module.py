from app.core.modules import ModuleManifest
from app.core.notifications.service import register_scanner
from app.modules.catalog import permissions
from app.modules.catalog.ai_images import router as ai_router
from app.modules.catalog.bom_router import router as bom_router
from app.modules.catalog.food_cost import scan_food_cost
from app.modules.catalog.import_router import router as import_router
from app.modules.catalog.photos import router as photo_router
from app.modules.catalog.platform_map import router as map_router
from app.modules.catalog.router import router

# FR-CAT-012: the alerts job checks food cost against targets.
register_scanner(scan_food_cost)

MANIFEST = ModuleManifest(
    name="catalog",
    core=True,
    routers=(router, bom_router, photo_router, ai_router, import_router, map_router),
    permissions=permissions.ALL,
    role_templates=permissions.ROLE_TEMPLATES,
    nav=("catalog",),
)
