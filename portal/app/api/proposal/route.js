import fs from "fs";
import path from "path";
import { NextResponse } from "next/server";

const ROOT = process.env.ORCH_ROOT || path.join(process.cwd(), "..");

// Mirrors runner/fm.py write_atomic: a conductor tick reading mid-write must
// see either the old file or the new one, never a truncated one.
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

export async function POST(req) {
  const { file, action, comment } = await req.json();
  // safety: only .md files inside proposals/, never TEMPLATE
  if (!file || !/^[\w.-]+\.md$/.test(file) || file === "TEMPLATE.md") {
    return NextResponse.json({ error: "bad file" }, { status: 400 });
  }
  const p = path.join(ROOT, "proposals", file);
  if (!fs.existsSync(p)) return NextResponse.json({ error: "not found" }, { status: 404 });
  let content = fs.readFileSync(p, "utf8");

  if (action === "confirm") {
    content = setFrontmatter(content, "status", "confirmed");
    writeAtomic(p, content);
    return NextResponse.json({ ok: true, status: "confirmed" });
  }
  if (action === "request-changes") {
    content = setFrontmatter(content, "status", "changes-requested");
    writeAtomic(p, content);
    // anchored review file the orchestrator picks up (structural vs cosmetic triage happens there)
    const reviewDir = path.join(ROOT, "proposals", "reviews");
    fs.mkdirSync(reviewDir, { recursive: true });
    const ts = new Date().toISOString().replace(/[:.]/g, "-");
    fs.writeFileSync(
      path.join(reviewDir, `${file.replace(/\.md$/, "")}-${ts}.md`),
      `---\nproposal: ${file}\ndate: ${new Date().toISOString()}\nstatus: open\n---\n\n${comment || "(no comment)"}\n`
    );
    return NextResponse.json({ ok: true, status: "changes-requested" });
  }
  return NextResponse.json({ error: "bad action" }, { status: 400 });
}
