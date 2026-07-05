---
workflow: <workflow-id>
client: JPE
status: proposed        # proposed | changes-requested | revised | confirmed | building | tested | build-failed
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
| # | Open item | Blocks build? (yes / proceed-under-assumption) |
|---|---|---|

## Test definition
- Fixtures:
- Layer 1 checks:
- Layer 2 number sources:
- Layer 3 rubric criteria + threshold:
- Gold standard comparison:

## Build order
1. shared deps first…
