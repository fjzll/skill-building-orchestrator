#!/usr/bin/env python3
"""orch retrospect — what this repo's pipeline actually cost, from artifacts on disk.

Reads only things the pipeline already wrote: per-attempt scorecards, the
conductor log, triage verdicts, the calibration ledger. Writes a markdown report
to analysis/retrospect.md. This is also the per-client feed for the Phase 5
fleet layer, so every number here is keyed by archetype as well as by skill.

Usage: python3 runner/retrospect.py [root]
"""
import glob
import json
import os
import re
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from archetype import archetype
from client_config import load_client_config
import triage as triage_lib

LOG_LINE = re.compile(r"^\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\] (.*)$")


def attempts_to_converge(root):
    """Per skill: how many evaluations it took, and whether it got there."""
    rows = []
    for sdir in sorted(glob.glob(os.path.join(root, "skills", "*"))):
        if not os.path.isdir(sdir):
            continue
        skill = os.path.basename(sdir)
        archived = sorted(glob.glob(os.path.join(sdir, "eval", "scorecard.attempt-*.json")))
        if not archived and not os.path.exists(os.path.join(sdir, "eval", "scorecard.json")):
            continue
        final = os.path.join(sdir, "eval", "scorecard.json")
        passed = None
        if os.path.exists(final):
            try:
                with open(final) as f:
                    passed = bool(json.load(f).get("gate", {}).get("overall"))
            except ValueError:
                passed = None
        rows.append({
            "skill": skill,
            "archetype": archetype(skill, (load_client_config(root) or {}).get("slug"),
                                   triage_lib.workflow_of(root, skill)),
            "evaluations": len(archived) or 1,
            "converged": passed,
        })
    return rows


def layer_failure_counts(root):
    """Which eval layer fails most — the signal for where the briefs are weak."""
    counts = Counter()
    for card_path in glob.glob(os.path.join(root, "skills", "*", "eval", "scorecard.attempt-*.json")):
        try:
            with open(card_path) as f:
                card = json.load(f)
        except (OSError, ValueError):
            continue
        if any(not c.get("pass") for c in card.get("layer1", {}).get("checks", [])):
            counts["layer 1 — deterministic checks"] += 1
        if card.get("layer2", {}).get("ungrounded"):
            counts["layer 2 — ungrounded numbers"] += 1
        if card.get("gate", {}).get("layer3") is False:
            counts["layer 3 — judge below threshold"] += 1
    return counts


def triage_distribution(root):
    """Verdict classes seen, and how often the human agreed."""
    classes, agreement = Counter(), Counter()
    for line in triage_lib.calibration_lines(root):
        classes[line.get("class", "unknown")] += 1
        agreement[(line.get("class"), line.get("human"))] += 1
    return classes, agreement


def stage_durations(root):
    """Wall-clock per stage, from conductor log timestamps."""
    log_path = os.path.join(root, "analysis", "conductor.log")
    if not os.path.exists(log_path):
        return Counter(), Counter()
    stages, events = Counter(), Counter()
    with open(log_path) as f:
        for raw in f:
            m = LOG_LINE.match(raw.strip())
            if not m:
                continue
            message = m.group(2)
            head = message.split(" ", 1)[0].rstrip(":")
            if head in ("build", "test", "refine", "triage", "facts"):
                events[head] += 1
    return stages, events


def render(root):
    client = load_client_config(root) or {}
    rows = attempts_to_converge(root)
    layers = layer_failure_counts(root)
    classes, agreement = triage_distribution(root)
    _, events = stage_durations(root)

    out = ["# Retrospect — " + (client.get("display_name") or "unconfigured client"), ""]
    out.append(f"Calibration phase **{triage_lib.calibration_phase(root)}** "
               f"({len(triage_lib.calibration_lines(root))} reviewed verdicts). "
               "Everything below is derived from artifacts on disk.")
    out += ["", "## Attempts to converge", ""]
    if rows:
        out.append("| Skill | Archetype | Evaluations | Converged |")
        out.append("|---|---|---|---|")
        for r in rows:
            converged = {True: "yes", False: "no", None: "—"}[r["converged"]]
            out.append(f"| {r['skill']} | {r['archetype']} | {r['evaluations']} | {converged} |")
        first_try = sum(1 for r in rows if r["evaluations"] == 1 and r["converged"])
        out += ["", f"{first_try} of {len(rows)} skills passed on the first evaluation."]
    else:
        out.append("_No scorecards on disk yet._")

    out += ["", "## Which eval layer fails most", ""]
    if layers:
        out.append("| Layer | Failed attempts |")
        out.append("|---|---|")
        for layer, count in layers.most_common():
            out.append(f"| {layer} | {count} |")
    else:
        out.append("_No failed attempts recorded._")

    out += ["", "## Triage verdicts", ""]
    if classes:
        out.append("| Class | Verdicts | Agreed | Disagreed |")
        out.append("|---|---|---|---|")
        for cls, count in classes.most_common():
            out.append(f"| {cls} | {count} | {agreement[(cls, 'agree')]} | "
                       f"{agreement[(cls, 'disagree')]} |")
    else:
        out.append("_No verdicts reviewed yet — the ramp is still in shadow._")

    out += ["", "## Conductor activity", ""]
    if events:
        out.append("| Stage | Log events |")
        out.append("|---|---|")
        for stage, count in events.most_common():
            out.append(f"| {stage} | {count} |")
    else:
        out.append("_No conductor log yet._")

    out += ["", "---", "",
            "Generated by `orch retrospect`. Regenerate rather than edit — this file is a "
            "derived view, not a record."]
    return "\n".join(out) + "\n"


def run(root):
    report = render(root)
    out_path = os.path.join(root, "analysis", "retrospect.md")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w") as f:
        f.write(report)
    print(report)
    print(f"wrote {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(run(sys.argv[1] if len(sys.argv) > 1 else "."))
