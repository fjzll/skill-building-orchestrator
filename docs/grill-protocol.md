# Grill session protocol (per-workflow, fresh context)

One session per entry in `analysis/facts.yaml → grill_order`. Session 1 covers
shared-skill candidates; later sessions cover one capability workflow each.

## Seeding a session
Start a fresh Claude session (Cowork or Claude Code) with the grill-me skill and:
- `analysis/facts.yaml` (the deterministic facts pass)
- `ledger/*.md` (all approved entries — the complete state so far)
- the workflow's `build-plans/<slug>-*.yaml` and `deep-dives/<slug>-*.yaml` (slug from `client.yaml`)

## Session rules
1. Hypotheses are formed IN-SESSION from facts + ledger, never precomputed.
   Cut lines generate hypotheses: (a) cut at human gates — a skill is the longest
   uninterrupted AI segment between purple/red steps; (b) cut at shared foundations.
2. One question at a time, each with a recommended answer.
3. Gaps only the client can answer become Information Request items — the
   session never blocks on client input; it records an assumption + IR.
4. Naming per ledger 000: `<client>-<workflow>-<skill>` / `<client>-shared-<skill>`.
5. Exit act: write the ledger entry (decisions, splits, assumptions, IRs emitted,
   conventions added, **and a "Rejected alternatives / why-nots" section** — the
   options considered and turned down, with reasons; see ledger 000) and
   update/create the workflow's proposal from TEMPLATE.md.
   Human approval of the ledger entry is the exit gate.
6. Exit act, continued — **write the executable test suite**: one
   `skills/<skill>/eval/eval.yaml` per skill in the proposal, plus the fixture
   files it references under `skills/<skill>/fixtures/`. This is not optional
   and it is not the builder's job: the author of a skill must not write its
   own exam. Fixtures you cannot produce become Information Request items in
   the proposal's Blockers table under the existing proceed-under-assumption
   rule — but eval.yaml itself must exist, or the conductor blocks the
   proposal rather than building it.

## After all sessions
Proposals sit at `status: proposed` awaiting review (PR or portal). The portal
renders each skill's `eval.yaml` and fixture list inline under the proposal:
one Confirm approves the contract prose and the executable suite together, and
the conductor records an `eval_hash` over that suite as it opens the build.
Every build and refine attempt is checked against that hash — which is what
makes "never weaken a test to pass it" mechanical rather than a prompt.
Cosmetic change → direct edit + ledger addendum. Structural change → targeted
re-grill seeded with ledger + the specific comment. Any change bumps version and
resets confirmation. Shared-skill changes flag dependent proposals stale.
