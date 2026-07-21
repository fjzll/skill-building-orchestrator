# Failure triage — LLM recovery hook for the conductor (design)

**Status:** designed 11-Jul-2026, not yet implemented. Motivated by the
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

## Implementation notes (~small)

- One new function `triage(skill, evidence)` in conductor.py: spawns
  `claude -p` with a triage prompt template (`docs/triage-prompt.md`, to
  write), same pattern as `build_skill`.
- Called from the three failure branches + repeat-tick-error.
- Portal: TRIAGE.md files with `autonomy: proposed` render in the Blockers
  tab as actionable items (approve = human writes the agree line).
- No queue, no state machine additions: TRIAGE.md presence + frontmatter is
  the state, consistent with files-as-system-of-record.
