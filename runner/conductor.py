#!/usr/bin/env python3
"""Conductor daemon — the autonomous half of the pipeline.

Loop (default every 15s):
  1. FACTS   build-plans/ changed since last facts run -> re-run facts_extractor
  2. BUILD   proposal status: confirmed -> building; run headless builds for its
             skills (shared deps first, one at a time, fresh process each)
  3. TEST    built skills with an eval config -> run harness -> scorecard
  4. REFINE  on an implementation-shaped gate failure, re-run the builder
             against the specific failing checks, then re-test — bounded by the
             same attempt budget, with the confirmed test suite re-hashed before
             and after every attempt
  5. DONE    all skills of a proposal pass layers 1-2 -> status: tested
             (layer 3 pending judge counts as pass until calibrated; a failure
             that survives the budget marks the proposal build-failed)

Human touchpoints are NOT here: grilling is interactive (orch grill) and
confirmation happens in the portal. The conductor only advances confirmed work.

Builds are budgeted: each skill gets at most BUILD_ATTEMPT_CAP attempts per
proposal version, counted in skills/<skill>/.build-attempts and shared between
clean builds and refines (open question 1 in the improvement plan: one pooled
budget of 3 in v1, to be revisited with retrospect data). The counter resets
when a proposal is confirmed and when the gate passes. A builder that writes
CHANGE_REQUEST.md stops the proposal instead of being rebuilt — there the
contract failed, not the build.

Builds run through the `claude` CLI if present (or ANTHROPIC_API_KEY for the
judge). With neither, build steps are logged as SKIPPED so the rest of the
loop still functions.

Usage: python3 runner/conductor.py [--once] [--interval N]
Log:   analysis/conductor.log
"""
import sys, os, glob, json, time, subprocess
from shutil import which

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from client_config import require_client_config
from fm import read_fm, set_fm
from eval_suite import config_path, skills_missing_suite, suite_hash

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG = os.path.join(ROOT, "analysis", "conductor.log")
STAMP = os.path.join(ROOT, "analysis", ".facts-stamp")
LOCK = os.path.join(ROOT, "analysis", ".conductor-lock")

BUILD_ATTEMPT_CAP = 3
LOCK_STALE_SECONDS = 10 * 60

def log(msg):
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line, flush=True)
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    with open(LOG, "a") as f:
        f.write(line + "\n")

def skills_of(meta):
    raw = meta.get("skills", [])
    if isinstance(raw, str):
        raw = raw.strip("[]").split(",")
    return [str(s).strip() for s in raw if str(s).strip()]

# ---------- single-conductor guard ----------
def _pid_alive(pid):
    try:
        os.kill(pid, 0)
    except (OSError, TypeError):
        return False
    return True

def lock_holder():
    """Returns the lock record if another conductor still holds it, else None."""
    if not os.path.exists(LOCK):
        return None
    try:
        with open(LOCK) as f:
            held = json.load(f)
    except (OSError, ValueError):
        return None
    if held.get("pid") == os.getpid():
        return None
    fresh = time.time() - held.get("timestamp", 0) < LOCK_STALE_SECONDS
    # Freshness covers a conductor on another host (CI); pid liveness covers a
    # local tick that has been inside a long build for more than the window.
    return held if fresh or _pid_alive(held.get("pid")) else None

def take_lock():
    os.makedirs(os.path.dirname(LOCK), exist_ok=True)
    with open(LOCK, "w") as f:
        json.dump({"pid": os.getpid(), "timestamp": time.time()}, f)

def release_lock():
    try:
        with open(LOCK) as f:
            mine = json.load(f).get("pid") == os.getpid()
        if mine:
            os.unlink(LOCK)
    except (OSError, ValueError):
        pass

# ---------- build budget ----------
def attempts_file(skill):
    return os.path.join(ROOT, "skills", skill, ".build-attempts")

def attempts_used(skill):
    try:
        with open(attempts_file(skill)) as f:
            return int(f.read().strip() or 0)
    except (OSError, ValueError):
        return 0

def record_attempt(skill):
    used = attempts_used(skill) + 1
    path = attempts_file(skill)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(str(used))
    return used

def clear_attempts(skill):
    if os.path.exists(attempts_file(skill)):
        os.unlink(attempts_file(skill))

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
    """Returns built | change-request | blocked | retry | exhausted | skipped."""
    sdir = os.path.join(ROOT, "skills", skill)
    if os.path.exists(os.path.join(sdir, "CHANGE_REQUEST.md")):
        log(f"build {skill}: CHANGE_REQUEST.md present — contract problem, not rebuilding")
        return "change-request"
    if not os.path.exists(config_path(ROOT, skill)):
        # The builder must not author its own exam: no confirmed suite, no build.
        log(f"build {skill}: BLOCKED — no confirmed eval/eval.yaml to build against")
        return "blocked"
    if os.path.exists(os.path.join(sdir, "SKILL.md")):
        log(f"build {skill}: already built")
        return "built"
    if not os.path.exists(os.path.join(sdir, "BUILD_BRIEF.md")):
        log(f"build {skill}: SKIPPED — no BUILD_BRIEF.md (grill/proposal should produce it)")
        return "skipped"
    if not which("claude"):
        log(f"build {skill}: SKIPPED — no `claude` CLI on PATH")
        return "skipped"
    if attempts_used(skill) >= BUILD_ATTEMPT_CAP:
        log(f"build {skill}: budget exhausted ({BUILD_ATTEMPT_CAP} attempts) — not rebuilding")
        return "exhausted"

    attempt = record_attempt(skill)
    log(f"build {skill}: launching headless build (attempt {attempt}/{BUILD_ATTEMPT_CAP})")
    r = subprocess.run(
        ["claude", "-p",
         "Read BUILD_BRIEF.md in this directory and build the skill exactly per the brief. "
         "Create SKILL.md and any scripts. Do not change the contract; if the boundaries do not "
         "work, write CHANGE_REQUEST.md and stop.",
         "--output-format", "json"],
        cwd=sdir, capture_output=True, text=True, timeout=3600)
    if os.path.exists(os.path.join(sdir, "CHANGE_REQUEST.md")):
        log(f"build {skill}: builder raised a change request")
        return "change-request"
    if r.returncode == 0 and os.path.exists(os.path.join(sdir, "SKILL.md")):
        log(f"build {skill}: done")
        return "built"
    if attempt >= BUILD_ATTEMPT_CAP:
        log(f"build {skill}: FAILED on final attempt {attempt}/{BUILD_ATTEMPT_CAP}")
        return "exhausted"
    log(f"build {skill}: FAILED (attempt {attempt}/{BUILD_ATTEMPT_CAP}) — retrying next tick")
    return "retry"

def test_skill(skill):
    """Returns pass | fail | blocked."""
    if not os.path.exists(config_path(ROOT, skill)):
        log(f"test {skill}: BLOCKED — no eval/eval.yaml (the confirmed test suite is missing)")
        return "blocked"
    r = subprocess.run([sys.executable, os.path.join(ROOT, "evals", "harness", "run_evals.py"), skill],
                       capture_output=True, text=True)
    if r.returncode == 2:  # the suite could not run: missing output or fixtures
        log(f"test {skill}: BLOCKED — {r.stdout.strip().splitlines()[-1] if r.stdout.strip() else 'suite could not run'}")
        return "blocked"
    log(f"test {skill}: {'gate PASS' if r.returncode == 0 else 'gate FAIL'}")
    return "pass" if r.returncode == 0 else "fail"

# ---------- convergence loop ----------
def scorecard(skill):
    try:
        with open(os.path.join(ROOT, "skills", skill, "eval", "scorecard.json")) as f:
            return json.load(f)
    except (OSError, ValueError):
        return None

def archive_scorecard(skill, attempt):
    """Keep one scorecard per attempt — the paper trail for triage and retrospect."""
    live = os.path.join(ROOT, "skills", skill, "eval", "scorecard.json")
    if not os.path.exists(live):
        return
    with open(live) as f:
        body = f.read()
    with open(os.path.join(ROOT, "skills", skill, "eval", f"scorecard.attempt-{attempt}.json"), "w") as f:
        f.write(body)

def failing_checks(skill):
    """The specific checks a refine attempt has to satisfy."""
    card = scorecard(skill) or {}
    failing = [c["check"] for c in card.get("layer1", {}).get("checks", []) if not c.get("pass")]
    ungrounded = card.get("layer2", {}).get("ungrounded", [])
    if ungrounded:
        failing.append("layer2: numbers not traceable to a source fixture: " + ", ".join(ungrounded))
    if card.get("gate", {}).get("layer3") is False:
        avg = card.get("layer3", {}).get("overall_avg")
        failing.append(f"layer3: judge rubric average {avg} is below the confirmed threshold")
    return failing

def failure_shape(skill):
    """implementation (refine-eligible) | environment (escalate).

    Deterministic and deliberately narrow — Phase 2 replaces this heuristic with
    triage verdicts. Anything it cannot recognise escalates rather than burning
    budget on a refine that was never going to help.
    """
    return "implementation" if failing_checks(skill) else "environment"

def suite_tampered(skills, expected_hash):
    """The frozen hash covers the whole proposal, so any skill's suite counts."""
    if not expected_hash:
        return False
    return suite_hash(ROOT, skills) != expected_hash

def refine_skill(skill, failing):
    """One bounded refine attempt: fix the output against the failing checks."""
    sdir = os.path.join(ROOT, "skills", skill)
    if not which("claude"):
        log(f"refine {skill}: SKIPPED — no `claude` CLI on PATH")
        return "skipped"
    attempt = record_attempt(skill)
    log(f"refine {skill}: attempt {attempt}/{BUILD_ATTEMPT_CAP} against {len(failing)} failing check(s)")
    subprocess.run(
        ["claude", "-p",
         "The eval gate for this skill failed. Read BUILD_BRIEF.md and eval/scorecard.json in this "
         "directory, then fix the skill and its output so these checks pass:\n"
         + "\n".join(f"- {c}" for c in failing)
         + "\neval/eval.yaml and everything under fixtures/ are read-only context — the test suite "
           "was confirmed with the contract and must not be edited. If the failing checks cannot be "
           "satisfied within the contract, write CHANGE_REQUEST.md and stop.",
         "--output-format", "json"],
        cwd=sdir, capture_output=True, text=True, timeout=3600)
    if os.path.exists(os.path.join(sdir, "CHANGE_REQUEST.md")):
        log(f"refine {skill}: builder raised a change request")
        return "change-request"
    return "refined"

def converge_skill(skill, proposal_skills, expected_hash):
    """Build, test, and refine until the gate passes or the budget runs out.

    No LLM drives this loop: the scheduler decides, and each iteration is a
    fresh sealed subprocess. The suite is re-hashed before and after every
    attempt, so 'never weaken a test to pass it' is enforced mechanically.
    """
    evaluation = 0
    while True:
        if suite_tampered(proposal_skills, expected_hash):
            log(f"{skill}: TAMPERED — the confirmed test suite changed since it was frozen")
            return "tampered"
        built = build_skill(skill)
        if built != "built":
            return built
        result = test_skill(skill)
        evaluation += 1
        archive_scorecard(skill, evaluation)
        if suite_tampered(proposal_skills, expected_hash):
            log(f"{skill}: TAMPERED — the test suite changed during the attempt")
            return "tampered"
        if result == "pass":
            clear_attempts(skill)
            return "pass"
        if result != "fail":
            return result
        failing = failing_checks(skill)
        if failure_shape(skill) != "implementation":
            log(f"{skill}: eval failure is environment-shaped — escalating instead of refining")
            return "blocked"
        if attempts_used(skill) >= BUILD_ATTEMPT_CAP:
            log(f"{skill}: budget exhausted with {len(failing)} check(s) still failing")
            return "exhausted"
        refined = refine_skill(skill, failing)
        if refined != "refined":
            return "change-request" if refined == "change-request" else "retry"

# Outcomes that stop a proposal, most severe first, and the status each sets.
TERMINAL_OUTCOMES = [
    ("tampered", "build-failed"),
    ("exhausted", "build-failed"),
    ("fail", "build-failed"),
    ("blocked", "blocked"),
    ("change-request", "changes-requested"),
]
TERMINAL_NAMES = [outcome for outcome, _ in TERMINAL_OUTCOMES]

def confirm_proposal(path, meta):
    """Freeze the confirmed test suite, then open the proposal for building.

    The hash is taken here, before the first build attempt, so tampering on any
    attempt is caught — not just tampering inside the refine loop.
    """
    name = os.path.basename(path)
    names = skills_of(meta)
    missing = skills_missing_suite(ROOT, names)
    if missing:
        set_fm(path, "status", "blocked")
        log(f"{name}: BLOCKED — no confirmed eval/eval.yaml for: {', '.join(missing)}")
        return "blocked"
    frozen = suite_hash(ROOT, names)
    for skill in names:  # the budget is per skill per proposal version
        clear_attempts(skill)
    set_fm(path, "eval_hash", frozen)
    set_fm(path, "status", "building")
    log(f"{name}: confirmed -> building ({len(names)} skills, eval_hash {frozen[:12]})")
    return "building"

def advance_proposal(path, meta):
    name = os.path.basename(path)
    names = skills_of(meta)
    if not names:
        log(f"{name}: no skills listed in frontmatter — waiting")
        return
    expected_hash = meta.get("eval_hash")
    outcomes = []
    for skill in names:  # proposal lists shared deps first by convention
        outcomes.append(converge_skill(skill, names, expected_hash))
        # Later skills build on the earlier ones; stop rather than build on sand.
        if outcomes[-1] in TERMINAL_NAMES:
            break
    for outcome, status in TERMINAL_OUTCOMES:
        if outcome in outcomes:
            set_fm(path, "status", status)
            log(f"{name}: {outcome} -> {status}")
            return
    if all(o == "pass" for o in outcomes):
        set_fm(path, "status", "tested")
        log(f"{name}: all skills pass -> tested")
    # skipped/retry outcomes leave the proposal at building for the next tick

def stage_proposals():
    for p in sorted(glob.glob(os.path.join(ROOT, "proposals", "*.md"))):
        if os.path.basename(p) == "TEMPLATE.md":
            continue
        meta, _ = read_fm(p)
        status = meta.get("status", "")
        if status == "confirmed":
            status = confirm_proposal(p, meta)
        if status == "building":
            advance_proposal(p, meta)

def tick():
    held = lock_holder()
    if held:
        log(f"tick skipped — conductor pid {held.get('pid')} holds the lock")
        return
    take_lock()
    stage_facts()
    stage_proposals()

if __name__ == "__main__":
    require_client_config(ROOT)
    once = "--once" in sys.argv
    interval = 15
    if "--interval" in sys.argv:
        interval = int(sys.argv[sys.argv.index("--interval") + 1])
    log("conductor started" + (" (single tick)" if once else f" (every {interval}s)"))
    try:
        while True:
            try:
                tick()
            except Exception as e:
                log(f"ERROR: {e}")
            if once:
                break
            time.sleep(interval)
    finally:
        release_lock()
