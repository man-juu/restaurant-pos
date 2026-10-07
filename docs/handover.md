# Handover (2026-10-07)

Paste the message below into a new Claude Code session opened in the repo root.

---

You are continuing development of this Restaurant POS / ERP. Read CLAUDE.md first and follow it exactly; all specs are in docs/.

Branch: `claude/restaurant-pos-project-acc8ep` (PR #1). Do NOT merge any PR; the owner merges.
Commits: author "Michael Julian" only; no co-author or AI attribution lines.

Done:
- Phase 0 complete (tooling, backend skeleton, RLS tenancy, sign-in + 2FA, permissions, platform admin, frontend shell, deploy).
- 1a tenant settings (FR-TEN-004 to 009).
- 1b part 1 catalog backend: units, categories, items, translations, conversions (FR-CAT-001, 002, 008, 009), migration 0007.
- Complexity limits: ruff C90/PLR09, complexipy <= 15, ESLint complexity/sonarjs/max-lines; tests/test_structure.py (backend files <= 400 lines, standard module files).
- Legacy app reviewed and deleted (docs/existing-code-review.md has kept ideas and order/table screen rules for Phase 2).

Owner decisions (docs/09 changelog 0.17 to 0.20):
- Add-ons/modifiers (FR-CAT-003) and per-outlet overrides (FR-TEN-011) moved to Phase 2; add-ons are normal menu items for now.
- Channel prices = list prices with start dates; promos are discount lines on sales; order-total-only records are allocated by list price (slice 1k).
- AI images only if free (ADR-022): show a usage counter and block at 85% of the free limit plus a per-tenant cap.
- Menu photos and supplier invoice attachments optional by default, configurable to mandatory later.

Next (docs/tasks/phase-1.md):
1. 1b part 2: channels + channel prices with start dates (FR-CAT-004).
2. 1b part 3: upload engine (menu/ingredient photos, login background).
3. 1b part 4: free AI images with counter.
4. 1b part 5: catalog screens (EN/ID, phone/tablet/desktop, docs/ux-review.md).
5. Then 1c recipes/BOM and onward.

Every change: security check + performance check before push (CLAUDE.md workflow), update docs/security-practices.md and the docs/09 changelog. Ask the owner before new dependencies, data-model changes beyond docs/05, or destructive actions.

Open follow-ups: permission backfill command for existing tenants before the first real tenant; pin images/actions by digest; dedicated backup DB role.

The owner reads on a phone: keep replies short, details in files.
