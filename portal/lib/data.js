import fs from "fs";
import path from "path";
import yaml from "js-yaml";

// Repo root: portal/ sits inside the orchestrator repo
const ROOT = process.env.ORCH_ROOT || path.join(process.cwd(), "..");

function safeYaml(p) {
  try { return yaml.load(fs.readFileSync(p, "utf8")); } catch { return null; }
}

export function getFacts() {
  return safeYaml(path.join(ROOT, "analysis", "facts.yaml"));
}

export function getWorkflowMap() {
  return safeYaml(path.join(ROOT, "build-plans", "workflow-map.yaml"));
}

export function getLedger() {
  const dir = path.join(ROOT, "ledger");
  if (!fs.existsSync(dir)) return [];
  return fs.readdirSync(dir).filter(f => f.endsWith(".md")).sort().map(f => ({
    name: f,
    content: fs.readFileSync(path.join(dir, f), "utf8"),
  }));
}

export function getProposals() {
  const dir = path.join(ROOT, "proposals");
  if (!fs.existsSync(dir)) return [];
  return fs.readdirSync(dir)
    .filter(f => f.endsWith(".md") && f !== "TEMPLATE.md")
    .sort()
    .map(f => {
      const content = fs.readFileSync(path.join(dir, f), "utf8");
      const m = content.match(/^---\n([\s\S]*?)\n---/);
      const meta = {};
      if (m) for (const line of m[1].split("\n")) {
        const i = line.indexOf(":");
        if (i > 0) meta[line.slice(0, i).trim()] = line.slice(i + 1).split("#")[0].trim();
      }
      return { name: f, meta, content };
    });
}

export function getSkills() {
  const dir = path.join(ROOT, "skills");
  if (!fs.existsSync(dir)) return [];
  return fs.readdirSync(dir).filter(f => fs.statSync(path.join(dir, f)).isDirectory()).sort().map(name => {
    const scorePath = path.join(dir, name, "eval", "scorecard.json");
    let scorecard = null;
    try { scorecard = JSON.parse(fs.readFileSync(scorePath, "utf8")); } catch {}
    return { name, scorecard, hasBrief: fs.existsSync(path.join(dir, name, "BUILD_BRIEF.md")) };
  });
}
