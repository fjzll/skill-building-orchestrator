import Link from "next/link";
import { getFacts, getWorkflowMap, getLedger, getProposals, getSkills, getBlockers, getGrillOrderProgress, getTriageVerdicts, getFleet } from "../lib/data";
import ProposalActions from "./proposal-actions";
import TriageActions from "./triage-actions";

export const dynamic = "force-dynamic";

const TABS = [
  ["overview", "Overview"],
  ["fleet", "Fleet"],
  ["proposals", "Proposals"],
  ["ledger", "Ledger"],
  ["builds", "Build Status"],
  ["scorecards", "Test Scorecards"],
  ["blockers", "Blockers"],
];

const CATEGORY_CHIP = { access: "amber", system: "red", materials: "purple" };
const BLOCKER_STATUS_CHIP = { open: "amber", resolved: "green", superseded: "grey" };

const STATUS_CHIP = {
  proposed: "amber", "changes-requested": "red", revised: "amber",
  confirmed: "purple", building: "amber", tested: "green",
  "build-failed": "red", blocked: "red",
};

function Hero({ sub }) {
  return (
    <div className="hero">
      <div className="eyebrow">Transcend AI Partners</div>
      <h1>Skill Implementation Orchestrator</h1>
      <p>{sub}</p>
    </div>
  );
}

function Overview() {
  const facts = getFacts();
  const map = getWorkflowMap();
  const proposals = getProposals();
  const skills = getSkills().filter(s => !s.name.startsWith("_"));
  const grillOrder = getGrillOrderProgress();
  return (
    <>
      <Hero sub="Build plans in, tested skills out — grill-gated, ledger-backed." />
      <div className="callout">
        <b>Client:</b> {map?.client?.name} ({map?.client?.code}) ·{" "}
        <b>Pipeline:</b> facts → grill sessions → proposals → builds → eval-gated tests
      </div>
      <div className="card">
        <h2>Where things stand</h2>
        <div className="grid">
          <div className="stat"><div className="num">{map?.workflows?.length ?? 0}</div><div className="lbl">Capability workflows</div></div>
          <div className="stat"><div className="num">{facts?.shared_skill_candidates?.length ?? 0}</div><div className="lbl">Shared-skill candidates</div></div>
          <div className="stat"><div className="num">{getLedger().length}</div><div className="lbl">Ledger entries</div></div>
          <div className="stat"><div className="num">{proposals.length}</div><div className="lbl">Proposals</div></div>
          <div className="stat"><div className="num">{skills.length}</div><div className="lbl">Skills</div></div>
        </div>
      </div>
      <div className="card">
        <h2>Grill order</h2>
        <table><thead><tr><th>Session</th><th>Subject</th><th>Type</th><th>State</th></tr></thead><tbody>
          {grillOrder.map(g => (
            <tr key={g.session}><td>{g.session}</td><td>{g.subject}</td>
              <td><span className={"chip " + (g.type === "shared" ? "purple" : "grey")}>{g.type}{g.rank ? ` · rank ${g.rank}` : ""}</span></td>
              <td><span className={"chip " + g.progress.chip}>{g.progress.label}</span></td></tr>
          ))}
        </tbody></table>
      </div>
      <div className="card">
        <h2>Shared-skill candidates</h2>
        <table><thead><tr><th>Candidate</th><th>Why</th><th>Used by</th></tr></thead><tbody>
          {(facts?.shared_skill_candidates ?? []).map(c => (
            <tr key={c.candidate_name}><td><b>{c.candidate_name}</b></td><td>{c.why}</td>
              <td>{Array.isArray(c.used_by) ? c.used_by.join(", ") : String(c.used_by ?? "")}</td></tr>
          ))}
        </tbody></table>
      </div>
      <div className="card">
        <h2>Workflows (facts pass)</h2>
        <table><thead><tr><th>Workflow</th><th>Slices</th><th>Rank</th><th>Human gates</th><th>Access to confirm</th><th>Open items</th></tr></thead><tbody>
          {(facts?.workflows ?? []).map(w => (
            <tr key={w.id}><td><b>{w.name}</b></td><td>{(w.slices ?? []).join(", ")}</td>
              <td>{String(w.decision_lens_rank)}</td>
              <td><span className="chip purple">{w.human_gates?.length ?? 0}</span></td>
              <td><span className="chip amber">{w.access_to_confirm?.length ?? 0}</span></td>
              <td><span className="chip grey">{w.open_items?.length ?? 0}</span></td></tr>
          ))}
        </tbody></table>
      </div>
    </>
  );
}

// Confirming a proposal approves its executable test suite too, so the suite has
// to be visible at the point of decision — not just the prose that describes it.
function EvalSuites({ suites, frozen }) {
  if (suites.length === 0) return null;
  return (
    <div className="callout">
      <b>Executable test suite</b> — Confirm approves these files as well as the prose above.
      {frozen
        ? <span className="chip green" style={{ marginLeft: 8 }}>frozen at {frozen.slice(0, 12)}</span>
        : <span className="chip amber" style={{ marginLeft: 8 }}>freezes on confirm</span>}
      {suites.map(s => (
        <div key={s.skill} style={{ marginTop: 10 }}>
          <b>{s.skill}</b>{" "}
          {s.config
            ? <span className="chip green">eval/eval.yaml</span>
            : <span className="chip red">eval/eval.yaml missing — cannot build</span>}{" "}
          <span className="chip grey">{s.fixtures.length} fixture{s.fixtures.length === 1 ? "" : "s"}</span>
          {s.config && <pre className="md">{s.config}</pre>}
          {s.fixtures.length > 0 && <p className="muted">fixtures: {s.fixtures.join(", ")}</p>}
        </div>
      ))}
    </div>
  );
}

// Read-only in v1: the fleet view is a lens over N client repos, and every
// action still belongs in the client repo that owns the decision.
function Fleet() {
  const clients = getFleet();
  return (
    <>
      <Hero sub="Every client repo at a glance — statuses, blockers, and verdicts awaiting a human." />
      {clients.length === 0 && (
        <div className="card"><h2>No fleet configured</h2>
          <p className="muted">Set <code>ORCH_FLEET_ROOTS</code> to a colon-separated list of client
            repo paths and restart the portal. Unset means this portal serves one client, which is
            the normal case.</p></div>
      )}
      {clients.length > 0 && (
        <div className="card">
          <h2>Clients <span className="chip grey">{clients.length}</span></h2>
          <table><thead><tr>
            <th>Client</th><th>Skills</th><th>Proposals</th><th>Open blockers</th>
            <th>Triage awaiting review</th><th>Template</th>
          </tr></thead><tbody>
            {clients.map(c => (
              <tr key={c.slug}>
                <td><b>{c.displayName}</b></td>
                <td>{c.skills}</td>
                <td>{c.proposals.map(p => (
                  <span key={p.name} className={"chip " + (STATUS_CHIP[p.status] || "grey")}
                    style={{ marginRight: 4 }}>{p.status}</span>
                ))}</td>
                <td>{c.blockers > 0
                  ? <span className="chip amber">{c.blockers}</span>
                  : <span className="chip green">0</span>}</td>
                <td>{c.awaitingTriage > 0
                  ? <span className="chip amber">{c.awaitingTriage}</span>
                  : <span className="chip green">0</span>}</td>
                <td><span className="chip grey">{String(c.templateCommit).slice(0, 12)}</span></td>
              </tr>
            ))}
          </tbody></table>
        </div>
      )}
    </>
  );
}

function Proposals() {
  const proposals = getProposals();
  return (
    <>
      <Hero sub="One proposal per workflow — derived views of the ledger, versioned, review-gated." />
      {proposals.length === 0 && (
        <div className="card"><h2>No proposals yet</h2>
          <p className="muted">Proposals are written by grill sessions. Status flow:
            proposed → changes requested ⇄ revised → confirmed → building → tested.</p></div>
      )}
      {proposals.map(p => (
        <div className="card" key={p.name}>
          <h2>{p.name} <span className={"chip " + (STATUS_CHIP[p.meta.status] || "grey")}>{p.meta.status}</span>{" "}
            <span className="chip grey">v{p.meta.version || "1"}</span></h2>
          <pre className="md">{p.content.replace(/^---[\s\S]*?---\n/, "")}</pre>
          <EvalSuites suites={p.suites} frozen={p.meta.eval_hash} />
          <ProposalActions file={p.name} status={p.meta.status} />
        </div>
      ))}
    </>
  );
}

function Ledger() {
  const entries = getLedger();
  return (
    <>
      <Hero sub="Append-only decision record — each grill session reads it on entry, writes it on exit." />
      {entries.map(e => (
        <div className="card" key={e.name}>
          <h2>{e.name}</h2>
          <pre className="md">{e.content}</pre>
        </div>
      ))}
    </>
  );
}

function Builds() {
  const skills = getSkills();
  return (
    <>
      <Hero sub="One directory per skill — fixtures and test definition live inside the skill." />
      <div className="card">
        <h2>Skills</h2>
        <table><thead><tr><th>Skill</th><th>Build brief</th><th>Eval gate</th></tr></thead><tbody>
          {skills.map(s => (
            <tr key={s.name}><td><b>{s.name}</b></td>
              <td>{s.hasBrief ? <span className="chip green">present</span> : <span className="chip grey">none</span>}</td>
              <td>{s.scorecard
                ? <span className={"chip " + (s.scorecard.gate?.overall ? "green" : "red")}>{s.scorecard.gate?.overall ? "passing" : "failing"}</span>
                : <span className="chip grey">not run</span>}</td></tr>
          ))}
          {skills.length === 0 && <tr><td colSpan={3} className="muted">No skills yet — builds start after a proposal is confirmed.</td></tr>}
        </tbody></table>
      </div>
    </>
  );
}

function Scorecards() {
  const skills = getSkills().filter(s => s.scorecard);
  return (
    <>
      <Hero sub="Three-layer eval results — deterministic checks, fact grounding, judge rubric." />
      {skills.length === 0 && <div className="card"><p className="muted">No scorecards yet.</p></div>}
      {skills.map(s => {
        const sc = s.scorecard;
        return (
          <div className="card" key={s.name}>
            <h2>{s.name}{" "}
              <span className={"chip " + (sc.gate?.overall ? "green" : "red")}>{sc.gate?.overall ? "gate: pass" : "gate: fail"}</span></h2>
            <h3>Layer 1 — deterministic</h3>
            <table><tbody>
              {(sc.layer1?.checks ?? []).map((c, i) => (
                <tr key={i}><td>{c.check}</td><td><span className={"chip " + (c.pass ? "green" : "red")}>{c.pass ? "pass" : "fail"}</span></td></tr>
              ))}
            </tbody></table>
            <h3>Layer 2 — fact grounding</h3>
            <p>{sc.layer2?.numbers_checked} numbers checked ·{" "}
              {sc.layer2?.ungrounded?.length
                ? <span className="chip red">ungrounded: {sc.layer2.ungrounded.join(", ")}</span>
                : <span className="chip green">all grounded</span>}</p>
            <h3>Layer 3 — judge rubric</h3>
            {sc.layer3?.status === "run"
              ? <p>overall {sc.layer3.overall_avg?.toFixed(2)} / 5 over {sc.layer3.runs} runs</p>
              : <p className="muted">pending — {sc.layer3?.note}</p>}
          </div>
        );
      })}
    </>
  );
}

const TRIAGE_CLASS_CHIP = {
  transient: "amber", implementation: "purple", contract: "red", environment: "red",
};

// A verdict is a diagnosis awaiting a human. Agreeing is also the calibration
// signal — which is why the review lives here rather than in a separate view.
function TriageVerdicts() {
  const verdicts = getTriageVerdicts();
  if (verdicts.length === 0) return null;
  const pending = verdicts.filter(v => !v.meta.human);
  return (
    <div className="card">
      <h2>Triage verdicts <span className="chip grey">{pending.length} awaiting review</span></h2>
      <p className="muted">
        Each verdict is the conductor&apos;s diagnosis of a failure, not an action taken. Agreeing or
        disagreeing writes the calibration line that decides whether this failure class earns autonomy.
        <b> contract</b> and <b>environment</b> never automate.
      </p>
      {verdicts.map(v => (
        <div key={v.skill} style={{ marginTop: 14, paddingTop: 14, borderTop: "1px solid var(--color-border)" }}>
          <h3>{v.skill}{" "}
            <span className={"chip " + (TRIAGE_CLASS_CHIP[v.meta.class] || "grey")}>{v.meta.class}</span>{" "}
            <span className="chip grey">{v.meta.action}</span>{" "}
            <span className="chip grey">confidence: {v.meta.confidence}</span>{" "}
            <span className={"chip " + (v.meta.autonomy === "applied" ? "purple" : "amber")}>
              {v.meta.autonomy === "applied" ? "auto-applied" : "proposed"}</span>
          </h3>
          <pre className="md">{v.body}</pre>
          <TriageActions skill={v.skill} verdictClass={v.meta.class} human={v.meta.human} />
        </div>
      ))}
    </div>
  );
}

function Blockers() {
  const items = getBlockers();
  const open = items.filter(i => i.status === "open");
  const closed = items.filter(i => i.status !== "open");
  const byCategory = ["access", "system", "materials"].map(cat => [cat, open.filter(i => i.category === cat)]);
  const other = open.filter(i => !["access", "system", "materials"].includes(i.category));
  return (
    <>
      <Hero sub="One feed across all workflows — derived from proposal Blockers and Assumptions tables, build failures and stale flags." />
      <div className="callout">
        <b>{open.length}</b> open · <b>{closed.length}</b> resolved/superseded ·
        Sources: proposals/*.md (nothing lives only here — resolve items by amending the proposal + ledger)
      </div>
      <TriageVerdicts />
      {items.length === 0 && (
        <div className="card"><h2>No blockers recorded</h2>
          <p className="muted">Blockers and assumptions are written into proposals at grill time; build failures and stale flags come from the conductor.</p></div>
      )}
      {byCategory.map(([cat, list]) => list.length > 0 && (
        <div className="card" key={cat}>
          <h2><span className={"chip " + CATEGORY_CHIP[cat]}>{cat.toUpperCase()}</span> {list.length} open</h2>
          <table><thead><tr><th>Item</th><th>Workflow</th><th>Kind</th><th>Detail</th><th>Status</th></tr></thead><tbody>
            {list.map((b, i) => (
              <tr key={i}><td><b>{b.item}</b></td><td>{b.workflow}</td>
                <td><span className="chip grey">{b.kind}</span></td>
                <td>{b.detail}</td>
                <td><span className={"chip " + (BLOCKER_STATUS_CHIP[b.status] || "grey")}>{b.status}</span></td></tr>
            ))}
          </tbody></table>
        </div>
      ))}
      {other.length > 0 && (
        <div className="card">
          <h2><span className="chip grey">OTHER</span> {other.length} open</h2>
          <table><tbody>{other.map((b, i) => <tr key={i}><td><b>{b.item}</b></td><td>{b.workflow}</td><td>{b.detail}</td></tr>)}</tbody></table>
        </div>
      )}
      {closed.length > 0 && (
        <div className="card">
          <h2>Resolved / superseded</h2>
          <table><tbody>
            {closed.map((b, i) => (
              <tr key={i}><td className="muted">{b.item}</td><td>{b.workflow}</td>
                <td><span className={"chip " + (BLOCKER_STATUS_CHIP[b.status] || "grey")}>{b.status}</span></td></tr>
            ))}
          </tbody></table>
        </div>
      )}
    </>
  );
}

export default async function Page({ searchParams }) {
  const sp = await searchParams;
  const tab = sp?.tab || "overview";
  return (
    <div className="shell">
      <div className="tabbar">
        {TABS.map(([id, label]) => (
          <Link key={id} href={id === "overview" ? "/" : `/?tab=${id}`}
            className={"tab" + (tab === id ? " active" : "")}>{label}</Link>
        ))}
      </div>
      {tab === "fleet" ? <Fleet />
        : tab === "proposals" ? <Proposals />
        : tab === "ledger" ? <Ledger />
        : tab === "builds" ? <Builds />
        : tab === "scorecards" ? <Scorecards />
        : tab === "blockers" ? <Blockers />
        : <Overview />}
    </div>
  );
}
