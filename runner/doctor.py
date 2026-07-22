#!/usr/bin/env python3
"""orch doctor — is anything stuck, and is this machine able to run the pipeline?

Pure file inspection: no LLM, no network, no state of its own. Everything it
reports is derived from artifacts the pipeline already writes, so `doctor` can
never disagree with the system of record.

Usage: python3 runner/doctor.py [root]
Exit:  0 = healthy, 1 = something needs a human
"""
import glob
import json
import os
import sys
import time
from shutil import which

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from client_config import load_client_config
from eval_suite import config_path
from fm import read_fm
import triage as triage_lib

STALL_MINUTES = 30
AWAITING_HUMAN_HOURS = 24
BUILD_ATTEMPT_CAP = 3


def minutes_since(path):
    return (time.time() - os.path.getmtime(path)) / 60 if os.path.exists(path) else None


def environment_checks(root):
    """Can this machine actually run a build? Missing pieces surface as findings."""
    findings = []
    if not load_client_config(root):
        findings.append(("error", "no client.yaml — this is a template clone; run ./orch init"))
    if not which("claude"):
        findings.append(("warn", "no `claude` CLI on PATH — builds and triage will be skipped"))
    if not os.environ.get("ANTHROPIC_API_KEY"):
        findings.append(("warn", "ANTHROPIC_API_KEY unset — the layer 3 judge will stay pending"))
    if not os.path.exists(os.path.join(root, "analysis", "facts.yaml")):
        findings.append(("warn", "no analysis/facts.yaml — run ./orch facts"))
    if not os.path.isdir(os.path.join(root, "portal", "node_modules")):
        findings.append(("warn", "portal dependencies not installed — run npm install in portal/"))
    return findings


def lock_checks(root):
    lock = os.path.join(root, "analysis", ".conductor-lock")
    if not os.path.exists(lock):
        return []
    try:
        with open(lock) as f:
            held = json.load(f)
    except (OSError, ValueError):
        return [("warn", "analysis/.conductor-lock is unreadable — delete it")]
    age = (time.time() - held.get("timestamp", 0)) / 60
    if age > STALL_MINUTES:
        return [("warn", f"conductor lock held by pid {held.get('pid')} for {age:.0f} min — "
                         "stale locks are ignored after 10 min, but a wedged conductor is worth a look")]
    return []


def proposal_checks(root):
    findings = []
    for path in sorted(glob.glob(os.path.join(root, "proposals", "*.md"))):
        if os.path.basename(path) == "TEMPLATE.md":
            continue
        name = os.path.basename(path)
        meta, _ = read_fm(path)
        status = meta.get("status", "draft")
        if status in ("build-failed", "blocked"):
            findings.append(("error", f"{name}: {status} — see the Blockers tab"))
        elif status == "changes-requested":
            findings.append(("warn", f"{name}: changes requested — awaiting a re-grill or an edit"))
        elif status == "building":
            stalled = True
            for skill in _skills_of(meta):
                sdir = os.path.join(root, "skills", skill)
                recent = [minutes_since(os.path.join(sdir, f)) for f in
                          (".build-attempts", "SKILL.md", "BUILD_LOG.md")]
                recent = [m for m in recent if m is not None]
                if recent and min(recent) < STALL_MINUTES:
                    stalled = False
            if stalled:
                findings.append(("error", f"{name}: building with no attempt progress for "
                                          f"{STALL_MINUTES}+ min — stalled"))
        if status == "building" and not meta.get("eval_hash"):
            findings.append(("warn", f"{name}: building without a frozen eval_hash — "
                                     "confirmed before the test-suite gate existed?"))
    return findings


def _skills_of(meta):
    raw = meta.get("skills", [])
    if isinstance(raw, str):
        raw = raw.strip("[]").split(",")
    return [str(s).strip() for s in raw if str(s).strip()]


def skill_states(root):
    """Per-skill budget and gate state — the table `doctor` prints."""
    rows = []
    for sdir in sorted(glob.glob(os.path.join(root, "skills", "*"))):
        if not os.path.isdir(sdir):
            continue
        skill = os.path.basename(sdir)
        attempts = 0
        counter = os.path.join(sdir, ".build-attempts")
        if os.path.exists(counter):
            with open(counter) as f:
                attempts = int((f.read().strip() or "0"))
        gate = "not run"
        card = os.path.join(sdir, "eval", "scorecard.json")
        if os.path.exists(card):
            try:
                with open(card) as f:
                    gate = "pass" if json.load(f).get("gate", {}).get("overall") else "fail"
            except ValueError:
                gate = "unreadable"
        rows.append({
            "skill": skill,
            "attempts": f"{attempts}/{BUILD_ATTEMPT_CAP}",
            "gate": gate,
            "suite": "present" if os.path.exists(config_path(root, skill)) else "MISSING",
            "built": os.path.exists(os.path.join(sdir, "SKILL.md")),
        })
    return rows


def awaiting_human(root):
    """Change requests and triage verdicts nobody has looked at."""
    findings = []
    for sdir in sorted(glob.glob(os.path.join(root, "skills", "*"))):
        skill = os.path.basename(sdir)
        request = os.path.join(sdir, "CHANGE_REQUEST.md")
        if os.path.exists(request):
            hours = minutes_since(request) / 60
            level = "error" if hours > AWAITING_HUMAN_HOURS else "warn"
            findings.append((level, f"{skill}: CHANGE_REQUEST.md open for {hours:.0f}h"))
        verdict = triage_lib.read_verdict(root, skill)
        if verdict and not verdict.get("human"):
            hours = minutes_since(triage_lib.verdict_path(root, skill)) / 60
            level = "error" if hours > AWAITING_HUMAN_HOURS else "warn"
            findings.append((level, f"{skill}: triage verdict ({verdict.get('class')}) "
                                    f"awaiting review for {hours:.0f}h"))
    return findings


def run(root):
    findings = (environment_checks(root) + lock_checks(root)
                + proposal_checks(root) + awaiting_human(root))
    rows = skill_states(root)

    print("== orch doctor ==")
    print(f"calibration phase: {triage_lib.calibration_phase(root)} "
          f"({len(triage_lib.calibration_lines(root))} reviewed verdicts)")
    print()
    if rows:
        print(f"{'skill':<32} {'attempts':<10} {'suite':<9} {'gate':<10} built")
        for r in rows:
            print(f"{r['skill']:<32} {r['attempts']:<10} {r['suite']:<9} {r['gate']:<10} "
                  f"{'yes' if r['built'] else 'no'}")
        print()
    if not findings:
        print("no findings — pipeline healthy")
        return 0
    for level, message in findings:
        print(f"[{level.upper():<5}] {message}")
    return 1 if any(level == "error" for level, _ in findings) else 0


if __name__ == "__main__":
    sys.exit(run(sys.argv[1] if len(sys.argv) > 1 else "."))
