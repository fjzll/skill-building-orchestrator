# Ledger entry 000 — Conventions
date: 2026-07-04
session: bootstrap (design grill with Lili & Danny)
status: approved

## Decisions

1. **Naming convention.** Workflow skills: `<client>-<workflow>-<skill>`
   (e.g. `jpe-client-updates-draft-pack`, `jpe-desk-note-research`).
   Shared skills: `<client>-shared-<skill>` (e.g. `jpe-shared-holder-identity`).
2. **Unit of a run** is one capability workflow, not one slice.
3. **Grill order**: shared skills first, then workflows in Decision Lens rank order.
   One workflow per session, fresh context; this ledger is the complete
   inter-session state.
4. **Splits are decided in dialogue**, never autonomously. Pre-grill pass
   computes facts only; hypotheses are formed live in-session from facts + this
   ledger. Cut lines (human gates, shared foundations) generate hypotheses.
5. **Proposals are derived views of this ledger.** Modifying a proposal means
   amending the ledger. Cosmetic changes = direct edit + addendum entry.
   Structural changes = targeted re-grill.
6. **Builder is autonomous** and cannot change the contract; boundary problems
   become structural change requests.
7. **Eval gates**: Layer 1 (deterministic) and Layer 2 (fact grounding) at 100%;
   Layer 3 (LLM judge rubric) threshold per proposal. Judge is calibrated
   against human verdicts before it gates alone.
8. **Cross-cutting client rules (JPE)**: no automatic sending; keep the personal
   adviser voice (must not read as AI); Front Office is the record; controlled
   access first.

## Ledger protocol

- Files are numbered `NNN-<slug>.md`, append-only. Never rewrite an approved entry;
  correct via a later addendum entry that references it.
- Each grill session writes its own entry as its final act; human approval of
  that entry is the session exit gate.
- Entry frontmatter: date, session, status (draft | approved).
