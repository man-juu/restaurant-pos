from app.core.invariants import register_invariant
from app.core.modules import ModuleManifest
from app.modules.finance import permissions
from app.modules.finance.gl_router import router as gl_router
from app.modules.finance.ledger import unbalanced_entries
from app.modules.finance.router import router

# docs/05 ledger invariants, checked nightly: every posted journal entry is balanced.
register_invariant("I-5 balanced journals", unbalanced_entries)

MANIFEST = ModuleManifest(
    name="finance",
    depends_on=("sales", "inventory"),
    routers=(router, gl_router),
    permissions=permissions.ALL,
    role_templates=permissions.ROLE_TEMPLATES,
    nav=("finance",),
)
