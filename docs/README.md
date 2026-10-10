# Restaurant POS / ERP: Documentation

**Status:** v0.2 approved 2026-10-07. **Date:** 2026-10-07. **Owner:** Michael Julian.

Working name: *Restaurant POS*. A multi-tenant, modular POS and back-office ERP for restaurants, cloud kitchens and central-kitchen groups, Indonesia first.

## How to read these docs

| # | Document | Answers |
| --- | --- | --- |
| 01 | [Product spec](01-product-spec.md) | What are we building, for whom, and what is out of scope? |
| 02 | [Functional spec](02-functional-spec.md) | What exactly must each module do? (numbered requirements) |
| 03 | [Roles and permissions](03-roles-permissions.md) | Who can do what: platform admin, owner, co-owner, staff? |
| 04 | [Architecture](04-architecture.md) | How is it structured, and why? |
| 05 | [Data model](05-data-model.md) | What is stored, with which rules and invariants? |
| 06 | [Security and compliance](06-security-compliance.md) | How do we keep tenants safe and legal? |
| 07 | [Infrastructure and cost](07-infrastructure-cost.md) | Where does it run, and what does it cost? |
| 08 | [Roadmap and engineering](08-roadmap-engineering.md) | In what order do we build, and how do we keep quality? |
| 09 | [Decisions and open questions](09-decisions-open-questions.md) | What is decided, what is not, what do I need from you? |

## Review process

1. Read 01 and 09 first. Answer the open questions in 09.
2. Review 02 to 08 in any order; comment per requirement ID (for example `FR-INV-014`).
3. Each round produces a new version in the changelog at the bottom of 09.
4. Implementation starts only when every document is marked **Approved** below.

## Approval status

| Document | Version | Status |
| --- | --- | --- |
| 01 Product spec | 0.2 | Approved |
| 02 Functional spec | 0.2 | Approved |
| 03 Roles and permissions | 0.1 | Approved |
| 04 Architecture | 0.1 | Approved |
| 05 Data model | 0.1 | Approved |
| 06 Security and compliance | 0.1 | Approved |
| 07 Infrastructure and cost | 0.1 | Approved |
| 08 Roadmap and engineering | 0.2 | Approved |
| 09 Decisions and open questions | 0.2 | Approved |

## Conventions used in all documents

- **Requirement IDs:** `FR-<MODULE>-<NNN>` (functional), `NFR-<NNN>` (non-functional), `ADR-<NNN>` (decision), `Q-<NNN>` (open question).
- **Phase:** the release in which a requirement is delivered (1 to 4, see [08](08-roadmap-engineering.md)).
- **Must / should / may** follow RFC 2119 meaning.
- Money is stored as whole numbers in the smallest currency unit. IDR has no minor unit, so Rp 25.000 is stored as `25000`.
- Statements about laws, prices and third-party products were researched on 2026-10-07 and must be re-verified before launch. They are marked **(verify)**.

## Working with Claude Code

Copy `CLAUDE.md` to the repository root and this `docs/` folder into the repository. Claude Code loads `CLAUDE.md` automatically; it points to these documents and to `docs/tasks/phase-0.md`, which holds the starter prompt and the Phase 0 work order.

## Existing code

An earlier prototype exists in a private GitHub repository. It has not been reviewed yet (see Q-001 in 09). Nothing in these docs assumes its structure.
