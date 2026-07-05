# One-time setup on your Mac

## Git

The sandbox that built this repo couldn't manage git lock files on the mounted
folder, so the `.git` directory here is stale. Fix it on your Mac (takes 10
seconds):

```bash
cd ~/Desktop/skill-orchestrator
rm -rf .git
git init && git add -A && git commit -m "Initial: orchestrator + full JPE dataset"
```

(Alternatively clone from `repo.bundle` if present: `git clone repo.bundle fresh-copy`.)

When you're ready for the PR review loop, create a GitHub repo and:

```bash
git remote add origin <your-repo-url>
git push -u origin main
```

## Python

```bash
pip3 install pyyaml
```

## Portal

```bash
cd portal
npm install
npm run dev        # http://localhost:3000
```

## Headless builds + Layer 3 judge

```bash
export ANTHROPIC_API_KEY=sk-ant-...
# and/or install the claude CLI for runner.py build
```
