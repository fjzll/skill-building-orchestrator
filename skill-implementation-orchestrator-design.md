# Skill Implementation Orchestration Layer — Design Decisions

**Status:** Decided via grill-me session · 04-Jul-2026
**Context:** Transcend AI Partners. The AI Review layer already orchestrates multiple skills to produce the client portal documents (workflow map, deep dives, build plans, decision lens). This layer does the same for the *implementation* side: it picks up confirmed build plans and turns them into built, tested skills.
**First client case:** JP Equity Partners (JPE) — 9 slices grouped into 6 capability workflows.

---

## Pipeline

```
ingest build plans
  → pre-grill analysis (facts only)
  → per-workflow grill sessions (human in the loop)
  → build proposals (one per workflow)
  → portal review loop (proposed ⇄ revised → confirmed)
  → autonomous builds (skill-creator engine)
  → eval-gated test runs
```

## Contracts

1. **Output of a run:** versioned, installable skill packages (SKILL.md + scripts) plus test-run evidence. Deployment is a separate, later concern.
2. **Input:** the orchestrator owns a canonical build-plan schema (slice id, steps[], today/with-AI per step, automation state, open items, evidence refs). A thin adapter converts whatever the portal's source format is into this schema. Never scrape portal HTML.
   - *Open item:* confirm the portal source format with Ash. Changes the adapter, not the architecture.
3. **Unit of a run:** one capability workflow (e.g. "client updates + holder list + social branch"), not one slice. Splitting decisions need the workflow-level view because slices share components.

## Human channels

4. Two distinct channels, never mixed:
   - **grill-me** — builder-side, synchronous, per client run. Stress-tests split proposals and build decisions.
   - **Information Requests** — client-side, asynchronous, queued via the portal. When the orchestrator hits a gap only the client can answer, it emits an IR item and either parks the skill or proceeds on a documented assumption. It never grills the client live.
5. **Grilling runs in bulk per client, but one workflow per fresh context window**, sequentially: shared skills first, then workflows in Decision Lens rank order. One big context for all workflows is prone to attention loss.

## Splitting — the gold question

6. **The orchestrator never decides the skill split autonomously.** The split is decided in dialogue:
   - **Pre-grill pass computes facts only:** shared-skill candidates (from the Decision Lens shared-foundations table + NESTED SLICE references), human-gate positions, dependencies, open-item lists, and the grill order. Deterministic, computed once.
   - **Hypotheses are formed live at the start of each grill session** from facts + the decision ledger so far. Later sessions inherit earlier decisions (e.g. merge conventions), so precomputed hypotheses would go stale and anchor the session.
   - **Cut-line heuristics** used as hypothesis generators, not deciders:
     - Cut at human gates — a skill is the longest uninterrupted AI-run segment between human review/send steps.
     - Cut at shared foundations — anything used by multiple workflows (holder-recipient identity, JP voice/examples, market-data source, client folders) becomes a standalone shared skill that workflow skills declare as dependencies.
7. **Decision ledger:** append-only record; each session reads it on entry and writes its decisions as its final act; human approval of that written entry is the session's exit gate. The ledger is the complete inter-session state (nothing important lives only in a session's chat) and doubles as the decision trace.

## Build proposals & portal review

8. **One proposal per workflow**, buildable without returning to the grill conversation:
   - Skill list — name, one-line job, trigger, inputs → outputs, build-plan steps covered, shared-skill dependencies.
   - Human gates — where each skill stops and who reviews.
   - Assumptions taken, each tagged to the Information Request that confirms or kills it.
   - Blockers — open items that block build vs. ones the build proceeds under assumption.
   - Test definition — fixtures, deterministic checks, rubric criteria, thresholds. Written at grill time while context is fresh.
   - Build order within the workflow (shared deps first).
9. **Portal review loop.** Proposals live in a portal tab per client with status flow:
   `proposed → changes requested ⇄ revised → confirmed → building → tested`
   - Proposals are **derived views of the ledger** — modifying a proposal means amending the ledger, never freehand edits.
   - Review actions are structured and anchored to proposal sections, not free-text chat.
   - Change triage: **cosmetic** (rename, wording) → direct edit + ledger addendum; **structural** (merge/split skills, move a gate, change scope/tests) → targeted re-grill session seeded with the ledger + the comment, covering only the affected branch.
   - Proposals are versioned with visible diffs; confirmation applies to a specific version and resets on any change.
   - Shared-skill changes auto-flag all dependent workflow proposals `stale — shared dependency changed`.

## Build

10. **Fully autonomous builder** — human touchpoints stay at grill, proposal review, and test review.
    - One skill per build run, fresh context, shared skills first.
    - Consumes: the confirmed proposal (its section only), the ledger, canonical build-plan data, and client evidence files as fixtures. Never the grill chat.
    - Engine: the existing `skill-creator` skill, orchestrated — not reimplemented.
    - Skills live in a per-client repo, one directory per skill, with fixtures and test definition inside the skill directory. `.skill` packaging is a release step.
    - **The builder cannot change the contract.** If proposal boundaries don't work mid-build, it stops and raises a structural change request into the portal revision loop.
11. **Naming convention** (recorded in the ledger):
    - Workflow skills: `<client>-<workflow>-<skill>` — e.g. `jpe-client-updates-draft-pack`, `jpe-desk-note-research`
    - Shared skills: `<client>-shared-<skill>` — e.g. `jpe-shared-holder-identity`

## Test — eval-gated, not vibes

12. **Three-layer eval harness**, producing a numeric scorecard per run:
    - **Layer 1 — deterministic assertions (hard gates, 100% required):** required fields present, attachment included, recipient count matches deduped CSV, batch sizes under send limits, disclaimers present, format rules followed.
    - **Layer 2 — fact grounding (100% required):** every number and factual claim in the output must trace to a source span in the fixtures. An invented figure is an automatic fail (mirrors the Decision Lens rule: every calculated field shows its source and formula).
    - **Layer 3 — LLM-judge rubric (graded 0–5 per criterion):** voice match vs gold examples, summary faithfulness, does-not-read-as-AI. Criteria written at grill time into the test definition. Judge runs in a separate context from the builder; multiple runs averaged.
    - **Gate policy lives in the proposal** — e.g. Layers 1–2 at 100%, Layer 3 average ≥ 85% with no criterion under 3. Pass → pipeline continues autonomously.
13. **Calibration ramp:** for first builds, LLM judge and human review run in parallel; once judge scores consistently agree with human verdicts, the judge becomes the gate and the human drops to spot-checks. Trust is earned away per skill, not assumed on day one.
    - Failure routing: implementation bug → bounded autonomous retries (e.g. 3); contract/test-definition problem → structural change request. Never weaken a test to pass it.
    - Test harness extends `skill-creator`'s existing eval machinery.

## Open items

| # | Item | Owner |
|---|------|-------|
| 1 | Portal source format behind the rendered pages (markdown/JSON/TSX?) — determines the ingest adapter | Ash |
| 2 | Portal support for proposal tabs, anchored review comments, and the status flow | Ash / portal build |
| 3 | Which model/framework runs the sessions-in-fresh-contexts mechanic (grill sessions, builders, judges) | Transcend |

## JPE first run (worked example)

- Unit: 6 capability workflows → grill order: shared skills, then client updates & social branch, capital raise layer, desk notes, screening, events, signal capture (per Decision Lens rank).
- First proof: `jpe-client-updates-draft-pack` tested by reproducing Jason's GML pack from the raw CSV + announcement PDF, cross-checked against Strickland and Tyler examples for generalisation.

---

## Technical approach (git backend)

The portal review UI is optional — everything it does (statuses, versions, diffs, anchored comments, approvals) maps onto git + GitHub. Files are the system of record; any portal is a view.

### Repo layout

```
jpe-skills/
  build-plans/        # canonical YAML per slice (adapter output from portal source format)
  ledger/             # append-only: 001-shared-skills.md, 002-client-updates.md…
  proposals/          # one .md per workflow, frontmatter: status, version
  skills/
    jpe-shared-holder-identity/   # SKILL.md + scripts + fixtures/ + eval/
    jpe-client-updates-draft-pack/
  evals/              # shared harness code
```

Proposal status lives in frontmatter (`status: proposed | confirmed | building | tested`); the runner reads it mechanically.

### Review loop = pull requests

- Proposal revision = PR → versioning and visible diffs for free.
- PR line comments = anchored review actions.
- Approve/merge = confirmation; request-changes = the `changes requested ⇄ revised` cycle.
- CI check flags dependent proposals when any `jpe-shared-*` path changes (ripple handling).

### Driver = Claude Agent SDK (thin scripts per stage)

| Stage | Mode | What it does |
|---|---|---|
| Pre-grill analysis | Headless SDK run | Writes facts file + grill order |
| Grill sessions | **Interactive** (Claude Code/Cowork + grill-me skill) | Fresh session per workflow, seeded with facts + ledger; exits by committing its ledger entry. Runner just tracks which session is next |
| Builder | Headless SDK run per skill, fresh context | Prompt = proposal section + ledger + fixtures; invokes skill-creator; opens PR with built skill |
| Test | Python harness | Layer 1 = pytest assertions; Layer 2 = claim extraction + source-span matching; Layer 3 = judge calls to a separate model, N runs averaged. Emits `scorecard.json`; CI gate compares against proposal thresholds |

### Deliberately not built

No database (files + git), no workflow engine (state machine = frontmatter + runner script), no custom review UI initially (PRs), no queue (runs are sequential by design).

New code is small: the build-plan adapter, the facts extractor, the eval harness, and a ~200-line runner that walks statuses and kicks off headless runs.

---

## Portal style guide (extracted from live JPE portal)

For building the implementation portal as a sibling app to the client review portal — same shell, new tabs (Proposals, Ledger, Build Status, Test Scorecards) — rendering from the git repo. Portal is read-and-review only, with two write actions: anchored comments and confirm (both call the GitHub API; the PR stays the real mechanism).

### Design tokens (`:root`)

```css
--color-primary:    #234E52;  /* deep teal — headings, active tab bg, hero banner */
--color-secondary:  #2D3748;  /* body text */
--color-accent:     #ED8936;  /* orange — callout left-borders */
--color-background: #FFFAF0;  /* warm cream page background */
--color-card:       #FFFFFF;
--color-border:     #D8E1E8;
--color-content-width: 1100px;
--font-heading: 'Merriweather', system-ui, sans-serif;  /* serif, 700 */
--font-body:    'Inter', system-ui, sans-serif;          /* 16px */
```

### Component patterns

- White rounded cards on the cream background.
- Pill tab bar: inactive = grey text (`#666`) on transparent; active = white text on teal (`#234E52`), 8px radius.
- Dark-teal hero banner per tab: small-caps grey "TRANSCEND AI PARTNERS" eyebrow, white Merriweather title, light subtitle line.
- Orange left-border callout strip (cream fill) for client/status/date metadata.
- Four-state step colour coding, reused for proposal statuses: green = automate/AI runs, amber = access to confirm, purple = human review, red = human does it.
- Sidebar sub-navigation for per-slice pages (deep dives, build plans).
- Tab routing via `?tab=` query param.
