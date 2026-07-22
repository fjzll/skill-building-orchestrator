# Failure triage — LLM recovery hook for the conductor

**Status:** designed 11-Jul-2026, implemented 22-Jul-2026 (`runner/triage.py`,
`docs/triage-prompt.md`, conductor trigger points, portal review UI). Two
implementation decisions this document did not pin down are recorded at the
bottom under "As built". Motivated by the
orchestrator comparison with Ash (see
`../../comparation-of-orchestrator-for-skill-production/round-two-discussion-notes.md`):
a deterministic conductor fails loud but dumb. This hook adds LLM reasoning at
failure points *only*, keeping the happy path deterministic. Autonomy is
graduated via the same calibration-ramp pattern the eval judge uses.

## Principle

The conductor stays a scheduler. It never reasons. When a stage fails, instead
of just logging and stopping, it spawns a **triage session** — a headless LLM
run seeded with the artifacts that hold the objective:

- the failed skill's proposal section (the contract)
- the relevant ledger entries, including `Rejected alternatives / why-nots`
- the error evidence: build log tail / scorecard.json / CHANGE_REQUEST.md
- `analysis/facts.yaml`

This answers Ash's "the code knows the next step, but not the overall
objective" without giving the happy path to a nondeterministic driver: the
North Star lives in the ledger, and the triage session reads it.

## Trigger points (mapped to conductor.py)

| # | Failure | Today | With triage |
|---|---------|-------|-------------|
| 1 | `build_skill` returns FAILED (claude run errored / no SKILL.md) | log + status stuck | triage classifies + acts |
| 2 | Builder wrote `CHANGE_REQUEST.md` and stopped | nothing reads it | triage packages it into a structural change request on the proposal |
| 3 | `test_skill` gate FAIL | proposal → `build-failed` | triage reads scorecard, classifies which layer failed and why |
| 4 | Conductor `tick()` exception | log ERROR, next tick | triage on repeat (same error 3 ticks running) |

## Triage output — a verdict file, not an action

The session writes `skills/<skill>/TRIAGE.md` with frontmatter:

```yaml
class: transient | implementation | contract | environment
action: retry | patch-and-retry | escalate-structural | escalate-human
confidence: high | medium | low
autonomy: applied | proposed   # what the conductor did with it (see ramp)
```

Body: diagnosis, evidence quotes, and (for `patch-and-retry`) the exact patch.

Class definitions:

- **transient** — timeout, rate limit, flaky subprocess → retry (bounded, 3).
- **implementation** — the build is wrong but the contract is fine (missing
  field, format bug, fixture misread) → patch-and-retry within retry budget.
- **contract** — the proposal boundaries don't work (this includes every
  CHANGE_REQUEST.md) → structural change request: proposal status →
  `changes-requested`, ledger addendum drafted, dependent proposals flagged if
  a shared skill is involved. Never patched around. **Never weaken a test to
  pass it.**
- **environment** — missing API key, missing fixtures, no `claude` CLI →
  escalate-human (surfaces as a SYSTEM blocker in the portal Blockers tab).

## Calibration ramp (autonomy is earned per class)

Phase 0 — **shadow**: triage runs and writes TRIAGE.md; conductor behaviour
unchanged. Human resolves failures manually and records agree/disagree with
the verdict (one line in the triage file).

Phase 1 — **transient auto**: after N=10 consecutive agreements on
`transient`, the conductor auto-applies retries for that class. Everything
else stays proposed.

Phase 2 — **implementation auto**: same bar (N=10 agreements, zero contract
misclassifications — an `implementation` verdict that was actually `contract`
resets the counter to zero, because that's the drift failure mode this whole
design exists to prevent). Auto patch-and-retry within the retry budget; every
applied patch gets a ledger addendum, auto-written, human-visible.

Never automated — `contract` and `environment` always escalate. The builder
can't change the contract; neither can its triage.

Agreement ledger: `analysis/triage-calibration.jsonl` (one line per verdict:
skill, class, human agree/disagree). The conductor reads counts from here to
decide the phase per class — no config flag to flip by hand, the data flips it.

## As built (22-Jul-2026)

Two things the design left open, and what was decided:

**1. What "auto-apply" actually does.** A verdict whose class has earned
autonomy causes exactly one thing: the skill's attempt budget is cleared, so
the deterministic build/refine loop gets one more bounded run at the problem.
That is what a human does when they agree with a `transient` or
`implementation` verdict, and it keeps the LLM out of the execution path — it
diagnoses, the scheduler acts. A one-shot marker (`.triage-applied`, cleared on
the next confirmation) means an auto-retry can never become its own retry bomb.
The Phase 1 refine loop remains unconditional and deterministic; triage does
not gate it, and shadow mode therefore costs no capability.

**2. The ramp is ordered.** `implementation` cannot reach auto before
`transient` has. The bar is 10 consecutive agreements per class either way, but
a repo cannot skip to the more consequential automation on the strength of
implementation agreements alone.

Trigger 4 (repeated tick exception) writes its verdict to
`analysis/TRIAGE-tick.md` rather than a skill directory — a tick error is not
attributable to one skill.

## Implementation notes (~small)

- One new function `triage(skill, evidence)` in conductor.py: spawns
  `claude -p` with a triage prompt template (`docs/triage-prompt.md`, to
  write), same pattern as `build_skill`.
- Called from the three failure branches + repeat-tick-error.
- Portal: TRIAGE.md files with `autonomy: proposed` render in the Blockers
  tab as actionable items (approve = human writes the agree line).
- No queue, no state machine additions: TRIAGE.md presence + frontmatter is
  the state, consistent with files-as-system-of-record.
