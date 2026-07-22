import fs from "fs";
import path from "path";
import yaml from "js-yaml";

// Repo root: portal/ sits inside the orchestrator repo.
// The fleet view reads other client repos through the same parsers, so the root
// is a function with a temporary override rather than a constant. Safe because
// every override window (readAt) is fully synchronous — there is no await inside
// it for another request to interleave on.
const DEFAULT_ROOT = process.env.ORCH_ROOT || path.join(process.cwd(), "..");
const ROOT_OVERRIDE = { value: null };
function root() { return ROOT_OVERRIDE.value || DEFAULT_ROOT; }

function safeYaml(p) {
  try { return yaml.load(fs.readFileSync(p, "utf8")); } catch { return null; }
}

export function getFacts() {
  return safeYaml(path.join(root(), "analysis", "facts.yaml"));
}

export function getWorkflowMap() {
  return safeYaml(path.join(root(), "build-plans", "workflow-map.yaml"));
}

export function getLedger() {
  const dir = path.join(root(), "ledger");
  if (!fs.existsSync(dir)) return [];
  return fs.readdirSync(dir).filter(f => f.endsWith(".md")).sort().map(f => ({
    name: f,
    content: fs.readFileSync(path.join(dir, f), "utf8"),
  }));
}

export function skillsOf(meta) {
  const raw = meta?.skills ?? "";
  return String(raw).replace(/^\[|\]$/g, "").split(",").map(s => s.trim()).filter(Boolean);
}

// The executable half of the contract. Rendered inline on the proposal so that
// one Confirm approves the prose test definition AND the suite that enforces it.
export function getEvalSuite(skill) {
  const dir = path.join(root(), "skills", skill);
  const configPath = path.join(dir, "eval", "eval.yaml");
  const fixturesDir = path.join(dir, "fixtures");
  let fixtures = [];
  if (fs.existsSync(fixturesDir)) {
    fixtures = fs.readdirSync(fixturesDir, { withFileTypes: true })
      .filter(e => e.isFile())
      .map(e => e.name)
      .sort();
  }
  return {
    skill,
    config: fs.existsSync(configPath) ? fs.readFileSync(configPath, "utf8") : null,
    fixtures,
  };
}

export function getProposals() {
  const dir = path.join(root(), "proposals");
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
      return { name: f, meta, content, suites: skillsOf(meta).map(getEvalSuite) };
    });
}

// ---------- Grill-order progress (derived from the system of record) ----------

const PROPOSAL_PROGRESS = {
  proposed: { label: "Proposal review", chip: "amber", priority: 1 },
  "changes-requested": { label: "Changes requested", chip: "red", priority: 1 },
  revised: { label: "Proposal review", chip: "amber", priority: 2 },
  confirmed: { label: "Build queued", chip: "purple", priority: 3 },
  building: { label: "Building", chip: "amber", priority: 4 },
  blocked: { label: "Blocked", chip: "red", priority: 5 },
  tested: { label: "Complete", chip: "green", priority: 5 },
  "build-failed": { label: "Build failed", chip: "red", priority: 5 },
};

function normaliseIdentifier(value) {
  return String(value || "").trim().toLowerCase().replace(/[_\s]+/g, "-");
}

function ledgerMeta(content) {
  const frontmatter = content.match(/^---\n([\s\S]*?)\n---/);
  // Older ledger entries can place their metadata before the first heading.
  const header = frontmatter ? frontmatter[1] : content.split(/^##\s+/m, 1)[0];
  const meta = {};
  for (const line of header.split("\n")) {
    const i = line.indexOf(":");
    if (i > 0) meta[line.slice(0, i).trim().toLowerCase()] = line.slice(i + 1).trim();
  }
  return meta;
}

function sessionProgress(entry) {
  const status = normaliseIdentifier(entry?.status);
  if (status === "approved") return { label: "Decision approved", chip: "green" };
  if (status === "draft") return { label: "Decision pending", chip: "amber" };
  return status
    ? { label: `Decision ${status.replace(/-/g, " ")}`, chip: "purple" }
    : { label: "Decision recorded", chip: "purple" };
}

// The grill order itself is facts-only. Its progress is derived on each request
// from the approved ledger entry for that session and its workflow proposal.
export function getGrillOrderProgress() {
  const order = getFacts()?.grill_order ?? [];
  const ledgerBySession = new Map();
  for (const entry of getLedger()) {
    const meta = ledgerMeta(entry.content);
    if (meta.session) ledgerBySession.set(String(meta.session), meta);
  }

  const proposals = getProposals();
  return order.map(item => {
    const subject = normaliseIdentifier(item.subject);
    const matchingProposals = proposals.filter(proposal => {
      const workflow = normaliseIdentifier(proposal.meta.workflow);
      if (item.type === "shared") {
        return ["shared", "shared-skills", "shared-skill-candidates"].includes(workflow);
      }
      return workflow === subject;
    });
    const proposalProgress = matchingProposals
      .map(proposal => PROPOSAL_PROGRESS[normaliseIdentifier(proposal.meta.status)])
      .filter(Boolean)
      .sort((a, b) => b.priority - a.priority)[0];

    return {
      ...item,
      progress: proposalProgress || (ledgerBySession.has(String(item.session))
        ? sessionProgress(ledgerBySession.get(String(item.session)))
        : { label: "Not started", chip: "grey" }),
    };
  });
}

// ---------- Blockers feed (derived view — no new state) ----------

function mdSection(content, heading) {
  const lines = content.split("\n");
  const start = lines.findIndex(l => new RegExp(`^##\\s+${heading}\\b`, "i").test(l));
  if (start === -1) return "";
  let end = lines.length;
  for (let i = start + 1; i < lines.length; i++) {
    if (/^##\s+/.test(lines[i])) { end = i; break; }
  }
  return lines.slice(start + 1, end).join("\n");
}

function mdTable(sectionText) {
  const rows = sectionText.split("\n").map(l => l.trim()).filter(l => l.startsWith("|"));
  if (rows.length < 3) return []; // header + separator + at least one row
  const headers = rows[0].split("|").slice(1, -1).map(h => h.trim().toLowerCase());
  return rows.slice(2).map(r => {
    const cells = r.split("|").slice(1, -1).map(c => c.trim());
    const obj = {};
    headers.forEach((h, i) => { obj[h] = cells[i] ?? ""; });
    return obj;
  }).filter(o => Object.values(o).some(v => v && !/^-+$/.test(v)));
}

const pick = (row, prefix) => {
  const key = Object.keys(row).find(k => k.startsWith(prefix));
  return key ? row[key] : "";
};

// Aggregates, across every proposal: Blockers table rows, open Assumptions
// (awaiting their Information Request), build-failed proposals, and stale
// flags. Purely derived from files — the artifacts stay the system of record.
export function getBlockers() {
  const items = [];
  for (const p of getProposals()) {
    const workflow = p.meta.workflow || p.name.replace(/\.md$/, "");
    for (const r of mdTable(mdSection(p.content, "Blockers"))) {
      items.push({
        kind: "blocker", source: p.name, workflow,
        item: pick(r, "open item") || pick(r, "item"),
        category: (pick(r, "category") || "materials").toLowerCase(),
        status: (pick(r, "status") || "open").toLowerCase(),
        detail: pick(r, "blocks build"),
      });
    }
    for (const r of mdTable(mdSection(p.content, "Assumptions"))) {
      items.push({
        kind: "assumption", source: p.name, workflow,
        item: pick(r, "assumption"),
        category: "materials", status: "open",
        detail: pick(r, "confirming") ? `IR: ${pick(r, "confirming")}` : "no IR tagged",
      });
    }
    if (p.meta.status === "build-failed") {
      items.push({
        kind: "build", source: p.name, workflow,
        item: "Build failed — see scorecards and analysis/conductor.log",
        category: "system", status: "open", detail: "conductor halted this proposal",
      });
    }
    if (p.meta.status === "blocked") {
      items.push({
        kind: "build", source: p.name, workflow,
        item: "Blocked — a skill is missing its confirmed eval/eval.yaml",
        category: "system", status: "open", detail: "conductor cannot test this proposal",
      });
    }
    if (p.meta.status === "changes-requested") {
      items.push({
        kind: "contract", source: p.name, workflow,
        item: "Change request raised — the contract, not the build, needs a decision",
        category: "system", status: "open", detail: "see skills/<skill>/CHANGE_REQUEST.md",
      });
    }
    if ((p.meta.status || "").startsWith("stale") || p.meta.stale) {
      items.push({
        kind: "stale", source: p.name, workflow,
        item: "Shared dependency changed — proposal needs re-confirmation",
        category: "system", status: "open", detail: "confirmation reset",
      });
    }
  }
  return items;
}

// ---------- Triage verdicts (the LLM's diagnosis, awaiting a human verdict) ----------

export function getTriageVerdicts() {
  const dir = path.join(root(), "skills");
  if (!fs.existsSync(dir)) return [];
  const out = [];
  for (const skill of fs.readdirSync(dir).sort()) {
    const file = path.join(dir, skill, "TRIAGE.md");
    if (!fs.existsSync(file)) continue;
    const content = fs.readFileSync(file, "utf8");
    const m = content.match(/^---\n([\s\S]*?)\n---/);
    const meta = {};
    if (m) for (const line of m[1].split("\n")) {
      const i = line.indexOf(":");
      if (i > 0) meta[line.slice(0, i).trim()] = line.slice(i + 1).split("#")[0].trim();
    }
    out.push({ skill, meta, body: content.replace(/^---[\s\S]*?---\n/, "") });
  }
  return out;
}

// ---------- Fleet view (read-only across N client repos) ----------

// ORCH_FLEET_ROOTS is a colon-separated list of client repo paths. Unset means
// this portal is running for a single client, which is the normal case.
export function fleetRoots() {
  return (process.env.ORCH_FLEET_ROOTS || "").split(":").map(s => s.trim()).filter(Boolean);
}

function readAt(root, fn) {
  const previous = ROOT_OVERRIDE.value;
  ROOT_OVERRIDE.value = root;
  try { return fn(); } finally { ROOT_OVERRIDE.value = previous; }
}

export function getFleet() {
  return fleetRoots().map(root => readAt(root, () => {
    const config = safeYaml(path.join(root, "client.yaml")) || {};
    const proposals = getProposals();
    const verdicts = getTriageVerdicts();
    return {
      root,
      slug: config.slug || path.basename(root),
      displayName: config.display_name || path.basename(root),
      templateCommit: config.template_commit || "unknown",
      proposals: proposals.map(p => ({ name: p.name, status: p.meta.status || "draft" })),
      blockers: getBlockers().filter(b => b.status === "open").length,
      awaitingTriage: verdicts.filter(v => !v.meta.human).length,
      skills: getSkills().filter(s => !s.name.startsWith("_")).length,
    };
  }));
}

export function getSkills() {
  const dir = path.join(root(), "skills");
  if (!fs.existsSync(dir)) return [];
  return fs.readdirSync(dir).filter(f => fs.statSync(path.join(dir, f)).isDirectory()).sort().map(name => {
    const scorePath = path.join(dir, name, "eval", "scorecard.json");
    let scorecard = null;
    try { scorecard = JSON.parse(fs.readFileSync(scorePath, "utf8")); } catch {}
    return { name, scorecard, hasBrief: fs.existsSync(path.join(dir, name, "BUILD_BRIEF.md")) };
  });
}
