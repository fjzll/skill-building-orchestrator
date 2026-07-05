#!/usr/bin/env python3
"""Orchestration runner — walks proposal statuses and drives the pipeline.

Pipeline stages per client run:
  1. facts        -> runner/facts_extractor.py (deterministic pre-grill pass)
  2. grill        -> INTERACTIVE. One session per grill_order entry, fresh context.
                     The runner only tells you which session is next; it never
                     grills autonomously. Session seed = analysis/facts.yaml +
                     ledger/*. Session exit = new approved ledger entry.
  3. proposals    -> written by grill sessions; live in proposals/*.md with
                     frontmatter status. Review via PR (or portal later).
  4. build        -> headless agent run per skill, shared skills first.
                     Requires ANTHROPIC_API_KEY (or `claude` CLI on PATH).
  5. test         -> evals/harness/run_evals.py per built skill; scorecard.json
                     compared against thresholds in the proposal frontmatter.

Usage:
  python3 runner/runner.py status          # show pipeline state
  python3 runner/runner.py next            # what should happen next
  python3 runner/runner.py build <skill>   # kick off a headless build (stub if no key)
  python3 runner/runner.py test <skill>    # run the eval harness for a skill
"""
import sys, os, glob, subprocess, json, re

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from client_config import require_client_config

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def frontmatter(path):
    meta = {}
    try:
        txt = open(path).read()
    except OSError:
        return meta
    m = re.match(r"^---\n(.*?)\n---", txt, re.S)
    if m:
        for line in m.group(1).splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                meta[k.strip()] = v.strip()
    return meta

def proposals():
    out = []
    for p in sorted(glob.glob(os.path.join(ROOT, "proposals", "*.md"))):
        if os.path.basename(p) == "TEMPLATE.md":
            continue
        meta = frontmatter(p)
        meta = {k: v.split("#")[0].strip() for k, v in meta.items()}
        out.append({"file": os.path.basename(p),
                    "workflow": meta.get("workflow", "?"),
                    "status": meta.get("status", "draft"),
                    "version": meta.get("version", "1")})
    return out

def ledger_entries():
    return sorted(os.path.basename(p) for p in glob.glob(os.path.join(ROOT, "ledger", "*.md")))

def skills():
    return sorted(os.path.basename(p) for p in glob.glob(os.path.join(ROOT, "skills", "*")) if os.path.isdir(p))

def cmd_status():
    print("== skill-orchestrator status ==")
    facts = os.path.join(ROOT, "analysis", "facts.yaml")
    print(f"facts: {'present' if os.path.exists(facts) else 'MISSING — run facts_extractor.py'}")
    print(f"ledger entries: {ledger_entries() or 'none'}")
    ps = proposals()
    if ps:
        for p in ps:
            print(f"proposal {p['file']}: status={p['status']} v{p['version']}")
    else:
        print("proposals: none (grill sessions not run yet)")
    print(f"skills built: {skills() or 'none'}")

def cmd_next():
    if not os.path.exists(os.path.join(ROOT, "analysis", "facts.yaml")):
        print("NEXT: python3 runner/facts_extractor.py  (pre-grill facts pass)")
        return
    entries = ledger_entries()
    # sessions are numbered from facts.grill_order; conventions entry is 000
    session_entries = [e for e in entries if not e.startswith("000")]
    try:
        import yaml
        facts = yaml.safe_load(open(os.path.join(ROOT, "analysis", "facts.yaml")))
        order = facts.get("grill_order", [])
    except Exception:
        order = []
    if len(session_entries) < len(order):
        nxt = order[len(session_entries)]
        print(f"NEXT: grill session {nxt['session']} — {nxt['subject']} ({nxt['type']})")
        print("  Run interactively (fresh context) with the grill-me skill.")
        print("  Seed: analysis/facts.yaml + ledger/*  |  Exit: approved ledger entry + proposal update.")
        return
    ps = proposals()
    for p in ps:
        if p["status"] == "proposed":
            print(f"NEXT: review proposal {p['file']} (open PR / set status: confirmed)")
            return
    for p in ps:
        if p["status"] == "confirmed":
            print(f"NEXT: build skills for {p['workflow']} (shared deps first): runner.py build <skill>")
            return
    for p in ps:
        if p["status"] == "building":
            print(f"NEXT: finish builds for {p['workflow']}, then runner.py test <skill>")
            return
    print("NEXT: all proposals tested or nothing to do. Add ledger/proposals to proceed.")

def cmd_build(skill):
    skill_dir = os.path.join(ROOT, "skills", skill)
    os.makedirs(skill_dir, exist_ok=True)
    prompt_path = os.path.join(skill_dir, "BUILD_BRIEF.md")
    if not os.path.exists(prompt_path):
        print(f"No BUILD_BRIEF.md in skills/{skill}/ — grill session should have produced one via the proposal.")
        print("Creating a stub brief from the proposal is the grill session's job, not the runner's.")
        return
    if os.environ.get("ANTHROPIC_API_KEY") or shutil_which("claude"):
        # Headless agent build. Uses claude CLI if available.
        cmd = ["claude", "-p", f"@{prompt_path} Build this skill per the brief. Do not change the contract.",
               "--output-format", "json"]
        print("running:", " ".join(cmd))
        subprocess.run(cmd, cwd=skill_dir)
    else:
        print("STUB: no ANTHROPIC_API_KEY and no `claude` CLI on PATH.")
        print(f"When available, the runner executes a fresh-context headless build from skills/{skill}/BUILD_BRIEF.md")

def shutil_which(x):
    from shutil import which
    return which(x)

def cmd_test(skill):
    harness = os.path.join(ROOT, "evals", "harness", "run_evals.py")
    subprocess.run([sys.executable, harness, skill], cwd=ROOT)

if __name__ == "__main__":
    require_client_config(ROOT)
    args = sys.argv[1:]
    if not args or args[0] == "status":
        cmd_status()
    elif args[0] == "next":
        cmd_next()
    elif args[0] == "build" and len(args) > 1:
        cmd_build(args[1])
    elif args[0] == "test" and len(args) > 1:
        cmd_test(args[1])
    else:
        print(__doc__)
