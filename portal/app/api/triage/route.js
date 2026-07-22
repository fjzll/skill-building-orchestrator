import fs from "fs";
import path from "path";
import { NextResponse } from "next/server";

const ROOT = process.env.ORCH_ROOT || path.join(process.cwd(), "..");
const CLASSES = ["transient", "implementation", "contract", "environment"];

function writeAtomic(file, content) {
  const tmp = path.join(path.dirname(file), `.portal-${process.pid}-${Date.now()}.tmp`);
  fs.writeFileSync(tmp, content);
  fs.renameSync(tmp, file);
}

function setFrontmatter(content, key, value) {
  const m = content.match(/^---\n([\s\S]*?)\n---/);
  if (!m) return content;
  let fm = m[1];
  const re = new RegExp(`^${key}:.*$`, "m");
  fm = re.test(fm) ? fm.replace(re, `${key}: ${value}`) : fm + `\n${key}: ${value}`;
  return content.replace(m[0], `---\n${fm}\n---`);
}

// Mirrors runner/archetype.py — calibration pools on the shape of the work, not
// the client it happened at. Workflow names contain hyphens, so the workflow is
// looked up from the proposal rather than guessed from the skill name.
function archetypeOf(skill, client, workflow) {
  let name = skill;
  if (client && name.startsWith(`${client}-`)) name = name.slice(client.length + 1);
  else if (name.includes("-")) name = name.slice(name.indexOf("-") + 1);
  if (name.startsWith("shared-")) return `shared/${name.slice("shared-".length)}`;
  if (workflow && name.startsWith(`${workflow}-`)) {
    return `${workflow}/${name.slice(workflow.length + 1)}`;
  }
  if (name.includes("-")) return name.replace("-", "/");
  return name;
}

function workflowOf(skill) {
  const dir = path.join(ROOT, "proposals");
  if (!fs.existsSync(dir)) return null;
  for (const name of fs.readdirSync(dir).sort()) {
    if (!name.endsWith(".md") || name === "TEMPLATE.md") continue;
    const fm = (fs.readFileSync(path.join(dir, name), "utf8").match(/^---\n([\s\S]*?)\n---/) || [])[1];
    if (!fm) continue;
    const listed = (fm.match(/^skills:\s*(.*)$/m) || [])[1] || "";
    const skills = listed.replace(/^\[|\]$/g, "").split(",").map(s => s.trim());
    if (skills.includes(skill)) return (fm.match(/^workflow:\s*(\S+)/m) || [])[1] || null;
  }
  return null;
}

function clientSlug() {
  try {
    const yaml = fs.readFileSync(path.join(ROOT, "client.yaml"), "utf8");
    return (yaml.match(/^slug:\s*(\S+)/m) || [])[1] || null;
  } catch { return null; }
}

export async function POST(req) {
  const { skill, agreement, actualClass } = await req.json();
  if (!skill || !/^[\w.-]+$/.test(skill)) {
    return NextResponse.json({ error: "bad skill" }, { status: 400 });
  }
  if (!["agree", "disagree"].includes(agreement)) {
    return NextResponse.json({ error: "bad agreement" }, { status: 400 });
  }
  if (actualClass && !CLASSES.includes(actualClass)) {
    return NextResponse.json({ error: "bad class" }, { status: 400 });
  }
  const verdictFile = path.join(ROOT, "skills", skill, "TRIAGE.md");
  if (!fs.existsSync(verdictFile)) {
    return NextResponse.json({ error: "not found" }, { status: 404 });
  }
  const content = fs.readFileSync(verdictFile, "utf8");
  const verdictClass = (content.match(/^class:\s*(\S+)/m) || [])[1] || "unknown";

  // The verdict file records the review; the jsonl is what the ramp counts.
  writeAtomic(verdictFile, setFrontmatter(content, "human", agreement));
  const line = {
    timestamp: new Date().toISOString().slice(0, 19),
    skill,
    archetype: archetypeOf(skill, clientSlug(), workflowOf(skill)),
    class: verdictClass,
    human: agreement,
    actual_class: actualClass || null,
  };
  const ledger = path.join(ROOT, "analysis", "triage-calibration.jsonl");
  fs.mkdirSync(path.dirname(ledger), { recursive: true });
  fs.appendFileSync(ledger, JSON.stringify(line) + "\n");

  return NextResponse.json({ ok: true, recorded: line });
}
