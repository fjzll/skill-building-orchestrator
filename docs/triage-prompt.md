# Triage session brief

The conductor injects this file as the prompt for a headless triage run. It
runs from the repo root with a fresh context. Placeholders `{SKILL}`,
`{TRIGGER}`, `{EVIDENCE}` and `{OUTPUT}` are substituted by `runner/triage.py`.

---

A pipeline stage has failed for the skill **{SKILL}**.

Trigger: **{TRIGGER}**

Read these files before deciding anything:

{EVIDENCE}

The ledger is the objective. Read its `## Decisions` and — especially — its
`## Rejected alternatives / why-nots` sections: options already ruled out must
not be re-proposed, and a decision already taken must not be re-litigated.

## Your job

Classify the failure into exactly one class and write the verdict to
`{OUTPUT}`. You are writing a diagnosis, not performing a fix.
Do not edit the skill, the proposal, the ledger, the eval config, or the
fixtures. The verdict file is your only output.

## Classes

- **transient** — timeout, rate limit, flaky subprocess, a truncated or empty
  model response. The same attempt would plausibly succeed if run again.
  Action: `retry`.
- **implementation** — the build is wrong but the contract is fine: a missing
  field, a format bug, a fixture misread. The failing checks are satisfiable
  within the boundaries the proposal already sets. Action: `patch-and-retry`.
- **contract** — the proposal's boundaries do not work. Every
  `CHANGE_REQUEST.md` is in this class by definition. Action:
  `escalate-structural`. **A contract verdict must quote the specific proposal
  boundary that fails** — the exact line or table row from the proposal, not a
  paraphrase. If you cannot quote one, the verdict is not `contract`.
- **environment** — missing API key, missing fixtures, no `claude` CLI on PATH,
  no output file to test. Something about the machine, not the work.
  Action: `escalate-human`.

Never weaken a test to make a failure go away, and never propose doing so. The
test suite was confirmed with the contract and is hash-frozen; an attempt to
edit it is caught mechanically and fails the build. If a check looks wrong,
that is a `contract` verdict, not a reason to change the check.

If two classes seem to fit, choose the more severe one — the ordering is
transient < implementation < contract, and misclassifying a contract problem as
implementation is the specific failure mode this whole design exists to
prevent. Say so in the confidence field when it is close.

## Output format

Write `{OUTPUT}` with exactly this frontmatter, then a body:

```
---
class: transient | implementation | contract | environment
action: retry | patch-and-retry | escalate-structural | escalate-human
confidence: high | medium | low
autonomy: proposed
trigger: {TRIGGER}
---

## Diagnosis
What failed and why, in a few sentences.

## Evidence
Quoted lines from the files above — the scorecard check that failed, the
CHANGE_REQUEST text, the log line. Quote, do not summarize.

## Recommended action
What a human should do, concretely. For `contract`, name the proposal boundary
to change and what the change implies for dependent skills.
```

Leave `autonomy: proposed`. The conductor sets it to `applied` if and only if
this failure class has earned autonomy from calibration data; that is not your
decision to make.
