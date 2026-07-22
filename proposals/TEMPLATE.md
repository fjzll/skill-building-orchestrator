---
workflow: <workflow-id>
client: <CLIENT>        # client identifier
status: proposed        # proposed | changes-requested | revised | confirmed | building | tested | build-failed | blocked
version: 1
ledger_entries: [<NNN-slug>]
skills: [<client>-shared-<dep>, <client>-<workflow>-<skill>]   # build order: shared deps first — the conductor builds these
---

# Build proposal: <workflow name>

Derived view of ledger decisions — do not edit content here without a ledger amendment.

## Skills

### <client>-<workflow>-<skill-name>
- **Job:** one line
- **Trigger:**
- **Inputs → Outputs:**
- **Build-plan steps covered:** slice N steps X–Y
- **Shared dependencies:** <client>-shared-...
- **Human gate:** where it stops, who reviews

## Assumptions
| # | Assumption | Confirming Information Request |
|---|---|---|

## Blockers

Category: access / system / materials · Status: open / resolved / superseded.
The portal Blockers tab aggregates these rows across all proposals.

| # | Open item | Category | Status | Blocks build? (yes / proceed-under-assumption) |
|---|---|---|---|---|

## Test definition

Written and committed at grill exit as `skills/<skill>/eval/eval.yaml` plus its
fixtures — the portal renders those files inline here, and Confirm approves them
along with this prose. The conductor freezes their hash into `eval_hash` on
confirmation; no build or refine attempt may change them afterwards.

- Fixtures:
- Layer 1 checks:
- Layer 2 number sources:
- Layer 3 rubric criteria + threshold:
- Gold standard comparison:

## Build order
1. shared deps first…
