"""Failure triage — the LLM recovery hook, and the calibration ramp that gates it.

The conductor stays a scheduler. When a stage fails terminally it spawns a
triage session (fresh context, sealed subprocess) seeded with the artifacts
that hold the objective — proposal, ledger with its why-nots, error evidence,
facts — and that session writes a verdict file. The verdict is a document, not
an action: what the conductor is allowed to *do* with it is decided here, from
calibration data, per failure class.

Autonomy is earned, never assumed:

    Phase 0  shadow          verdict written, conductor behaviour unchanged
    Phase 1  transient auto  after AUTONOMY_BAR consecutive agreements
    Phase 2  implementation  same bar; an implementation verdict that was
                             really a contract problem zeroes the counter

`contract` and `environment` never automate. That is the whole point of the
design and no amount of agreement data changes it.
"""
import json
import os
import time

from archetype import archetype

VERDICT_FILE = "TRIAGE.md"
TICK_VERDICT_FILE = os.path.join("analysis", "TRIAGE-tick.md")
CALIBRATION_FILE = os.path.join("analysis", "triage-calibration.jsonl")
PROMPT_FILE = os.path.join("docs", "triage-prompt.md")

AUTONOMY_BAR = 10
AUTOMATABLE_CLASSES = ("transient", "implementation")
NEVER_AUTOMATED = ("contract", "environment")


def verdict_path(root, skill):
    return os.path.join(root, "skills", skill, VERDICT_FILE)


def read_verdict(root, skill):
    """The verdict frontmatter, or None if this skill has no triage on record."""
    path = verdict_path(root, skill)
    if not os.path.exists(path):
        return None
    from fm import read_fm
    meta, _ = read_fm(path)
    return meta or None


def calibration_path(root):
    return os.path.join(root, CALIBRATION_FILE)


def calibration_lines(root):
    path = calibration_path(root)
    if not os.path.exists(path):
        return []
    lines = []
    with open(path) as f:
        for raw in f:
            raw = raw.strip()
            if not raw:
                continue
            try:
                lines.append(json.loads(raw))
            except ValueError:
                continue  # a malformed line must not silently skew the counts
    return lines


def workflow_of(root, skill):
    """The workflow whose proposal lists this skill — the archetype needs it."""
    from fm import read_fm
    directory = os.path.join(root, "proposals")
    if not os.path.isdir(directory):
        return None
    for name in sorted(os.listdir(directory)):
        if not name.endswith(".md") or name == "TEMPLATE.md":
            continue
        meta, _ = read_fm(os.path.join(directory, name))
        listed = meta.get("skills", [])
        if isinstance(listed, str):
            listed = listed.strip("[]").split(",")
        if skill in [str(s).strip() for s in listed]:
            return meta.get("workflow")
    return None


def record_agreement(root, skill, verdict_class, human, actual_class=None, client=None,
                     workflow=None):
    """Append one human verdict-review to the calibration ledger."""
    path = calibration_path(root)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    line = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "skill": skill,
        "archetype": archetype(skill, client, workflow or workflow_of(root, skill)),
        "class": verdict_class,
        "human": human,
        "actual_class": actual_class,
    }
    with open(path, "a") as f:
        f.write(json.dumps(line) + "\n")
    return line


def consecutive_agreements(root, verdict_class):
    """Agreements on this class since the most recent disagreement."""
    streak = 0
    for line in reversed(calibration_lines(root)):
        if line.get("class") != verdict_class:
            continue
        misclassified_contract = (verdict_class == "implementation"
                                  and line.get("actual_class") == "contract")
        if line.get("human") != "agree" or misclassified_contract:
            break
        streak += 1
    return streak


def is_automated(root, verdict_class):
    """Has this class earned autonomy yet? Read from data, not a config flag."""
    if verdict_class not in AUTOMATABLE_CLASSES:
        return False
    if verdict_class == "implementation" and not is_automated(root, "transient"):
        return False  # the ramp is ordered: transient first, then implementation
    return consecutive_agreements(root, verdict_class) >= AUTONOMY_BAR


def calibration_phase(root):
    """0 shadow | 1 transient auto | 2 implementation auto — for logs and reports."""
    if is_automated(root, "implementation"):
        return 2
    if is_automated(root, "transient"):
        return 1
    return 0


def build_prompt(root, skill, trigger, evidence_paths, output_relpath):
    """The triage brief: class definitions verbatim, plus where the evidence is."""
    with open(os.path.join(root, PROMPT_FILE)) as f:
        template = f.read()
    return (template
            .replace("{SKILL}", skill)
            .replace("{TRIGGER}", trigger)
            .replace("{OUTPUT}", output_relpath)
            .replace("{EVIDENCE}", "\n".join(f"- {p}" for p in evidence_paths) or "- (none on disk)"))


def evidence_for(root, skill):
    """Files that exist and bear on this failure, as repo-relative paths."""
    sdir = os.path.join("skills", skill)
    candidates = [
        os.path.join(sdir, "BUILD_BRIEF.md"),
        os.path.join(sdir, "CHANGE_REQUEST.md"),
        os.path.join(sdir, "eval", "eval.yaml"),
        os.path.join(sdir, "eval", "scorecard.json"),
        os.path.join(sdir, "BUILD_LOG.md"),
        os.path.join("analysis", "facts.yaml"),
        os.path.join("analysis", "conductor.log"),
    ]
    found = [p for p in candidates if os.path.exists(os.path.join(root, p))]
    for extra in ("proposals", "ledger"):
        directory = os.path.join(root, extra)
        if os.path.isdir(directory):
            found += [os.path.join(extra, f) for f in sorted(os.listdir(directory))
                      if f.endswith(".md") and f != "TEMPLATE.md"]
    return found
