#!/usr/bin/env python3
"""Conductor daemon — the autonomous half of the pipeline.

Loop (default every 15s):
  1. FACTS   build-plans/ changed since last facts run -> re-run facts_extractor
  2. BUILD   proposal status: confirmed -> building; run headless builds for its
             skills (shared deps first, one at a time, fresh process each)
  3. TEST    built skills with an eval config -> run harness -> scorecard
  4. DONE    all skills of a proposal pass layers 1-2 -> status: tested
             (layer 3 pending judge counts as pass until calibrated; a hard
             layer-1/2 failure marks the proposal build-failed and stops)

Human touchpoints are NOT here: grilling is interactive (orch grill) and
confirmation happens in the portal. The conductor only advances confirmed work.

Builds run through the `claude` CLI if present (or ANTHROPIC_API_KEY for the
judge). With neither, build steps are logged as SKIPPED so the rest of the
loop still functions.

Usage: python3 runner/conductor.py [--once] [--interval N]
Log:   analysis/conductor.log
"""
import sys, os, glob, re, json, time, subprocess
from shutil import which

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from client_config import require_client_config

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG = os.path.join(ROOT, "analysis", "conductor.log")
STAMP = os.path.join(ROOT, "analysis", ".facts-stamp")

def log(msg):
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line, flush=True)
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    with open(LOG, "a") as f:
        f.write(line + "\n")

# ---------- frontmatter helpers ----------
def read_fm(path):
    txt = open(path).read()
    m = re.match(r"^---\n([\s\S]*?)\n---", txt)
    meta = {}
    if m:
        for ln in m.group(1).splitlines():
            i = ln.find(":")
            if i > 0:
                meta[ln[:i].strip()] = ln[i + 1:].split("#")[0].strip()
    return meta, txt

def set_fm(path, key, value):
    meta, txt = read_fm(path)
    m = re.match(r"^---\n([\s\S]*?)\n---", txt)
    fm = m.group(1)
    if re.search(rf"^{key}:", fm, re.M):
        fm = re.sub(rf"^{key}:.*$", f"{key}: {value}", fm, flags=re.M)
    else:
        fm += f"\n{key}: {value}"
    open(path, "w").write(txt.replace(m.group(0), f"---\n{fm}\n---", 1))

def skills_of(meta):
    raw = meta.get("skills", "")
    raw = raw.strip("[]")
    return [s.strip() for s in raw.split(",") if s.strip()]

# ---------- stages ----------
def stage_facts():
    src = glob.glob(os.path.join(ROOT, "build-plans", "*.yaml"))
    latest = max((os.path.getmtime(p) for p in src), default=0)
    last = os.path.getmtime(STAMP) if os.path.exists(STAMP) else 0
    if latest > last:
        log("facts: build-plans changed — re-running extractor")
        r = subprocess.run([sys.executable, os.path.join(ROOT, "runner", "facts_extractor.py"), ROOT],
                           capture_output=True, text=True)
        log("facts: " + (r.stdout.strip().splitlines()[0] if r.returncode == 0 else "FAILED " + r.stderr[:200]))
        if r.returncode == 0:
            open(STAMP, "w").write(str(time.time()))

def build_skill(skill):
    sdir = os.path.join(ROOT, "skills", skill)
    brief = os.path.join(sdir, "BUILD_BRIEF.md")
    if not os.path.exists(brief):
        log(f"build {skill}: SKIPPED — no BUILD_BRIEF.md (grill/proposal should produce it)")
        return False
    if os.path.exists(os.path.join(sdir, "SKILL.md")):
        log(f"build {skill}: already built")
        return True
    if which("claude"):
        log(f"build {skill}: launching headless build")
        r = subprocess.run(
            ["claude", "-p",
             "Read BUILD_BRIEF.md in this directory and build the skill exactly per the brief. "
             "Create SKILL.md and any scripts. Do not change the contract; if the boundaries do not "
             "work, write CHANGE_REQUEST.md and stop.",
             "--output-format", "json"],
            cwd=sdir, capture_output=True, text=True, timeout=3600)
        ok = r.returncode == 0 and os.path.exists(os.path.join(sdir, "SKILL.md"))
        log(f"build {skill}: {'done' if ok else 'FAILED'}")
        return ok
    log(f"build {skill}: SKIPPED — no `claude` CLI on PATH")
    return False

def test_skill(skill):
    cfg = os.path.join(ROOT, "skills", skill, "eval", "eval.yaml")
    if not os.path.exists(cfg):
        log(f"test {skill}: SKIPPED — no eval/eval.yaml")
        return None
    r = subprocess.run([sys.executable, os.path.join(ROOT, "evals", "harness", "run_evals.py"), skill],
                       capture_output=True, text=True)
    log(f"test {skill}: {'gate PASS' if r.returncode == 0 else 'gate FAIL'}")
    return r.returncode == 0

def stage_proposals():
    for p in sorted(glob.glob(os.path.join(ROOT, "proposals", "*.md"))):
        if os.path.basename(p) == "TEMPLATE.md":
            continue
        meta, _ = read_fm(p)
        status = meta.get("status", "")
        names = skills_of(meta)
        if status == "confirmed":
            log(f"{os.path.basename(p)}: confirmed -> building ({len(names)} skills)")
            set_fm(p, "status", "building")
            status = "building"
        if status == "building":
            if not names:
                log(f"{os.path.basename(p)}: no skills listed in frontmatter — waiting")
                continue
            results = []
            for s in names:  # proposal lists shared deps first by convention
                built = build_skill(s)
                results.append(test_skill(s) if built else None)
            if all(r is True for r in results):
                set_fm(p, "status", "tested")
                log(f"{os.path.basename(p)}: all skills pass -> tested")
            elif any(r is False for r in results):
                set_fm(p, "status", "build-failed")
                log(f"{os.path.basename(p)}: eval gate failure -> build-failed (see scorecards)")
            # None results (skipped builds) leave status at building for next tick

def tick():
    stage_facts()
    stage_proposals()

if __name__ == "__main__":
    require_client_config(ROOT)
    once = "--once" in sys.argv
    interval = 15
    if "--interval" in sys.argv:
        interval = int(sys.argv[sys.argv.index("--interval") + 1])
    log("conductor started" + (" (single tick)" if once else f" (every {interval}s)"))
    while True:
        try:
            tick()
        except Exception as e:
            log(f"ERROR: {e}")
        if once:
            break
        time.sleep(interval)
