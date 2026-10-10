from app.core.invariants import register_invariant
from app.core.modules import ModuleManifest
from app.modules.finance import events, permissions
from app.modules.finance.budget_router import router as budget_router
from app.modules.finance.gl_router import router as gl_router
from app.modules.finance.ledger import unbalanced_entries
from app.modules.finance.prime_router import router as prime_router
from app.modules.finance.router import router
from app.modules.finance.settlement_router import router as settlement_router

# docs/05 ledger invariants, checked nightly: every posted journal entry is balanced.
register_invariant("I-5 balanced journals", unbalanced_entries)

events.register()

MANIFEST = ModuleManifest(
    name="finance",
    depends_on=("sales", "inventory", "catalog"),
    routers=(router, gl_router, settlement_router, prime_router, budget_router),
    permissions=permissions.ALL,
    role_templates=permissions.ROLE_TEMPLATES,
    nav=("finance",),
)
