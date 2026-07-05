import fs from "fs";
import path from "path";
import "./globals.css";

const ROOT = process.env.ORCH_ROOT || path.join(process.cwd(), "..");
const FALLBACK_TITLE = "Skill Implementation Orchestrator (template — run ./orch init)";

function getPortalTitle() {
  try {
    const raw = fs.readFileSync(path.join(ROOT, "client.yaml"), "utf8");
    const m = raw.match(/^portal_title:\s*(.+)$/m);
    if (m) return m[1].trim().replace(/^["']|["']$/g, "");
  } catch {
    // no client.yaml — bare template clone, use fallback
  }
  return FALLBACK_TITLE;
}

export const metadata = {
  title: getPortalTitle(),
  description: "Transcend AI Partners — skill implementation orchestrator",
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
