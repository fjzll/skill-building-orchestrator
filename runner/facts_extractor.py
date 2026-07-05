#!/usr/bin/env python3
"""Pre-grill facts extractor.

Reads build-plans/*.yaml + workflow-map.yaml and emits facts.yaml:
deterministic extractions only (no hypotheses) —
  - shared-skill candidates (from workflow map shared_foundations + nested slices)
  - human gates per slice (steps with human-review / human states)
  - access-to-confirm steps
  - cross-slice dependencies (nested_slice references)
  - open items / open questions
  - grill order (shared first, then Decision Lens rank)

Usage: python3 runner/facts_extractor.py [repo_root]
Output: analysis/facts.yaml
"""
import sys, os, glob
import yaml

def load(path):
    with open(path) as f:
        return yaml.safe_load(f)

def main(root="."):
    bp_dir = os.path.join(root, "build-plans")
    wf_map = load(os.path.join(bp_dir, "workflow-map.yaml"))
    slices = {}
    for p in sorted(glob.glob(os.path.join(bp_dir, "jpe-*.yaml"))):
        s = load(p)
        slices[str(s["slice"])] = s

    client = wf_map["client"]["code"].lower()
    facts = {
        "client": wf_map["client"],
        "generated_by": "facts_extractor.py (deterministic; no hypotheses)",
        "workflows": [],
        "shared_skill_candidates": [],
        "cross_slice_dependencies": [],
        "grill_order": [],
    }

    # shared foundations -> shared skill candidates
    for sf in wf_map.get("shared_foundations", []):
        facts["shared_skill_candidates"].append({
            "candidate_name": f"{client}-shared-{sf['id']}",
            "foundation": sf["id"],
            "why": sf.get("why"),
            "used_by": sf.get("used_by"),
            "slice_home": sf.get("slice_home"),
        })

    # nested-slice references -> dependencies
    for sid, s in slices.items():
        for step in s.get("steps", []):
            ns = step.get("nested_slice")
            if ns:
                facts["cross_slice_dependencies"].append({
                    "from_slice": sid, "at_step": str(step["id"]),
                    "depends_on_slice": str(ns),
                })

    # per-workflow facts
    rank_order = []
    for w in wf_map["workflows"]:
        wf = {
            "id": w["id"], "name": w["name"],
            "slices": w.get("slices", []),
            "shared_slice_deps": w.get("shared_slice_deps", []),
            "decision_lens_rank": w.get("decision_lens_rank"),
            "human_gates": [], "access_to_confirm": [], "open_items": [],
            "ai_segments": [],
        }
        for sid in w.get("slices", []):
            s = slices.get(str(sid))
            if not s:
                continue
            seg = []
            for step in s.get("steps", []):
                states = step.get("states", [])
                ref = {"slice": str(sid), "step": str(step["id"]), "title": step["title"]}
                if "human-review" in states or "human" in states:
                    wf["human_gates"].append({**ref, "states": states})
                    if seg:
                        wf["ai_segments"].append({"slice": str(sid), "steps": seg})
                        seg = []
                else:
                    seg.append(str(step["id"]))
                if "access-to-confirm" in states:
                    wf["access_to_confirm"].append(ref)
            if seg:
                wf["ai_segments"].append({"slice": str(sid), "steps": seg})
            for oq in s.get("open_questions", []) or []:
                wf["open_items"].append({"slice": str(sid), **oq})
        facts["workflows"].append(wf)
        rank_order.append((w.get("decision_lens_rank"), w["id"]))

    # grill order: shared candidates first, then workflows by rank (parallel foundation last-but-parallel)
    def rank_key(r):
        return 0 if r == "parallel-foundation" else int(r) if str(r).isdigit() else 99
    ordered = sorted(rank_order, key=lambda t: rank_key(t[0]))
    facts["grill_order"] = (
        [{"session": 1, "subject": "shared-skill candidates", "type": "shared"}]
        + [{"session": i + 2, "subject": wid, "type": "workflow", "rank": str(r)}
           for i, (r, wid) in enumerate(ordered)]
    )

    out_dir = os.path.join(root, "analysis")
    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, "facts.yaml")
    with open(out, "w") as f:
        yaml.safe_dump(facts, f, sort_keys=False, allow_unicode=True, width=100)
    print(f"wrote {out}")
    print(f"  workflows: {len(facts['workflows'])}")
    print(f"  shared candidates: {len(facts['shared_skill_candidates'])}")
    print(f"  cross-slice deps: {len(facts['cross_slice_dependencies'])}")

if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else ".")
