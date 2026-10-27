// GUI nad celou firmou (P3-1): přihlášení (Keycloak), seznam zakázek (threadů), detail zakázky = AG-UI run (role jako subagenti,
// předání artefaktů jako zprávy s disclosure čl. 50, aktivity, stav), HITL = interrupt → formulář s povinným důvodem → resume, stop.
import { useEffect, useMemo, useRef, useState } from "react";
import { EventType } from "@ag-ui/core";
import { hasToken, klasQuestions, listThreads, login, me, runAgent, setToken, threadState, type KlasQuestion, type ThreadState, type User } from "./api";
import { AuditPage, FinopsPage, FirmaPage, GovernancePage, Nav, RegistrPage } from "./Firma";

type Ev = Record<string, any>;
type Msg = { id: string; role: string; name?: string; text: string; sub?: string };
type Act = { id: string; type: string; content: Record<string, any>; sub?: string; ts?: number };
type Sub = { id: string; name: string; status: "running" | "done" | "error"; result?: any; message?: string };
type Interrupt = { id: string; reason: string; message?: string; metadata?: Record<string, any>; expiresAt?: string };

const pendingCreate: Record<string, { poptavka: string; budget?: number; klasifikace?: Record<string, boolean> }> = {};

// P3-4: dotazník klasifikační brány K1–K6 (autonomie.md) – checkboxy, výchozí „ne“; profil počítá platforma (deterministicky), ne GUI ani model
function KlasForm({ qs, val, onChange, prefix }: { qs: KlasQuestion[]; val: Record<string, boolean>; onChange: (v: Record<string, boolean>) => void; prefix: string }) {
  return (
    <div data-testid={`${prefix}-form`} style={{ marginTop: 8 }}>
      {qs.map((q) => (
        <label key={q.id} style={{ display: "flex", gap: 8, alignItems: "flex-start", fontWeight: "normal" }}>
          <input type="checkbox" data-testid={`${prefix}-${q.id}`} checked={!!val[q.id]} onChange={(x) => onChange({ ...val, [q.id]: x.target.checked })} style={{ width: "auto", marginTop: 3 }} />
          <span><b>{q.id}</b> {q.text} <span className="muted">(ano → {q.yes})</span></span>
        </label>))}
    </div>);
}

function useHash() {
  const [h, setH] = useState(window.location.hash);
  useEffect(() => { const f = () => setH(window.location.hash); window.addEventListener("hashchange", f); return () => window.removeEventListener("hashchange", f); }, []);
  return h;
}

export function App() {
  const [user, setUser] = useState<User | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const hash = useHash();
  useEffect(() => { if (hasToken()) me().then(setUser).catch(() => setToken(null)); }, []);
  if (!user) return <Login onLogin={(u) => { setUser(u); setErr(null); }} />;
  const m = hash.match(/^#\/t\/([^/?]+)/);
  const page = (hash.match(/^#\/([a-z]+)/) ?? [null, ""])[1] ?? "";
  return (
    <>
      <header>
        <h1><a href="#/" style={{ color: "inherit", textDecoration: "none" }}>Platforma · řídicí pult firmy</a></h1>
        <span className="muted">tenant <b data-testid="user-tenant">{user.tenant}</b></span>
        <span className="spacer" />
        <span className="muted" data-testid="user-name">{user.name}</span>
        <button onClick={() => { setToken(null); setUser(null); }} data-testid="logout">Odhlásit</button>
      </header>
      <main>
        {err && <div className="card err">{err}</div>}
        {!m && <Nav page={page} />}
        {m ? <Thread id={decodeURIComponent(m[1])} user={user} /> : page === "firma" ? <FirmaPage user={user} /> : page === "registr" ? <RegistrPage /> : page === "finops" ? <FinopsPage /> : page === "governance" ? <GovernancePage /> : page === "audit" ? <AuditPage /> : <Threads />}
      </main>
    </>
  );
}

function Login({ onLogin }: { onLogin: (u: User) => void }) {
  const [u, setU] = useState(""); const [p, setP] = useState(""); const [e, setE] = useState<string | null>(null); const [busy, setBusy] = useState(false);
  return (
    <main style={{ maxWidth: 380 }}>
      <div className="card">
        <h2 style={{ marginTop: 0 }}>Přihlášení</h2>
        <p className="muted">Účet člověka v Keycloaku platformy (realm role <code>human</code>). Agenti se sem nepřihlašují.</p>
        <form onSubmit={async (ev) => { ev.preventDefault(); setBusy(true); setE(null); try { onLogin(await login(u, p)); } catch (x: any) { setE(String(x.message ?? x)); } finally { setBusy(false); } }}>
          <label>Uživatel</label><input data-testid="login-user" value={u} onChange={(x) => setU(x.target.value)} autoFocus />
          <label>Heslo</label><input data-testid="login-pass" type="password" value={p} onChange={(x) => setP(x.target.value)} />
          <div style={{ marginTop: 12 }}><button className="primary" type="submit" disabled={busy || !u || !p} data-testid="login-submit">Přihlásit</button></div>
          {e && <p className="err" data-testid="login-error">{e}</p>}
        </form>
      </div>
    </main>
  );
}

function Threads() {
  const [list, setList] = useState<ThreadState[] | null>(null); const [e, setE] = useState<string | null>(null);
  const [nid, setNid] = useState(() => `Z-${new Date().toISOString().slice(5, 16).replace(/[-T:]/g, "")}`); const [pop, setPop] = useState(""); const [bud, setBud] = useState("");
  const [qs, setQs] = useState<KlasQuestion[]>([]); const [kl, setKl] = useState<Record<string, boolean>>({});
  const load = () => listThreads().then((r) => { setList(r.threads); setE(null); }).catch((x) => setE(String(x.message ?? x)));
  useEffect(() => { load(); klasQuestions().then(setQs).catch(() => setQs([])); const t = setInterval(load, 5000); return () => clearInterval(t); }, []);
  return (
    <>
      <div className="card">
        <h2 style={{ marginTop: 0 }}>Nová zakázka</h2>
        <p className="muted">První zpráva uživatele = poptávka; Account z ní sepíše Zadání, které schválíte (H1). Thread = zakázka.</p>
        <form onSubmit={(ev) => { ev.preventDefault(); pendingCreate[nid] = { poptavka: pop, budget: bud ? Number(bud) : undefined, klasifikace: Object.fromEntries(qs.map((q) => [q.id, !!kl[q.id]])) }; window.location.hash = `#/t/${encodeURIComponent(nid)}`; }}>
          <div className="row">
            <div style={{ flex: 1 }}><label>ID zakázky</label><input data-testid="new-id" value={nid} onChange={(x) => setNid(x.target.value)} pattern="[A-Za-z0-9][A-Za-z0-9_.\-]{2,39}" /></div>
            <div style={{ width: 160 }}><label>Rozpočet (USD, 30 d)</label><input data-testid="new-budget" value={bud} onChange={(x) => setBud(x.target.value)} placeholder="výchozí" /></div>
          </div>
          <label>Poptávka</label><textarea data-testid="new-poptavka" value={pop} onChange={(x) => setPop(x.target.value)} />
          <label>Klasifikační brána P1a (AI Act) – zaškrtněte, co platí; profil rizika určí platforma</label>
          {qs.length ? <KlasForm qs={qs} val={kl} onChange={setKl} prefix="new-k" /> : <p className="muted">otázky brány nedostupné</p>}
          <div style={{ marginTop: 10 }}><button className="primary" type="submit" disabled={!pop.trim() || !nid || !qs.length} data-testid="new-submit">Založit a sledovat</button></div>
        </form>
      </div>
      <div className="card">
        <h2 style={{ marginTop: 0 }}>Zakázky</h2>
        {e && <p className="err">{e}</p>}
        {list === null ? <p className="muted">načítám…</p> : list.length === 0 ? <p className="muted" data-testid="threads-empty">zatím žádná zakázka tohoto tenanta</p> : (
          <table data-testid="threads-table">
            <thead><tr><th>ID</th><th>Tenant</th><th>Stav</th><th>Bod</th><th>Role</th><th>Rozpočet</th><th>Útrata</th><th>Založeno</th></tr></thead>
            <tbody>{list.map((t) => (
              <tr key={t.id} data-testid={`thread-row-${t.id}`} data-tenant={t.tenant}>
                <td><a href={`#/t/${encodeURIComponent(t.id)}`}>{t.id}</a></td>
                <td><span className="badge" data-testid="thread-tenant">{t.tenant}</span></td>
                <td><span className={`badge ${t.status === "RUNNING" ? (t.bod ? "waiting" : "running") : t.status === "COMPLETED" ? "done" : t.status === "SUSPENDED" ? "error" : ""}`}>{t.stav ?? t.status ?? "?"}</span></td>
                <td>{t.bod ?? ""}</td>
                <td>{Object.entries(t.roles).map(([r, s]) => <span key={r} className={`badge ${s}`} style={{ marginRight: 4 }}>{r}</span>)}</td>
                <td>{t.budget_usd ?? ""}</td><td>{t.spent_usd != null ? t.spent_usd.toFixed(4) : ""}</td>
                <td className="muted">{t.started ? new Date(t.started * 1000).toLocaleString("cs-CZ") : ""}</td>
              </tr>))}</tbody>
          </table>)}
      </div>
    </>
  );
}

function Thread({ id, user }: { id: string; user: User }) {
  const [events, setEvents] = useState<Ev[]>([]);
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [acts, setActs] = useState<Act[]>([]);
  const [subs, setSubs] = useState<Sub[]>([]);
  const [state, setState] = useState<ThreadState | null>(null);
  const [interrupt, setInterrupt] = useState<Interrupt | null>(null);
  const [runStatus, setRunStatus] = useState<string>("idle");
  const [proto, setProto] = useState<string | null>(null);
  const [runId, setRunId] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [reason, setReason] = useState("");
  const [stopReason, setStopReason] = useState("");
  const [stopOpen, setStopOpen] = useState(false);
  const [kl, setKl] = useState<Record<string, boolean>>({});
  const abort = useRef<AbortController | null>(null);

  const reset = () => { setEvents([]); setMsgs([]); setActs([]); setSubs([]); setInterrupt(null); setErr(null); };

  const onEvent = (e: Ev) => {
    setEvents((xs) => [...xs, e]);
    switch (e.type) {
      case EventType.RUN_STARTED: setProto(e.protocolVersion ?? null); setRunId(e.runId); setRunStatus("running"); break;
      case EventType.RUN_FINISHED: {
        const o = e.outcome ?? {};
        if (o.type === "interrupt") { setInterrupt(o.interrupts?.[0] ?? null); setRunStatus("interrupt"); }
        else setRunStatus(o.type === "cancelled" ? "cancelled" : "finished");
        if (e.result) setState(e.result);
        break;
      }
      case EventType.RUN_ERROR: setErr(e.message); setRunStatus("error"); break;
      case EventType.STATE_SNAPSHOT: setState(e.snapshot); break;
      case EventType.TEXT_MESSAGE_START: setMsgs((m) => [...m.filter((x) => x.id !== e.messageId), { id: e.messageId, role: e.role, name: e.name, text: "", sub: e.subagentRunId }]); break;
      case EventType.TEXT_MESSAGE_CONTENT: setMsgs((m) => m.map((x) => (x.id === e.messageId ? { ...x, text: x.text + e.delta } : x))); break;
      case EventType.ACTIVITY_SNAPSHOT: setActs((a) => [...a.filter((x) => x.id !== e.messageId), { id: e.messageId, type: e.activityType, content: e.content, sub: e.subagentRunId, ts: e.timestamp }]); break;
      case EventType.SUBAGENT_STARTED: setSubs((s) => [...s.filter((x) => x.id !== e.subagentRunId), { id: e.subagentRunId, name: e.name, status: "running" }]); break;
      case EventType.SUBAGENT_FINISHED: setSubs((s) => s.map((x) => (x.id === e.subagentRunId ? { ...x, status: "done", result: e.result } : x))); break;
      case EventType.SUBAGENT_ERROR: setSubs((s) => { const i = s.findIndex((x) => x.id === e.subagentRunId); const r = { id: e.subagentRunId, name: s[i]?.name ?? "?", status: "error" as const, message: e.message }; return i >= 0 ? s.map((x, j) => (j === i ? r : x)) : [...s, r]; }); break;
      default: break;
    }
  };

  const retries = useRef(0);
  const start = async (opts: { resume?: any[]; forwardedProps?: Record<string, unknown>; messages?: any[] } = {}, isRetry = false) => {
    abort.current?.abort(); const ac = new AbortController(); abort.current = ac;
    reset(); setRunStatus("connecting");
    try { await runAgent({ threadId: id, onEvent, signal: ac.signal, ...opts }); if (!isRetry) retries.current = 0; }
    catch (x: any) {
      if (ac.signal.aborted) return;
      const msg = String(x.message ?? x); setErr(msg); setRunStatus("error");
      // síťový výpadek streamu (ne 4xx ze serveru): po chvíli znovu sledovat thread – run je jen pohled, nic se neztratí (zdroj pravdy = ledger)
      if (!/^\d{3}/.test(msg) && retries.current < 30) { retries.current += 1; setTimeout(() => { if (abort.current === ac) start({}, true); }, 3000); }
    }
  };

  useEffect(() => {
    const c = pendingCreate[id]; delete pendingCreate[id];
    start(c ? { messages: [{ id: crypto.randomUUID(), role: "user", content: c.poptavka }], forwardedProps: { ...(c.budget ? { budget_usd: c.budget } : {}), ...(c.klasifikace ? { klasifikace: c.klasifikace } : {}) } } : {});
    return () => abort.current?.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  // P3-4: run končí interruptem; než člověk rozhodne, GUI každých 5 s čte stav threadu (SLA překročení, profil) – zdroj je stále ledger
  useEffect(() => {
    if (runStatus !== "interrupt") return;
    const t = setInterval(() => threadState(id).then(setState).catch(() => undefined), 5000);
    return () => clearInterval(t);
  }, [runStatus, id]);

  const decide = (decision: "approve" | "reject") => {
    if (!interrupt) return;
    start({ resume: [{ interruptId: interrupt.id, status: decision === "approve" ? "resolved" : "cancelled", payload: { decision, reason: reason.trim() } }] });
    setReason("");
  };
  const stop = () => { start({ forwardedProps: { action: "stop", reason: stopReason.trim() } }); setStopOpen(false); setStopReason(""); };

  const reasonOk = reason.trim().length >= 10;
  const timeline = useMemo(() => {
    const items: { k: string; ts: number; el: JSX.Element }[] = [];
    for (const m of msgs) {
      const i = m.text.indexOf("\n\n"); const disc = m.text.startsWith("> ") && i > 0 ? m.text.slice(2, i) : null; const body = disc ? m.text.slice(i + 2) : m.text;
      items.push({ k: m.id, ts: Number(m.id.split(":")[1] ?? 0), el: (
        <div className="ev msg" key={m.id} data-testid={`msg-${m.name ?? m.role}`} data-role={m.role}>
          <div><b>{m.name ?? m.role}</b> <span className="muted">({m.role})</span></div>
          {disc && <div className="disc" data-testid="disclosure">{disc}</div>}
          <div>{body}</div>
        </div>) });
    }
    for (const a of acts) items.push({ k: a.id, ts: Number(a.id.split(":")[1] ?? 0), el: (
      <div className={`ev ${a.type}`} key={a.id} data-testid={`act-${a.type}`}>
        <span className="muted">{a.type}</span> {Object.entries(a.content).filter(([, v]) => v != null && typeof v !== "object").map(([k, v]) => <span key={k} style={{ marginRight: 8 }}>{k}=<code>{String(v)}</code></span>)}
      </div>) });
    return items.sort((x, y) => x.ts - y.ts).map((x) => x.el);
  }, [msgs, acts]);

  return (
    <>
      <div className="card">
        <div className="row">
          <h2 style={{ margin: 0 }}>Zakázka <code>{id}</code></h2>
          <span className={`badge ${runStatus === "running" ? "running" : runStatus === "interrupt" ? "waiting" : runStatus === "error" || runStatus === "cancelled" ? "error" : "done"}`} data-testid="run-status">{runStatus}</span>
          <span className="muted">AG-UI <span data-testid="run-protocol">{proto ?? "?"}</span> · run <code data-testid="run-id">{runId?.slice(0, 8) ?? "-"}</code></span>
          <span className="spacer" />
          {state?.status === "RUNNING" && !stopOpen && <button className="danger" onClick={() => setStopOpen(true)} data-testid="stop-button">Stop zakázky</button>}
          {(runStatus === "finished" || runStatus === "error") && <button onClick={() => start()} data-testid="refresh">Obnovit</button>}
        </div>
        {stopOpen && (
          <div className="card interrupt" style={{ marginTop: 10 }}>
            <b>Stop zakázky</b> – pozastaví workflow (čekající schválení zůstává) a ukončí běžící sandboxy rolí. Důvod je povinný (T5/T6).
            <textarea data-testid="stop-reason" value={stopReason} onChange={(x) => setStopReason(x.target.value)} placeholder="důvod (≥ 10 znaků)" />
            <div className="row" style={{ marginTop: 8 }}>
              <button className="danger" disabled={stopReason.trim().length < 10} onClick={stop} data-testid="stop-confirm">Zastavit</button>
              <button onClick={() => setStopOpen(false)}>Zrušit</button>
            </div>
          </div>)}
        {err && <p className="err" data-testid="run-error">{err}</p>}
        {state && (
          <div className="row" style={{ marginTop: 8 }} data-testid="state">
            <span>stav <b data-testid="state-stav">{state.stav ?? state.status ?? "?"}</b></span>
            <span>workflow <code data-testid="state-status">{state.status ?? "?"}</code></span>
            {state.bod && <span>bod <code data-testid="state-bod">{state.bod}</code></span>}
            {state.profile && <span>profil <b data-testid="state-profile" className={`badge ${state.profile === "standard" ? "done" : "error"}`}>{state.profile}</b></span>}
            {!!state.sla_breaches?.length && <span className="err" data-testid="state-sla">SLA překročeno: {state.sla_breaches.join(", ")}</span>}
            <span>rozpočet <code>{state.budget_usd ?? "?"}</code> USD</span>
            <span>útrata <code data-testid="state-spent">{state.spent_usd != null ? state.spent_usd.toFixed(4) : "-"}</code> USD</span>
            <span className="muted">tenant {state.tenant}</span>
          </div>)}
        <div className="roles" style={{ marginTop: 10 }} data-testid="subagents">
          {subs.map((s) => (
            <div className="role" key={s.id} data-testid={`subagent-${s.name}`} data-status={s.status}>
              <div><b>{s.name}</b> <span className={`badge ${s.status}`}>{s.status}</span></div>
              {s.result && <div className="muted">cena {s.result.cost_usd ?? "?"} USD · nástroje {s.result.tool_uses ?? "?"} · {s.result.via ?? ""}</div>}
              {s.message && <div className="err">{s.message}</div>}
            </div>))}
        </div>
      </div>

      {interrupt && interrupt.reason === "klasifikace" && (
        <div className="card interrupt" data-testid="interrupt" data-interrupt-id={interrupt.id} data-kind="klasifikace">
          <h3 style={{ marginTop: 0 }}>Klasifikační brána <span data-testid="interrupt-bod">klasifikace</span> <span className="muted">(P1a, zadani.classify)</span></h3>
          <p>{interrupt.message}</p>
          <KlasForm qs={(interrupt.metadata?.questions ?? []) as KlasQuestion[]} val={kl} onChange={setKl} prefix="klas" />
          <label>Poznámka (volitelná)</label>
          <textarea data-testid="klas-reason" value={reason} onChange={(x) => setReason(x.target.value)} />
          <div className="row" style={{ marginTop: 8 }}>
            <button className="primary" onClick={() => { const qs = (interrupt.metadata?.questions ?? []) as KlasQuestion[]; start({ resume: [{ interruptId: interrupt.id, status: "resolved", payload: { answers: Object.fromEntries(qs.map((q) => [q.id, !!kl[q.id]])), reason: reason.trim() } }] }); setReason(""); setKl({}); }} data-testid="klas-submit">Odeslat klasifikaci</button>
          </div>
        </div>)}
      {interrupt && interrupt.reason === "dialog" && (
        <div className="card interrupt" data-testid="interrupt" data-interrupt-id={interrupt.id} data-kind="dialog">
          <h3 style={{ marginTop: 0 }}>Account se ptá (kolo <span data-testid="dialog-round">{interrupt.metadata?.round}</span>)</h3>
          <pre style={{ whiteSpace: "pre-wrap" }} data-testid="dialog-questions">{interrupt.metadata?.questions}</pre>
          <label>Vaše odpovědi (Account je zapracuje do Zadání; max 3 kola)</label>
          <textarea data-testid="dialog-answer" value={reason} onChange={(x) => setReason(x.target.value)} />
          <div className="row" style={{ marginTop: 8 }}>
            <button className="primary" disabled={reason.trim().length < 3} onClick={() => { start({ resume: [{ interruptId: interrupt.id, status: "resolved", payload: { answer: reason.trim() } }] }); setReason(""); }} data-testid="dialog-submit">Odpovědět</button>
          </div>
        </div>)}
      {interrupt && interrupt.reason !== "dialog" && interrupt.reason !== "klasifikace" && (
        <div className="card interrupt" data-testid="interrupt" data-interrupt-id={interrupt.id} data-kind="approval">
          <h3 style={{ marginTop: 0 }}>Rozhodnutí člověka: <span data-testid="interrupt-bod">{interrupt.metadata?.bod}</span> <span className="muted">({interrupt.metadata?.action})</span></h3>
          <p>{interrupt.message} · artefakt <code>{interrupt.metadata?.artifact}</code> · hash <code data-testid="interrupt-hash">{interrupt.metadata?.artifact_hash}</code> · od role <b>{interrupt.metadata?.from}</b>{interrupt.expiresAt && <span className="muted"> · timeout {new Date(interrupt.expiresAt).toLocaleString("cs-CZ")} (bez rozhodnutí → Pozastaveno)</span>}</p>
          <label>Důvod rozhodnutí (povinný, ≥ 10 znaků – zapisuje se do org.approvals, podepsaný token nese vaše jméno)</label>
          <textarea data-testid="approve-reason" value={reason} onChange={(x) => setReason(x.target.value)} />
          <div className="row" style={{ marginTop: 8 }}>
            <button className="primary" disabled={!reasonOk} onClick={() => decide("approve")} data-testid="approve-submit">Schválit</button>
            <button className="danger" disabled={!reasonOk} onClick={() => decide("reject")} data-testid="reject-submit">Zamítnout</button>
            {!reasonOk && <span className="muted" data-testid="reason-hint">bez důvodu nelze rozhodnout</span>}
          </div>
        </div>)}

      <div className="card">
        <h3 style={{ marginTop: 0 }}>Průběh</h3>
        <div className="timeline" data-testid="timeline">{timeline}</div>
      </div>
      <div className="card">
        <details>
          <summary>Události AG-UI ({events.length})</summary>
          <div className="log" data-testid="event-log">{events.map((e, i) => <div key={i} data-event-type={e.type}>{e.type}{e.outcome ? ` outcome=${e.outcome.type}` : ""}{e.protocolVersion ? ` protocolVersion=${e.protocolVersion}` : ""}{e.name ? ` ${e.name}` : ""}{e.activityType ? ` ${e.activityType}` : ""}</div>)}</div>
        </details>
      </div>
      <p className="muted">Přihlášen {user.name} · tenant {user.tenant}</p>
    </>
  );
}
