"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";

// Agreeing with a verdict is the calibration signal: it writes the human line
// into analysis/triage-calibration.jsonl, and enough consecutive agreements on a
// class is what earns the conductor autonomy for that class.
export default function TriageActions({ skill, verdictClass, human }) {
  const [busy, setBusy] = useState(false);
  const [actual, setActual] = useState("");
  const router = useRouter();

  async function record(agreement) {
    setBusy(true);
    await fetch("/api/triage", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ skill, agreement, actualClass: agreement === "disagree" ? actual : null }),
    });
    setBusy(false);
    setActual("");
    router.refresh();
  }

  if (human) {
    return <p className="muted">Human verdict recorded: <b>{human}</b></p>;
  }
  return (
    <div style={{ display: "flex", gap: 10, alignItems: "center", marginTop: 10, flexWrap: "wrap" }}>
      <button disabled={busy} onClick={() => record("agree")}
        style={{ padding: "6px 16px", borderRadius: 8, border: "none", cursor: "pointer",
                 background: "var(--color-primary)", color: "#fff", fontWeight: 600 }}>
        Agree — {verdictClass}
      </button>
      <select value={actual} onChange={e => setActual(e.target.value)}
        style={{ padding: "6px 10px", borderRadius: 8, border: "1px solid var(--color-border)" }}>
        <option value="">it was actually…</option>
        <option value="transient">transient</option>
        <option value="implementation">implementation</option>
        <option value="contract">contract</option>
        <option value="environment">environment</option>
      </select>
      <button disabled={busy || !actual} onClick={() => record("disagree")}
        style={{ padding: "6px 16px", borderRadius: 8, cursor: "pointer",
                 border: "1px solid var(--color-accent)", background: "#fff",
                 color: "var(--color-accent)", fontWeight: 600 }}>
        Disagree
      </button>
    </div>
  );
}
