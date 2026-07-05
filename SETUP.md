# One-time setup on your Mac

Git is already initialised with a clean history — nothing to fix.

## Python

```bash
pip3 install pyyaml
```

## Portal + conductor (the "on" switch)

```bash
cd ~/Desktop/transcend-workspace/skill-building-orchestrator/portal && npm install   # once
cd ~/Desktop/transcend-workspace/skill-building-orchestrator
./orch up          # starts conductor (background) + portal at http://localhost:3000
./orch down        # stops the conductor
```

## Grill sessions

```bash
./orch grill       # works out the next session and launches it, seeded
```

Needs the claude CLI (`npm install -g @anthropic-ai/claude-code`). Without it,
`./orch grill` prints the seeded prompt to paste into a Cowork session instead.

## Headless builds + Layer 3 judge

```bash
export ANTHROPIC_API_KEY=sk-ant-...    # judge (Layer 3 evals)
# claude CLI on PATH                   # headless skill builds
```

Until these exist, the conductor logs builds as SKIPPED and Layer 3 as pending —
everything else still runs.

## GitHub (when ready for the PR review loop)

```bash
git remote add origin <your-repo-url>
git push -u origin main
```
