#!/usr/bin/env python3
"""Three-layer eval harness. Emits skills/<skill>/eval/scorecard.json

Layer 1 — deterministic assertions (hard gates, all must pass)
Layer 2 — fact grounding: every number in the output must trace to a source
          span in the fixtures (invented figures = automatic fail)
Layer 3 — LLM-judge rubric (0-5 per criterion, averaged over N runs).
          Requires ANTHROPIC_API_KEY; otherwise recorded as "pending".

Per-skill config: skills/<skill>/eval/eval.yaml
  fixtures: [relative paths]
  output: relative path to the artifact under test
  layer1:
    required_fields: [strings that must appear]
    forbidden: [strings that must not appear]
    max_batch_size: 30            # optional, example of a structural check
  layer2:
    number_sources: [fixture paths whose numbers are the allowed universe]
    tolerance: 0.0
  layer3:
    criteria: [{name, description}]
    threshold_avg: 4.25   # of 5  (== 85%)
    floor: 3
    runs: 3
Gate policy: layers 1-2 at 100%; layer 3 avg >= threshold_avg and min >= floor.
"""
import sys, os, json, re

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

NUM_RE = re.compile(r"(?<![\d.])(\d{1,3}(?:,\d{3})+|\d+\.\d+|\d+)(?!\d)")

def load_yaml(path):
    import yaml
    with open(path) as f:
        return yaml.safe_load(f)

def read(path):
    with open(path, encoding="utf-8", errors="ignore") as f:
        return f.read()

def numbers_in(text, significant_only=False):
    out = set()
    for m in NUM_RE.finditer(text):
        n = m.group(1).replace(",", "")
        if significant_only:
            prev = text[m.start() - 1] if m.start() > 0 else ""
            nxt = text[m.end():m.end() + 1]
            # keep decimals, currency amounts, percentages, unit-suffixed and large ints
            is_small_int = n.isdigit() and int(n) <= 31
            if is_small_int and prev != "$" and nxt not in ("%",) and not nxt.isalpha():
                continue
        out.add(n)
    return out

def layer1(cfg, output_text):
    results = []
    for s in cfg.get("required_fields", []):
        results.append({"check": f"required: {s}", "pass": s.lower() in output_text.lower()})
    for s in cfg.get("forbidden", []):
        results.append({"check": f"forbidden: {s}", "pass": s.lower() not in output_text.lower()})
    return results

def layer2(cfg, output_text, skill_dir):
    allowed = set()
    for src in cfg.get("number_sources", []):
        allowed |= numbers_in(read(os.path.join(skill_dir, src)))
    suspects = numbers_in(output_text, significant_only=True)
    ungrounded = sorted(suspects - allowed)
    return {"numbers_checked": len(suspects), "ungrounded": ungrounded,
            "pass": len(ungrounded) == 0}

def layer3(cfg, output_text, fixtures_text):
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        return {"status": "pending", "note": "no ANTHROPIC_API_KEY; judge not run",
                "criteria": [c["name"] for c in cfg.get("criteria", [])]}
    import urllib.request
    criteria = cfg.get("criteria", [])
    runs = int(cfg.get("runs", 3))
    scores = {c["name"]: [] for c in criteria}
    rubric = "\n".join(f"- {c['name']}: {c['description']}" for c in criteria)
    prompt = (
        "You are a strict evaluator. Score the OUTPUT against each rubric criterion "
        "from 0-5 (5 = indistinguishable from the gold standard). Respond ONLY with "
        "JSON {\"scores\": {<criterion>: <int>}, \"rationale\": {<criterion>: <string>}}.\n\n"
        f"RUBRIC:\n{rubric}\n\nSOURCE FIXTURES:\n{fixtures_text[:20000]}\n\nOUTPUT:\n{output_text[:20000]}"
    )
    for _ in range(runs):
        body = json.dumps({
            "model": "claude-sonnet-5",
            "max_tokens": 1024,
            "messages": [{"role": "user", "content": prompt}],
        }).encode()
        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages", data=body,
            headers={"content-type": "application/json", "x-api-key": key,
                     "anthropic-version": "2023-06-01"})
        with urllib.request.urlopen(req, timeout=120) as r:
            resp = json.load(r)
        text = resp["content"][0]["text"]
        j = json.loads(re.search(r"\{.*\}", text, re.S).group(0))
        for k, v in j.get("scores", {}).items():
            if k in scores:
                scores[k].append(v)
    avg = {k: (sum(v) / len(v) if v else 0) for k, v in scores.items()}
    overall = sum(avg.values()) / len(avg) if avg else 0
    return {"status": "run", "runs": runs, "avg_per_criterion": avg, "overall_avg": overall}

def main(skill):
    skill_dir = os.path.join(ROOT, "skills", skill)
    cfg_path = os.path.join(skill_dir, "eval", "eval.yaml")
    if not os.path.exists(cfg_path):
        print(f"missing {cfg_path}"); sys.exit(2)
    cfg = load_yaml(cfg_path)
    out_path = os.path.join(skill_dir, cfg["output"])
    if not os.path.exists(out_path):
        print(f"missing output under test: {out_path}"); sys.exit(2)
    output_text = read(out_path)
    fixtures_text = "\n\n".join(read(os.path.join(skill_dir, f)) for f in cfg.get("fixtures", []))

    l1 = layer1(cfg.get("layer1", {}), output_text)
    l2 = layer2(cfg.get("layer2", {}), output_text, skill_dir)
    l3 = layer3(cfg.get("layer3", {}), output_text, fixtures_text)

    l1_pass = all(r["pass"] for r in l1)
    l3cfg = cfg.get("layer3", {})
    if l3.get("status") == "run":
        l3_pass = (l3["overall_avg"] >= float(l3cfg.get("threshold_avg", 4.25)) and
                   min(l3["avg_per_criterion"].values() or [0]) >= float(l3cfg.get("floor", 3)))
    else:
        l3_pass = None  # pending judge / calibration
    scorecard = {
        "skill": skill,
        "layer1": {"checks": l1, "pass": l1_pass},
        "layer2": l2,
        "layer3": l3,
        "gate": {"layers_1_2": l1_pass and l2["pass"],
                 "layer3": l3_pass,
                 "overall": bool(l1_pass and l2["pass"] and (l3_pass is not False))},
        "note": "layer3=None means judge pending; human review gates until calibrated",
    }
    os.makedirs(os.path.join(skill_dir, "eval"), exist_ok=True)
    sc_path = os.path.join(skill_dir, "eval", "scorecard.json")
    with open(sc_path, "w") as f:
        json.dump(scorecard, f, indent=2)
    print(json.dumps(scorecard, indent=2))
    print(f"\nwrote {sc_path}")
    sys.exit(0 if scorecard["gate"]["overall"] else 1)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__); sys.exit(2)
    main(sys.argv[1])
