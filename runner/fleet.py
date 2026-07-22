#!/usr/bin/env python3
"""Fleet layer — template upgrades and calibration transfer across client repos.

Two jobs, both files-and-git only:

**Upgrade path.** ENGINE_PATHS is the boundary between what the template owns
and what a client owns. The upgrade bot diffs only those paths, so merging an
upgrade PR can never touch a client's ledger, proposals, skills, or facts.

**Calibration transfer.** A verdict is evidence about an archetype — a shape of
work — not about the client it happened at. Aggregating verdicts fleet-wide by
archetype lets a new client *start* where the fleet already has evidence,
instead of grinding out its own ten agreements for the same shape of work.

The transfer is deliberately asymmetric. Fleet priors set a starting phase and
nothing more: a local disagreement demotes immediately and the prior cannot
override it, and a contract misclassification anywhere zeroes that archetype's
prior for everyone. Evidence accelerates trust; only local evidence sustains it.

Usage:
  python3 runner/fleet.py aggregate <fleet-dir> <client-repo> [<client-repo> ...]
  python3 runner/fleet.py priors <fleet-dir> [-o <out.yaml>]
"""
import json
import os
import sys
from collections import defaultdict

import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import triage as triage_lib

# Paths the template owns. Everything else in a client repo is client data and
# is never touched by an upgrade.
ENGINE_PATHS = ["runner/", "evals/", "portal/", "docs/", "tests/", ".github/", "orch"]

PRIORS_FILE = os.path.join("analysis", "fleet-priors.yaml")

# A fleet prior is granted at the same bar as local autonomy, plus a breadth
# requirement so one busy client cannot speak for the fleet.
PRIOR_BAR = 10
IMPLEMENTATION_PRIOR_BAR = 20
IMPLEMENTATION_MIN_CLIENTS = 3


def calibration_dir(fleet_dir):
    return os.path.join(fleet_dir, "calibration")


def aggregate(fleet_dir, client_roots):
    """Pull every client's calibration ledger into per-archetype fleet files."""
    by_archetype = defaultdict(list)
    for root in client_roots:
        slug = os.path.basename(os.path.abspath(root))
        config = os.path.join(root, "client.yaml")
        if os.path.exists(config):
            with open(config) as f:
                slug = (yaml.safe_load(f) or {}).get("slug", slug)
        for line in triage_lib.calibration_lines(root):
            line = dict(line, client=slug)
            by_archetype[line.get("archetype") or "unknown"].append(line)

    out_dir = calibration_dir(fleet_dir)
    os.makedirs(out_dir, exist_ok=True)
    for archetype, lines in by_archetype.items():
        path = os.path.join(out_dir, archetype.replace("/", "__") + ".jsonl")
        lines.sort(key=lambda l: l.get("timestamp", ""))
        with open(path, "w") as f:
            for line in lines:
                f.write(json.dumps(line) + "\n")
    return {a: len(l) for a, l in by_archetype.items()}


def fleet_lines(fleet_dir):
    """Every aggregated verdict, keyed by archetype."""
    out_dir = calibration_dir(fleet_dir)
    if not os.path.isdir(out_dir):
        return {}
    by_archetype = {}
    for name in sorted(os.listdir(out_dir)):
        if not name.endswith(".jsonl"):
            continue
        archetype = name[: -len(".jsonl")].replace("__", "/")
        lines = []
        with open(os.path.join(out_dir, name)) as f:
            for raw in f:
                raw = raw.strip()
                if raw:
                    try:
                        lines.append(json.loads(raw))
                    except ValueError:
                        continue
        by_archetype[archetype] = lines
    return by_archetype


def compute_priors(fleet_dir):
    """Starting phase per archetype, per class, from fleet-wide evidence."""
    priors = {}
    for archetype, lines in fleet_lines(fleet_dir).items():
        # Circuit breaker: one contract misclassification anywhere in the fleet
        # zeroes this archetype's prior entirely. This is the drift failure mode
        # the whole design exists to prevent — treat it fleet-wide.
        if any(l.get("actual_class") == "contract" for l in lines):
            continue
        grants = {}
        for verdict_class, bar, min_clients in (
            ("transient", PRIOR_BAR, 1),
            ("implementation", IMPLEMENTATION_PRIOR_BAR, IMPLEMENTATION_MIN_CLIENTS),
        ):
            agreed = [l for l in lines if l.get("class") == verdict_class and l.get("human") == "agree"]
            disagreed = any(l.get("class") == verdict_class and l.get("human") != "agree"
                            for l in lines)
            clients = {l.get("client") for l in agreed}
            if not disagreed and len(agreed) >= bar and len(clients) >= min_clients:
                grants[verdict_class] = {"agreements": len(agreed), "clients": sorted(clients)}
        # The ramp is ordered fleet-wide too.
        if "implementation" in grants and "transient" not in grants:
            del grants["implementation"]
        if grants:
            priors[archetype] = grants
    return priors


def write_priors(priors, out_path):
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    header = (
        "# Generated by `python3 runner/fleet.py priors` — do not hand-edit.\n"
        "# Fleet evidence, by archetype, that lets this client START at an\n"
        "# autonomy phase instead of earning it from zero. A local disagreement\n"
        "# always demotes locally and immediately; these priors never override\n"
        "# a local reset.\n"
    )
    with open(out_path, "w") as f:
        f.write(header)
        yaml.safe_dump({"archetypes": priors}, f, sort_keys=True, default_flow_style=False)
    return out_path


def load_priors(root):
    path = os.path.join(root, PRIORS_FILE)
    if not os.path.exists(path):
        return {}
    with open(path) as f:
        return (yaml.safe_load(f) or {}).get("archetypes") or {}


def locally_demoted(root, verdict_class, archetype):
    """Has this repo disagreed with a verdict of this class for this archetype?

    One disagreement is enough, and it is permanent for the prior: the fleet may
    say this shape of work is safe to automate, but this client has seen it be
    wrong here, and local evidence wins.
    """
    for line in triage_lib.calibration_lines(root):
        if line.get("class") != verdict_class or line.get("archetype") != archetype:
            continue
        if line.get("human") != "agree" or line.get("actual_class") == "contract":
            return True
    return False


def prior_grants(root, verdict_class, archetype):
    """Does fleet evidence grant this class autonomy for this archetype here?"""
    if not archetype or verdict_class not in triage_lib.AUTOMATABLE_CLASSES:
        return False
    grants = load_priors(root).get(archetype) or {}
    if verdict_class not in grants:
        return False
    if locally_demoted(root, verdict_class, archetype):
        return False
    if verdict_class == "implementation" and not prior_grants(root, "transient", archetype):
        return False  # ordered ramp, same as locally
    return True


def main(argv):
    if len(argv) >= 3 and argv[0] == "aggregate":
        counts = aggregate(argv[1], argv[2:])
        for archetype, count in sorted(counts.items()):
            print(f"{archetype}: {count} verdicts")
        print(f"wrote {calibration_dir(argv[1])}")
        return 0
    if len(argv) >= 2 and argv[0] == "priors":
        priors = compute_priors(argv[1])
        out = argv[argv.index("-o") + 1] if "-o" in argv else PRIORS_FILE
        write_priors(priors, out)
        for archetype, grants in sorted(priors.items()):
            print(f"{archetype}: {', '.join(sorted(grants))}")
        print(f"wrote {out}")
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
