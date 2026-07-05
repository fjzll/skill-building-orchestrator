"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";

export default function ProposalActions({ file, status }) {
  const [comment, setComment] = useState("");
  const [busy, setBusy] = useState(false);
  const router = useRouter();

  async function act(action) {
    setBusy(true);
    await fetch("/api/proposal", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ file, action, comment }),
    });
    setBusy(false);
    setComment("");
    router.refresh();
  }

  const confirmable = ["proposed", "revised"].includes(status);
  return (
    <div style={{ marginTop: 14, paddingTop: 14, borderTop: "1px solid var(--color-border)" }}>
      <textarea
        value={comment}
        onChange={e => setComment(e.target.value)}
        placeholder="Review comment (required for Request changes; anchor it: which skill / gate / test)"
        style={{ width: "100%", minHeight: 64, padding: 10, borderRadius: 8,
                 border: "1px solid var(--color-border)", fontFamily: "inherit", fontSize: 14 }}
      />
      <div style={{ display: "flex", gap: 10, marginTop: 8 }}>
        <button disabled={!confirmable || busy} onClick={() => act("confirm")}
          style={{ padding: "8px 18px", borderRadius: 8, border: "none", cursor: "pointer",
                   background: confirmable ? "var(--color-primary)" : "#ccc", color: "#fff", fontWeight: 600 }}>
          Confirm proposal
        </button>
        <button disabled={busy || !comment.trim()} onClick={() => act("request-changes")}
          style={{ padding: "8px 18px", borderRadius: 8, cursor: "pointer",
                   border: "1px solid var(--color-accent)", background: "#fff",
                   color: "var(--color-accent)", fontWeight: 600 }}>
          Request changes
        </button>
      </div>
    </div>
  );
}
