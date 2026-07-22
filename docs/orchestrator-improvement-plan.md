# skill-building-orchestrator — Improvement Plan

**Date:** 22-Jul-2026
**Basis:** Code review of `skill-building-orchestrator` (conductor.py, runner.py, facts_extractor.py, run_evals.py, orch, ledger conventions, grill protocol, failure-triage design, portal, CI) and comparison against a5c-ai/babysitter.
**Verdict carried forward:** Do not migrate to babysitter. Keep the architecture (deterministic Python scheduler, files-as-system-of-record, sealed fresh-context agent subprocesses, ledger with why-nots, calibration-ramp autonomy). Fix the bugs, close the convergence gap, implement the already-designed triage layer, and borrow four specific babysitter capabilities.

---

## Guiding principles (unchanged, restated so the plan can't drift from them)

1. The happy path contains no LLM. Intelligence is summoned at failure points only, and autonomy is earned per failure class from calibration data — never assumed.
2. Files are the system of record. Any portal, dashboard, or bot is a view or an actor on files. No new databases, no queues.
3. The builder cannot change the contract. Neither can any retry, patch, or triage action. Contract problems always escalate as structural change requests.
4. Never weaken a test to pass it.
5. Every borrowed babysitter idea is adopted as a pattern implemented in this codebase — not as a runtime dependency — with one contained exception evaluated in Phase 3.

---

## Phase 0 — Hotfixes (do first; small, urgent)

These are correctness bugs found in the current code. All are independent of the roadmap.

**0.1 Retry bomb / CHANGE_REQUEST.md never read.** In `conductor.py`, a failed `build_skill` (or a builder that wrote `CHANGE_REQUEST.md` and stopped) leaves no `SKILL.md`, the proposal stays `building`, and the next 15-second tick launches another full `claude -p` build — unbounded retries of up to 1-hour timeouts, indefinitely.
Fix in `build_skill()`:
- If `CHANGE_REQUEST.md` exists in the skill dir: do not build. Log, set proposal `status: changes-requested`, and surface it (portal Blockers tab reads it). This wires up triage trigger #2 from the design doc in its manual form until Phase 2 automates classification.
- Maintain `skills/<skill>/.build-attempts` (a counter file, consistent with files-as-record). Cap at 3; on cap, set proposal `status: build-failed` with a log line naming the skill.
- On successful build, delete the counter.

**0.2 Judge model string.** `run_evals.py` Layer 3 calls model `"claude-sonnet-5"`, which is not a valid API identifier — the judge will error the moment `ANTHROPIC_API_KEY` is set. Set it to a current valid model string (verify against the live models list at implementation time; as of this writing `claude-sonnet-4-6`), and read it from `eval.yaml` (`layer3.model:`) with that default so per-skill overrides are possible and future model changes are config, not code.

**0.3 Frontmatter robustness.** `read_fm`/`set_fm` split on `:` and strip after `#`; values containing either character corrupt state, and `set_fm` writes are not atomic (portal Confirm and conductor tick can race). Replace with `python-frontmatter` (or a small hardened parser), and write via temp-file + `os.replace` for atomicity. Add a 5-line unit test with a frontmatter value containing `:` and `#`.

**0.4 SKIPPED-test silent stall.** `test_skill` returns `None` when `eval/eval.yaml` is missing; all-`None` results leave the proposal at `building` forever with only a log line. Make a missing eval config a hard blocker: log it, set the proposal to a blocked state, and surface it in the portal Blockers tab. (Phase 1.0 removes the root cause by guaranteeing eval.yaml exists before build.)

**0.5 Double-conductor guard.** Local daemon (`orch up`) and CI conductor (`pipeline.yml` conduct job) can both act on the same repo state. Add a advisory lock file (`analysis/.conductor-lock` with PID + timestamp, stale after N minutes) so a second conductor instance no-ops with a log line instead of double-building.

**Exit criteria:** a deliberately broken skill (bad brief) reaches `build-failed` after exactly 3 attempts; a skill with `CHANGE_REQUEST.md` never re-builds and appears in Blockers; Layer 3 runs end-to-end against the demo skill; frontmatter round-trips values containing `:` and `#`.

---

## Phase 1.0 — Test-suite-first gate (tests materialized, confirmed, and frozen before any build)

**Problem:** the human confirms the proposal's prose "Test definition", but the executable `eval/eval.yaml` is never presented for approval — and nothing in the pipeline materializes it. Either the builder authors it (author writes its own exam, breaking the author/reviewer separation) or it's absent (silent stall per 0.4). The test suite is part of the contract; today it's the one part the builder can author.

**Design (TDD ordering applied to the pipeline):**
- **Materialize at grill exit.** Extend the grill session's exit act (grill-protocol.md rule 5) to write, alongside the ledger entry and proposal: `skills/<skill>/eval/eval.yaml` per skill and fixture files (fixture gaps become Information Request items governed by the proposal's Blockers table, per the existing proceed-under-assumption mechanism).
- **One Confirm covers contract + tests.** The portal proposal view renders the actual eval.yaml contents and fixture list inline under the Test definition section; Confirm explicitly approves both. No new status added.
- **Freeze on confirm.** On the `confirmed` transition, the conductor records `eval_hash` (eval.yaml + fixtures) into proposal frontmatter. The Phase 1 refine-loop guard verifies against this confirm-time hash — not a loop-start snapshot — so tampering on the first build attempt is also caught.
- **Builder precondition.** `build_skill()` refuses to run without `eval/eval.yaml` (→ blocked, surfaced in portal); the builder brief declares eval config and fixtures read-only context.
- **Doc updates:** grill-protocol.md rule 5 and proposals/TEMPLATE.md Test definition section note that eval.yaml/fixtures are written and committed at grill exit; ledger 000 convention 7 gains a sentence that the executable suite is confirmed and hash-frozen with the proposal.

**Authorship result across layers:** checks and rubric authored by the grill session (human-approved), executed by the harness (deterministic), against output from a sealed builder — three separated parties.

**Exit criteria:** a proposal cannot reach `building` without a confirmed eval.yaml; portal Confirm page displays the executable suite; a post-confirm edit to eval.yaml or fixtures fails the hash check on the next conductor tick.

## Phase 1 — Convergence loop (borrow #1 from babysitter; the biggest functional gap)

**Problem:** the pipeline is one-shot. Build → test → on any eval failure, `build-failed`, stop. Babysitter's core value — iterate against the gate until the target is met — has no counterpart here. This is also the most common edge case (output almost passes), so it dominates human-touch count.

**Design:** add a bounded refine loop between `test_skill` and the fail transition, entirely inside the existing scheduler (no LLM in the loop; the LLM is still a sealed subprocess per iteration).

- New conductor stage: on eval gate FAIL where Layer 1–2 failures are *implementation-shaped* (see classification below) or Layer 3 is below threshold, spawn a **refine build**: `claude -p` in the skill dir, fresh context, seeded with `BUILD_BRIEF.md` + `eval/scorecard.json` + the specific failing checks, with the instruction: fix the output/skill to satisfy the failing checks; do not modify eval config, fixtures, or the contract; if the checks cannot be satisfied within the contract, write `CHANGE_REQUEST.md` and stop.
- Budget: reuse the `.build-attempts` counter from 0.1 (total build+refine attempts ≤ 3 per skill per proposal version). On exhaustion → `build-failed` with the last scorecard attached.
- Guard: verify `eval/eval.yaml` and `fixtures/` against the confirm-time `eval_hash` recorded in the proposal frontmatter (Phase 1.0) before and after every build/refine attempt; any mismatch hard-fails the attempt (principle 4 enforced mechanically, not by prompt).
- Classification for loop eligibility (deterministic, no LLM yet): Layer 2 ungrounded-number failures and Layer 1 required/forbidden-string failures are refine-eligible; missing output file or missing fixtures are environment-shaped → escalate (Blockers), do not refine. Phase 2 replaces this heuristic with triage verdicts.

**What this buys:** babysitter-grade autonomous absorption of the most frequent failure, with a paper trail (each attempt's scorecard is retained as `scorecard.attempt-N.json`) and a hard budget — which babysitter's loop has, but yours will have *plus* the contract-immutability hash check it lacks.

**Exit criteria:** a skill seeded with a deliberate Layer-1 miss converges to pass within budget with no human touch; a refine run that edits `eval.yaml` is caught and failed by the hash guard.

---

## Phase 2 — Implement the failure-triage design (your own doc, now with running code)

`docs/failure-triage.md` is the right design; this phase implements it as specified, with the Phase 1 loop folded in as the `implementation` class action.

- New `triage(skill, evidence)` in conductor.py: headless `claude -p` seeded with the proposal section, relevant ledger entries (including Rejected alternatives / why-nots), error evidence (build log tail, scorecard, CHANGE_REQUEST.md), and `analysis/facts.yaml`. Output: `skills/<skill>/TRIAGE.md` with the frontmatter schema from the design doc (`class`, `action`, `confidence`, `autonomy`).
- Wire the four trigger points exactly as tabled in the design doc (build FAILED; CHANGE_REQUEST.md present; eval gate FAIL; repeated tick exception ×3).
- Calibration ramp exactly as designed: Phase 0 shadow (verdicts written, conductor behaviour unchanged, human records agree/disagree in the triage file); Phase 1 transient auto after 10 consecutive agreements; Phase 2 implementation auto on the same bar, counter zeroed by any implementation-that-was-actually-contract misclassification. `contract` and `environment` never automate.
- Agreement ledger `analysis/triage-calibration.jsonl` (one line per verdict: skill, archetype — see Phase 5 — class, human agree/disagree). Conductor reads phase per class from counts; no manual flags.
- Portal: TRIAGE.md files with `autonomy: proposed` render in the Blockers tab; approving one = the human agree line. (Small `portal/lib/data.js` addition; the pattern matches existing proposal parsing.)
- Prompt template `docs/triage-prompt.md` (referenced by the design doc, to be written) — include the class definitions verbatim and the instruction that a `contract` verdict must quote the specific proposal boundary that fails.

**Exit criteria:** each of the four trigger types produces a correctly-classed TRIAGE.md in shadow mode on synthetic failures; after 10 seeded agreements, a transient failure auto-retries without human touch and writes the autonomy line.

---

## Phase 3 — Execution visibility inside builds (borrow #2)

**Problem:** a `claude -p` build is an opaque up-to-1-hour subprocess; on failure you triage from an exit code and whatever the builder left on disk. Babysitter journals every step inside a run.

**Baseline (do this regardless):** instruct the builder, in the brief preamble the conductor injects, to append one line per significant action to `skills/<skill>/BUILD_LOG.md` (timestamp, action, files touched). Cheap, honor-system, but transforms triage evidence quality. Conductor archives it per attempt (`BUILD_LOG.attempt-N.md`).

**Evaluation spike (timeboxed, e.g. 2 days):** prototype wrapping *only* `build_skill()` in babysitter's internal harness (`babysitter harness:call --harness internal --process ... --no-interactive --json`) with a minimal process definition (task: build per brief; gate: SKILL.md exists and evals pass Layer 1). Assess: journal quality vs BUILD_LOG, stop-hook enforcement value inside the build, added dependency weight, and failure-mode behaviour. Decision rule: adopt only if the journal materially improves triage verdict quality in Phase-2 shadow data; otherwise keep the baseline. Either way, `build_skill()`'s interface to the conductor is unchanged (exit code + files), so the choice is reversible with zero blast radius — this is the only place babysitter may enter the stack, and it enters as a swappable implementation detail.

**Exit criteria:** every build attempt leaves a step-level trail the triage prompt consumes; adopt/reject decision on the internal-harness hybrid recorded as a ledger-style entry in `docs/` with why-nots.

---

## Phase 4 — Parallel builds and run tooling (borrows #3)

**4.1 Parallelism.** Conductor builds strictly sequentially. Parallelize independent skills within a proposal: topological order from proposal `skills:` list (shared deps first is already the convention — make it explicit by reading shared-dep edges from the proposal), then `concurrent.futures.ProcessPoolExecutor` for same-level skills, bounded (start at 3) to respect API rate limits. Fresh-process-per-skill means this is safe by construction; the only shared writes are frontmatter status (atomic after 0.3) and the log (append-only).

**4.2 Doctor.** `orch doctor`: stall detection (proposal in `building` with no attempt progress for N minutes; conductor lock stale; CHANGE_REQUEST/TRIAGE awaiting human beyond N hours), environment checks (claude CLI, API key, client.yaml, portal deps), and per-skill attempt/budget state. Pure file inspection — 100 lines of Python, mirrors babysitter's `doctor` without the dependency.

**4.3 Retrospect.** `orch retrospect`: per-repo summary from artifacts already on disk — attempts-to-converge per skill, which eval layer fails most, triage class distribution and agreement rates, wall-clock per stage from log timestamps. Output a markdown report into `analysis/`. This is the per-client feed for Phase 5's fleet layer.

**Exit criteria:** a 3-skill proposal with one shared dep builds shared-first then two in parallel; `orch doctor` flags a deliberately stalled proposal; `orch retrospect` renders on the demo repo.

---

## Phase 5 — Fleet scale for 20 clients (borrow #4: distribution; plus the transfer layer babysitter doesn't have)

**5.1 Upgrade-PR bot (babysitter's plugin/migration story, in git).** A GitHub Action in the template repo that, on release/tag: for each registered client repo, opens a PR containing `git diff <client's template_commit>..<release>` restricted to engine paths (`runner/ evals/ portal/ docs/ orch .github/`), and bumps `template_commit` in the PR. Client data paths are never touched. Registry: a `clients.yaml` in the template repo (or an org-level topic query). Merging the PR *is* the migration; review effort scales with change size, not client count. Kill the manual cherry-pick workflow described in the README once this lands.

**5.2 Calibration transfer (the compounding-autonomy layer; no babysitter counterpart).**
- **Archetype key:** derive from the naming convention mechanically — strip `<client>-` and generalize: `shared-<skill>` → archetype `shared/<skill>`; `<workflow>-<skill>` → archetype `<workflow-family>/<skill-family>`, where families come from a small mapping table maintained in the template (start with exact workflow/skill names; generalize only when two clients' names differ for the same shape of work, and record the merge as a ledger addendum in the template).
- **Aggregation:** a scheduled Action pulls `analysis/triage-calibration.jsonl` and judge-vs-human agreement records from all client repos into `fleet/calibration/<archetype>.jsonl` in a central (template or dedicated) repo. Client identity is retained in the line but the operative key is archetype.
- **Prior inheritance:** on `orch init`, seed the new client's calibration state from fleet priors: an archetype with ≥10 fleet agreements and zero contract misclassifications starts that client at triage Phase 1 (transient auto) for that archetype; ≥10 more including ≥3 distinct clients starts Phase 2 (implementation auto). Judge gating (Layer 3 as sole gate) inherits similarly per archetype.
- **Demotion:** per-client disagreement always demotes locally and immediately (local counter resets to zero for that class/archetype); fleet priors set the *starting* phase, never override a local reset. A fleet-level circuit breaker: any contract misclassification anywhere zeroes the fleet prior for that archetype (this is the drift failure mode the whole design exists to prevent — treat it fleet-wide).
- Files remain the record: priors are a generated `analysis/fleet-priors.yaml` committed into the client repo at init and refreshable via the upgrade bot.

**5.3 Fleet dashboard.** Extend the portal (or a sibling Next.js app) to read N client repos: proposal statuses, blockers, triage items awaiting agreement, calibration phase per archetype. `portal/lib/data.js` is already pure file parsing — parameterize `ROOT` into a list. Read-only in v1.

**5.4 Cross-ledger convention mining.** Quarterly (or per-N-clients) job: collect `## Rejected alternatives / why-nots` and `## Decisions` sections across client ledgers, cluster recurring decisions, and draft promotions into the template's `ledger/000-conventions.md` item 8 defaults and grill-protocol hypotheses. Human-reviewed PR, never automatic — this is methodology evolution, the consulting IP flywheel.

**Exit criteria:** a template release reaches 3 test client repos as reviewable PRs untouched client data; a fresh `orch init` starts a well-evidenced archetype at triage Phase 1; the fleet dashboard shows live status across ≥3 repos.

---

## Sequencing, effort, dependencies

| Phase | Contents | Rough effort | Depends on |
|---|---|---|---|
| 0 | Retry cap, CHANGE_REQUEST guard, judge model, frontmatter, SKIPPED-stall, lock | 1–2 days | — |
| 1.0 | Test-suite-first gate: grill-exit materialization, portal render, confirm-time hash freeze | 2 days | 0 |
| 1 | Convergence loop + immutability check vs confirm-time hash | 2–3 days | 0, 1.0 |
| 2 | Triage implementation + calibration ramp + portal Blockers wiring | 4–6 days | 0, 1 |
| 3 | BUILD_LOG baseline + babysitter-internal-harness spike & decision | 1 day + 2-day spike | 2 (shadow data informs decision) |
| 4 | Parallel builds, doctor, retrospect | 3–4 days | 0 (4.1 needs 0.3/0.4) |
| 5 | Upgrade bot, calibration transfer, fleet dashboard, convention mining | 1–2 weeks, incremental | 2 (transfer needs calibration data), 4.3 (retrospect feeds fleet) |

Phases 0–1 are worth doing this week regardless of any other decision: 0 stops live money-burning failure modes, 1 closes the single biggest capability gap vs babysitter. Phases 2–4 convert the triage design from paper to running autonomy. Phase 5 is the 20-client play and can start with 5.1 alone.

## Explicitly not doing

- **Migrating the pipeline to babysitter.** The architecture comparison concluded the ledger/portal/calibration design is better fitted to a consulting operation than babysitter would be after adaptation; the only sanctioned entry point is the Phase 3 spike, behind a stable interface.
- **Adding queues, databases, or a central orchestration server.** Every phase above is files + git + Actions, preserving auditability and the CI-per-repo scaling model.
- **Automating `contract` or `environment` escalations, ever.** Restated from the triage design because Phase 5's transfer layer must not erode it: fleet priors accelerate `transient` and `implementation` autonomy only.

## Open questions to resolve during implementation

1. Refine-loop budget: is 3 total attempts right, or should refine attempts have their own budget separate from clean-build attempts? (Suggest: total 3 in v1; revisit with retrospect data.)
2. Archetype family mapping: seed list needed from your first two real clients' workflow names before 5.2 is designable in detail.
3. Layer 3 judge: per-criterion score variance across the 3 runs is currently discarded — worth recording in the scorecard for calibration analysis? (Cheap; suggest yes.)
4. Portal write-path: Confirm currently edits frontmatter via the API route; after 0.3, route it through the same atomic-write helper to close the last race.
