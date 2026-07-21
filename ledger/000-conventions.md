# Ledger entry 000 — Conventions

**Template note:** this entry ships as a genericized starting point. Fill in
`## Decisions` item 8 with this client's cross-cutting rules during the
bootstrap grill, and update the frontmatter below.

date: <bootstrap date>
session: bootstrap (design grill)
status: approved

## Decisions

1. **Naming convention.** Workflow skills: `<client>-<workflow>-<skill>`
   (for example, `<client>-client-updates-draft-pack`). Shared skills:
   `<client>-shared-<skill>` (for example, `<client>-shared-holder-identity`).
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
8. **Cross-cutting client rules** — client-specific, fill in at bootstrap grill
   (for example: required human approvals, voice or brand constraints, systems
   of record, and access controls).

## Ledger protocol

- Files are numbered `NNN-<slug>.md`, append-only. Never rewrite an approved entry;
  correct via a later addendum entry that references it.
- Each grill session writes its own entry as its final act; human approval of
  that entry is the session exit gate.
- Entry frontmatter: date, session, status (draft | approved).
- **Every entry includes a `## Rejected alternatives / why-nots` section**: the
  options considered and turned down, and why. Decisions carry between sessions
  automatically; the reasoning perimeter around them is lost unless written
  here. This is the mitigation for fresh-context nuance loss — builders and
  re-grill sessions read it so they don't re-litigate (or accidentally adopt)
  paths already ruled out. "None considered" is a valid entry, silence is not.
