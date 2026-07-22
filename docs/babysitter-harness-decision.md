# Decision — babysitter internal harness inside `build_skill()`

date: 22-Jul-2026
session: Phase 3 of the orchestrator improvement plan
status: **deferred** (not adopted, not rejected)

## Context

Phase 3 of the improvement plan has two halves. The baseline — instruct the
builder to keep `BUILD_LOG.md`, archive it per attempt — is implemented and
shipped. The second half was a timeboxed spike: wrap *only* `build_skill()` in
babysitter's internal harness (`babysitter harness:call --harness internal
--process ... --no-interactive --json`) and compare its journal against the
honour-system BUILD_LOG.

## Decision

**Deferred.** The spike is not run, and no dependency is added.

The plan's own decision rule is: *adopt only if the journal materially improves
triage verdict quality in Phase-2 shadow data; otherwise keep the baseline.*
That rule cannot be evaluated yet. `analysis/triage-calibration.jsonl` is empty
— Phase 2 shipped hours ago and no real build has failed under it. Running the
spike now would produce a decision made on zero evidence, which is exactly the
failure mode the calibration ramp exists to prevent everywhere else in this
system. Deciding on vibes here while demanding ten consecutive agreements
before automating a retry would be incoherent.

## Trigger to revisit

Run the spike when **both** hold:

1. `analysis/triage-calibration.jsonl` holds at least 20 reviewed verdicts, of
   which at least 5 are `implementation` or `contract` class (the classes where
   evidence quality plausibly changes the verdict — `transient` and
   `environment` are usually obvious from the exit code alone).
2. `orch retrospect` shows BUILD_LOG evidence present for the majority of
   failed attempts. If builders are not honouring the honour-system log, the
   comparison is against nothing and the answer is trivially "adopt" for the
   wrong reason — fix the preamble first.

Measure by re-running triage on a sample of past failures with and without the
journal, and comparing verdicts to the human's recorded class.

## Rejected alternatives / why-nots

- **Adopt the internal harness now, on the reasoning that a structured journal
  is obviously better than an honour-system log.** Probably true and still not
  a reason: the cost is a runtime dependency on another orchestrator inside the
  one place this system spends real money, and "probably better" is what the
  evidence bar exists to discipline. If the baseline turns out to be enough,
  the dependency is pure carrying cost.
- **Reject it outright and close the question.** The interface really is
  swappable — `build_skill()` exposes only an exit code and files on disk to the
  conductor — so the blast radius of adopting later is genuinely small. Closing
  a cheap, reversible option to avoid holding an open question is a bad trade.
- **Run the spike against synthetic failures instead of waiting for real shadow
  data.** Synthetic failures are the ones we already know how to classify;
  they would show the journal helping least, and would bias toward rejection
  for the wrong reason.
- **Build our own structured journal format instead** (JSON events rather than
  a markdown log). Speculative: nothing has yet failed because BUILD_LOG.md is
  prose. Revisit only if triage verdicts are demonstrably limited by parsing
  the log, not by what the builder recorded in it.

## What ships regardless

`BUILD_LOG.md` is requested in every build and refine brief, archived per
attempt as `BUILD_LOG.attempt-N.md`, and listed in the triage evidence set. If
the spike is eventually adopted, `build_skill()`'s interface to the conductor
does not change — exit code plus files on disk — so the choice stays reversible
with zero blast radius. This remains the only sanctioned entry point for
babysitter into this stack.
