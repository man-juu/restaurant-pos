# UX review: design principles and current status

Every screen is checked against two standard lists before it ships:
**Shneiderman's 8 Golden Rules of Interface Design** and **Nielsen's 10 Usability Heuristics** (nngroup.com/articles/ten-usability-heuristics). Reference design systems worth studying (all open source, mature and widely used; read for patterns, nothing copied): GitLab **Pajamas**, Shopify **Polaris**, IBM **Carbon** (data-dense dashboards and tables), **Radix** primitives (already used for accessible dialogs and menus) and the Odoo POS flows (see `research/open-source-review.md`).

Status: ✅ in place, 🔧 fixed in this review, 🔜 planned (slice or phase).

## Shneiderman's 8 Golden Rules

| Rule | How the app follows it | Status |
| --- | --- | --- |
| 1. Strive for consistency | One token set for colour, type and spacing; one button, field, card and badge component; one error format from the API, translated in one place | ✅ |
| 2. Seek universal usability | EN/ID; dark, light and system modes; 44 px touch targets; keyboard focus ring; AA contrast; phone, tablet and desktop layouts; reduced-motion respected | ✅ |
| 3. Offer informative feedback | Translated error messages; buttons show "Please wait…" while working; renewal banner | 🔧 pending labels added |
| 4. Design dialogs to yield closure | 2FA setup ends on an explicit "I saved them" step; sign-in ends on the dashboard | ✅ |
| 5. Prevent errors | Show-password toggle; JSON-only sign-in; server-side validation; read-only mode blocks writes with a clear message; dependency checks before switching modules | 🔧 show-password added |
| 6. Permit easy reversal of actions | "Use a different account" leaves the 2FA step; sessions can be revoked; business documents use reversals, not deletes | 🔧 way back added |
| 7. Keep users in control | Theme, language and background are user choices; nothing auto-submits; destructive admin actions need explicit status changes | ✅ |
| 8. Reduce short-term memory load | Active business always visible in the top bar; navigation shows only what the user can use; recovery codes shown in a list to copy | ✅ |

## Nielsen's 10 heuristics

| Heuristic | Status and notes |
| --- | --- |
| 1. Visibility of system status | ✅ pending states, subscription state, active business. 🔜 offline indicator (Phase 4 offline mode) |
| 2. Match with the real world | ✅ restaurant terms (outlet, HPP, central kitchen), Indonesian copy written for owners, IDR formatting |
| 3. User control and freedom | 🔧 exit from 2FA; ✅ dismissible banner; 🔜 undo for row edits where documents allow it |
| 4. Consistency and standards | ✅ shared components; platform conventions (Escape closes dialogs, Radix) |
| 5. Error prevention | ✅ see rule 5; 🔜 confirmation for irreversible admin actions in the admin UI |
| 6. Recognition rather than recall | ✅ labelled fields, visible navigation, swatch previews |
| 7. Flexibility and efficiency | 🔜 keyboard shortcuts and quick search for back-office power users (Phase 1 tables) |
| 8. Aesthetic and minimalist design | ✅ calm palette, one accent, empty states instead of fake numbers |
| 9. Help users recover from errors | ✅ plain-language messages that say what to do ("Try the newest code") |
| 10. Help and documentation | 🔜 context help and in-app changelog (FR-X-007, Phase 3) |

## Checklist per new screen

1. Uses only tokens and shared components; works in dark and light mode.
2. Every action shows progress and a result; every error says what to do next.
3. A way back from every step; destructive actions confirm or can be reversed.
4. Phone, tablet and desktop checked (Playwright projects); no horizontal scroll.
5. EN and ID strings; no hard-coded text (lint rule).
6. Security and performance checks pass (CLAUDE.md, Workflow).
