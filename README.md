# skill-orchestrator

Implementation orchestration layer for Transcend AI Partners — takes AI Review
build plans and turns them into built, eval-gated skills. First client: JP
Equity Partners (JPE). Design decisions: see `skill-implementation-orchestrator-design.md`
on the Desktop and `ledger/000-conventions.md`.

## Layout

```
build-plans/     canonical YAML — workflow-map.yaml + one file per slice (10 JPE slices)
deep-dives/      as-is process reconstructions per slice (10 JPE slices)
analysis/        facts.yaml — deterministic pre-grill pass output
ledger/          append-only decision record; sessions read on entry, write on exit
proposals/       one per workflow; frontmatter status drives the pipeline
skills/          one directory per skill (fixtures + eval config + scorecard inside)
evals/harness/   3-layer eval harness (deterministic / grounding / LLM judge)
runner/          facts_extractor.py + runner.py (pipeline driver)
portal/          Next.js implementation portal (JPE design system)
docs/            grill-protocol.md
```

## Quick start

```bash
pip install pyyaml                      # once
python3 runner/facts_extractor.py .     # pre-grill facts pass
python3 runner/runner.py status         # pipeline state
python3 runner/runner.py next           # what to do next
```

Portal:

```bash
cd portal && npm install && npm run dev   # http://localhost:3000
```

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

## Data provenance

JPE dataset ingested 04-Jul-2026 from the rendered client portal
(jp.transcendai.com.au/jp) via the v0 scrape adapter. When Ash confirms the
portal's source format, replace with a direct adapter — the canonical schema
here stays the same. The Agreements tab was not ingested (commercial doc, not
orchestrator input).

## Open items

1. Portal source format (Ash) → real ingest adapter.
2. GitHub remote for the PR review loop (currently local-only).
3. ANTHROPIC_API_KEY / `claude` CLI for headless builds + Layer 3 judge.
4. Real client fixtures (GML CSVs, example emails) into skills/*/fixtures/.
