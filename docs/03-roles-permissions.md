# 03. Roles and Permissions

## 1. Model

- **Permission:** one atomic right written as `module.resource.action`, for example `inventory.adjustment.approve`.
- **Role:** a named bundle of permissions. Platform-provided role templates exist; a tenant can clone and edit them or create custom roles.
- **Scope:** every role assignment is either *tenant-wide* or limited to a *set of outlets*. A permission check always evaluates *permission and scope*.
- **Approval:** some actions need a second person. Approval rules (per document type and amount threshold) decide who may approve (FR-TEN-007).
- **Module gate:** a permission only works if its module is enabled for the tenant and the subscription is not read-only.

Order of evaluation on every request: authenticated session, tenant membership, subscription state, module enabled, permission, outlet scope, document-level rules (for example "cannot approve own request").

## 2. Platform roles (our side)

| Role | Purpose | Notes |
| --- | --- | --- |
| Super admin | Create tenants, set plans, modules, subscription, manage admins | Two-factor required. Few people. |
| Support | Help tenants | Read-only impersonation with stated reason; time-limited; logged and visible to the tenant owner |

Platform roles live in a separate admin area and a separate user table. They are never mixed with tenant users.

## 3. Tenant roles

### Owner

Exactly one primary owner per tenant (the billing contact). Can do everything, plus: delete the tenant, transfer ownership, see subscription details, manage co-owners. Two-factor required.

### Co-owner

Any number. Full operational and financial access across all outlets, including users, settings, modules visibility, approvals and reports. Cannot: delete the tenant, transfer ownership, remove the owner, or edit subscription contact. Two-factor required.

### Staff role templates

| Template | Typical person | Default scope |
| --- | --- | --- |
| Manager | Outlet or area manager | Assigned outlets |
| Cashier | Front counter | One outlet |
| Waiter | Floor staff | One outlet |
| Kitchen | Line cook, expediter | One outlet |
| Warehouse | Stock handler, central kitchen storekeeper | One outlet |
| Purchaser | Buyer | Tenant-wide |
| Accountant | Bookkeeper or external accountant | Tenant-wide, mostly read plus finance |
| Viewer | Investor, auditor | Tenant-wide, read-only |

Custom roles can combine any permissions.

## 4. Capability matrix (default templates)

Legend: **Y** allowed, **A** allowed but needs approval by rule, **O** own outlets only, **R** read only, **-** not allowed. Owner and co-owner columns apply to all outlets.

| Capability | Owner | Co-owner | Manager | Cashier | Waiter | Kitchen | Warehouse | Purchaser | Accountant | Viewer |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Manage users and roles | Y | Y | - | - | - | - | - | - | - | - |
| Manage outlets, tax, payment methods | Y | Y | - | - | - | - | - | - | - | - |
| Switch modules (within plan) | Y | Y | - | - | - | - | - | - | - | - |
| Subscription and billing info | Y | R | - | - | - | - | - | - | - | - |
| Delete tenant, transfer ownership | Y | - | - | - | - | - | - | - | - | - |
| Edit items, menu, recipes, prices | Y | Y | O | - | - | - | - | - | - | R |
| See item cost and margin | Y | Y | O | - | - | - | R | R | R | R |
| Take and edit POS orders | Y | Y | O | O | O | - | - | - | - | - |
| Apply discount (up to limit) | Y | Y | O | O | - | - | - | - | - | - |
| Void or refund | Y | Y | A | A | - | - | - | - | - | - |
| Open and close cash shift | Y | Y | O | O | - | - | - | - | R | - |
| Manage tables and reservations | Y | Y | O | O | O | - | - | - | - | - |
| Kitchen display actions | Y | Y | O | - | - | O | - | - | - | - |
| Record manual daily sales | Y | Y | O | O | - | - | - | - | - | - |
| Lock a sales day | Y | Y | O | - | - | - | - | - | - | - |
| Receive goods | Y | Y | O | - | - | - | O | O | - | - |
| Create purchase request or order | Y | Y | O | - | - | - | O | Y | - | - |
| Approve purchase order | Y | Y | A | - | - | - | - | - | - | - |
| Production orders | Y | Y | O | - | - | O | O | - | - | - |
| Request transfer | Y | Y | O | - | - | - | O | - | - | - |
| Approve and ship transfer | Y | Y | O | - | - | - | O | - | - | - |
| Receive transfer | Y | Y | O | - | - | - | O | - | - | - |
| Waste log | Y | Y | O | - | - | O | O | - | - | - |
| Stock count (enter) | Y | Y | O | - | - | O | O | - | - | - |
| Stock count and adjustment (approve) | Y | Y | A | - | - | - | - | - | - | - |
| Vendors and vendor prices | Y | Y | R | - | - | - | R | Y | R | R |
| Journals, expenses, period close | Y | Y | - | - | - | - | - | - | Y | R |
| Reports (own scope) | Y | Y | O | - | - | - | O | O | Y | R |
| Audit log | Y | Y | O | - | - | - | - | - | R | R |
| Export data | Y | Y | O | - | - | - | - | - | Y | - |

The matrix is the *default*. The source of truth is the permission list in the code (`backend/app/modules/*/permissions.py`), and a test checks this table stays in sync.

## 5. Permission naming

Format `module.resource.action`. Actions: `view`, `create`, `update`, `delete` (soft), `approve`, `post`, `reverse`, `export`, `configure`.

Examples:

| Permission | Meaning |
| --- | --- |
| `catalog.item.view` / `create` / `update` | See and edit items |
| `catalog.item.availability` | Mark a menu item sold out or back on sale (manager, cashier, kitchen) |
| `catalog.cost.view` | See item costs and margins |
| `inventory.count.create` / `approve` | Enter and approve stock counts |
| `inventory.adjustment.create` / `approve` | Manual adjustments |
| `purchasing.order.create` / `approve` | Purchase orders |
| `sales.order.create` / `void` / `refund` | POS orders |
| `tables.table.view` / `tables.table.setup` / `tables.session.manage` | See the floor; set up floors and tables (manager); seat, move, merge, split, mark clean (manager, cashier, waiter) |
| `sales.order.pay` | Take payment for a POS order (waiters take orders without it) |
| `sales.discount.apply` | Discounts up to the role's limit (default cashier 10 %, manager 50 %; Settings > Limits) |
| `sales.order.void` / `sales.order.refund` | Void with a reason; ask for or approve a refund (approval rule "refund", default manager) |
| `sales.shift.open` / `sales.shift.view` | Own cash shift; review every shift's expected cash and variance |
| `sales.discount.apply` | Discounts (with a per-role maximum percentage) |
| `sales.day.lock` | Lock a sales day |
| `finance.journal.post` / `reverse` | Manual journals |
| `finance.period.close` | Close an accounting period |
| `tenant.user.manage` | Invite, edit, deactivate users |
| `tenant.settings.configure` | Settings, tax, payment methods |
| `audit.log.view` | See the audit log |

## 6. Rules that always apply

1. Nobody can approve their own request, regardless of role.
2. Owners cannot be removed or demoted except through ownership transfer.
3. There is always at least one active owner per tenant.
4. A user's access to an outlet ends immediately when the assignment is removed (sessions are re-evaluated per request).
5. Cost and margin data are hidden from roles without `catalog.cost.view`, including in API responses, not only in the UI.
6. Role changes, invitations, PIN resets and permission overrides are written to the audit log.
7. Per-role limits (maximum discount %, maximum refund amount, maximum approval amount) are configurable and enforced on the server.

## 7. Approval rules (examples, all configurable)

| Document | Default rule |
| --- | --- |
| Purchase order | Above a tenant-set amount, owner or co-owner approves |
| Stock adjustment or count correction | Manager approves variance above a threshold; owner above a higher threshold |
| Void or refund | Manager approves after the order is paid |
| Discount | Cashier up to a role limit; manager above |
| Transfer discrepancy | Central kitchen manager approves |
| Manual journal | Owner or co-owner approves |

## 8. Sessions and devices

- Registered devices are named and revocable.
- POS devices may be locked to one outlet.
- PIN sign-in only works on a registered device after a full sign-in there (FR-IDN-004).
- Idle timeout and PIN re-prompt intervals are configurable within platform limits.
