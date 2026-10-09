from app.core.invariants import register_invariant
from app.core.modules import ModuleManifest
from app.modules.production import permissions
from app.modules.production.invariants import output_value_matches_input
from app.modules.production.prep_router import router as prep_router
from app.modules.production.router import router

# docs/05 ledger invariants, checked nightly.
register_invariant("I-3 production value", output_value_matches_input)

MANIFEST = ModuleManifest(
    name="production",
    depends_on=("inventory", "catalog"),
    routers=(router, prep_router),
    permissions=permissions.ALL,
    role_templates=permissions.ROLE_TEMPLATES,
    nav=("production",),
)
