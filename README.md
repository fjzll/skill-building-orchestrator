# skill-building-orchestrator (template)

Implementation orchestration layer for Transcend AI Partners — takes AI Review
build plans and turns them into built, eval-gated skills. This repo is the
**template / engine**: no client data lives here. Each client gets its own
clone with a `client.yaml` and its own build-plans, deep-dives, ledger,
proposals and skills. Design decisions: see
`skill-implementation-orchestrator-design.md` and `ledger/000-conventions.md`.

## Starting a new client

```bash
git clone <template-repo-url> <slug>-skills
cd <slug>-skills
./orch init <slug> "<Display Name>"     # writes client.yaml, refuses to overwrite
```

Then fill in the client's data:
- `build-plans/workflow-map.yaml` + `build-plans/<slug>-*.yaml` (canonical YAML,
  one file per slice)
- `deep-dives/<slug>-*.yaml` (as-is process reconstructions per slice)

Everything else (`runner/`, `evals/`, `portal/`, `docs/`, `orch`, the ledger
conventions entry, the proposal template) is the reusable engine and works
unmodified once `client.yaml` exists.

## client.yaml

Every client clone has one (gitignored in the template itself, committed in
client clones):

```yaml
slug: acme
display_name: Acme Corp
portal_title: Skill Implementation — Acme Corp
template_commit: <hash of the template commit this clone was cut from>
```

`slug` drives the `build-plans/{slug}-*.yaml` / `deep-dives/{slug}-*.yaml` glob
and the `<client>-<workflow>-<skill>` naming convention. `template_commit`
tracks how far the client clone has drifted from the template — see "Pulling
in template upgrades" below. See `client.yaml.example` for the schema.

Running `runner/facts_extractor.py`, `runner/runner.py`, or `runner/conductor.py`
without a `client.yaml` present exits with a message pointing at `./orch init`
instead of a traceback — that's how you know you're still looking at a bare
template clone.

## Layout

```
client.yaml      per-client config (gitignored here; committed in client clones)
build-plans/     canonical YAML — workflow-map.yaml + one file per slice (client data)
deep-dives/      as-is process reconstructions per slice (client data)
analysis/        facts.yaml — deterministic pre-grill pass output (client data)
ledger/          append-only decision record; sessions read on entry, write on exit
                 (000-conventions.md ships genericized; the rest is per-client)
proposals/       one per workflow; frontmatter status drives the pipeline
                 (TEMPLATE.md ships here; the rest is per-client)
skills/          one directory per skill (fixtures + eval config + scorecard inside)
                 (_demo-eval-check/ ships as a worked example; the rest is per-client)
evals/harness/   3-layer eval harness (deterministic / grounding / LLM judge)
runner/          client_config.py + facts_extractor.py + runner.py + conductor.py
portal/          Next.js implementation portal (title reads client.yaml at build time)
docs/            grill-protocol.md, failure-triage.md (LLM triage hook design, not yet implemented)
```

## Quick start — two human touchpoints, everything else autonomous

```bash
./orch up      # the on switch: conductor daemon + portal at http://localhost:3000
./orch grill   # touchpoint 1: start the next grill session (interactive, auto-seeded)
```

Touchpoint 2 is in the portal: the Proposals tab has **Confirm** and **Request
changes** buttons. On Confirm, the conductor automatically builds the proposal's
skills (shared deps first), runs the eval harness, writes scorecards and flips
the status to `tested` (or `build-failed`). The conductor also re-runs the facts
pass whenever `build-plans/` changes. Log: `analysis/conductor.log`.

Manual equivalents (all optional): `./orch status|facts|daemon|build <skill>|test <skill>`.

Evals (see `skills/_demo-eval-check/` for a worked example):

```bash
python3 evals/harness/run_evals.py <skill-name>
# exit 0 = gate passed; scorecard at skills/<skill>/eval/scorecard.json
```

## Pipeline

facts → grill sessions (human, one workflow per fresh context; see
docs/grill-protocol.md) → proposals (status: proposed → confirmed) → autonomous
builds (skill-creator engine; needs ANTHROPIC_API_KEY or `claude` CLI) →
eval-gated tests. Layers 1–2 must pass 100%; the Layer 3 judge gates only after
calibration against human verdicts.

## Pulling in template upgrades

Client clones drift from the template over time (bug fixes, new eval-harness
features, portal changes). To pull those in deliberately, without touching
client data:

```bash
git diff <template_commit>..<template-repo-head> -- runner/ evals/ portal/ docs/ orch
```

(`<template_commit>` comes from the client's `client.yaml`.) Review the diff,
apply the parts you want (cherry-pick, patch, or manual merge — whichever
suits the size of the change), then bump `template_commit` in `client.yaml` to
the commit you upgraded to.

## Open items

1. Portal source format (Ash) → real ingest adapter for build-plan ingestion.
2. GitHub remote for the PR review loop (currently local-only).
3. ANTHROPIC_API_KEY / `claude` CLI for headless builds + Layer 3 judge.
4. Real client fixtures into skills/*/fixtures/ (per client).
