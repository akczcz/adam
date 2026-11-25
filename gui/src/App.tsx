// GUI nad celou firmou (P3-1, redesign 2026-11-24 – varianta A „Nebula“): přihlášení (Keycloak), seznam zakázek (threadů), karta zakázky = AG-UI run
// (role jako subagenti, předání artefaktů jako zprávy s disclosure čl. 50, aktivity, stav), HITL = interrupt → formulář s povinným důvodem → resume, stop.
// Stav karty drží reducer (threadView.ts) – nový run pohled nemaže, interrupt je odvozený z aktivit, chyby streamu jsou toast.
import { useEffect, useMemo, useState, type ReactNode } from "react";
import { activity, hasToken, idleLimitMs, klasQuestions, listThreads, login, me, needsKeepalive, renewMandat, setToken, isActive, type KlasQuestion, type ThreadState, type User } from "./api";
import { AuditPage, FinopsPage, FirmaPage, GovernancePage, Nav, RegistrPage } from "./Firma";
import { selActivities, selDecisions, selMessages, selReviewTasks, selSubagents, selTimeline, type Act, type Interrupt, type Msg, type ThreadView } from "./threadView";
import { useThreadRun, type StartOpts } from "./useThreadRun";
import { Badge, Button, Card, CardHeader, Checkbox, DataTable, Field, Orb, PageError, Progress, RoleChip, Skeleton, Sync, ThemeToggle, Tile, ToastHost, fmtDate, fmtTime, fmtUsd, statusTone, stavLabel, useToast, type Col } from "./ui";

const pendingCreate: Record<string, { poptavka: string; budget?: number; klasifikace?: Record<string, boolean>; live?: boolean }> = {};   // P4-2: live = ostrý běh
const MIN_REASON = 10;

// P3-4: dotazník klasifikační brány K1–K6 (autonomie.md) – checkboxy, výchozí „ne“; profil počítá platforma (deterministicky), ne GUI ani model
function KlasForm({ qs, val, onChange, prefix }: { qs: KlasQuestion[]; val: Record<string, boolean>; onChange: (v: Record<string, boolean>) => void; prefix: string }) {
  return (
    <div className="stack" data-testid={`${prefix}-form`}>
      {qs.map((q) => <Checkbox key={q.id} testid={`${prefix}-${q.id}`} checked={!!val[q.id]} onChange={(x) => onChange({ ...val, [q.id]: x.target.checked })} label={<><b>{q.id}</b>{q.text} <span className="muted">(ano → {q.yes})</span></>} />)}
    </div>);
}

function useHash() {
  const [h, setH] = useState(window.location.hash);
  useEffect(() => { const f = () => setH(window.location.hash); window.addEventListener("hashchange", f); return () => window.removeEventListener("hashchange", f); }, []);
  return h;
}

export function App() { return <ToastHost><Shell /></ToastHost>; }

function Shell() {
  const [user, setUser] = useState<User | null>(null);
  const hash = useHash();
  const [idleMsg, setIdleMsg] = useState<string | null>(null);
  useEffect(() => { if (hasToken()) me().then(setUser).catch(() => setToken(null)); }, []);
  useEffect(() => {   // P4-5: idle timeout – bez aktivity člověka (myš, klávesy, dotyk) se GUI odhlásí (výchozí 30 min; veřejný vstup přes tunel)
    const bump = () => { activity.last = Date.now(); };
    for (const ev of ["mousemove", "mousedown", "keydown", "touchstart", "scroll"]) window.addEventListener(ev, bump, { passive: true });
    const t = setInterval(() => { if (hasToken() && Date.now() - activity.last > idleLimitMs()) { setToken(null, null); setUser(null); setIdleMsg(`Odhlášeno po nečinnosti (${Math.round(idleLimitMs() / 60000) || "<1"} min).`); } }, 5000);
    return () => { clearInterval(t); for (const ev of ["mousemove", "mousedown", "keydown", "touchstart", "scroll"]) window.removeEventListener(ev, bump); };
  }, []);
  if (!user) return <div className="app"><Login notice={idleMsg} onLogin={(u) => { setUser(u); setIdleMsg(null); activity.last = Date.now(); }} /></div>;
  const m = hash.match(/^#\/t\/([^/?]+)/);
  const page = m ? "" : ((hash.match(/^#\/([a-z]+)/) ?? [null, ""])[1] ?? "");
  return (
    <div className="app">
      <header className="hdr">
        <a href="#/" className="brand"><Orb /><span>Platforma<small>řídicí pult firmy</small></span></a>
        <span className="tenant">tenant <b data-testid="user-tenant">{user.tenant}</b></span>
        <Nav page={page} />
        <span className="sp" />
        <div className="who"><ThemeToggle /><span className="name"><b data-testid="user-name">{user.name}</b></span><Button variant="g" size="sm" testid="logout" onClick={() => { setToken(null); setUser(null); }}>Odhlásit</Button></div>
      </header>
      <main>
        {m ? <Thread key={decodeURIComponent(m[1])} id={decodeURIComponent(m[1])} user={user} /> : page === "firma" ? <FirmaPage user={user} /> : page === "registr" ? <RegistrPage /> : page === "finops" ? <FinopsPage /> : page === "governance" ? <GovernancePage /> : page === "audit" ? <AuditPage /> : <Threads user={user} />}
      </main>
    </div>
  );
}

function Login({ onLogin, notice }: { onLogin: (u: User) => void; notice?: string | null }) {
  const [u, setU] = useState(""); const [p, setP] = useState(""); const [e, setE] = useState<string | null>(null); const [busy, setBusy] = useState(false);
  return (
    <main className="narrow">
      <Card className="stack login">
        <div className="brand"><Orb lg /><span>Platforma<small>řídicí pult firmy</small></span></div>
        {notice && <p className="alert" data-testid="idle-notice">{notice}</p>}
        <form className="stack" onSubmit={async (ev) => { ev.preventDefault(); setBusy(true); setE(null); try { onLogin(await login(u, p)); } catch (x: any) { setE(String(x.message ?? x)); } finally { setBusy(false); } }}>
          <Field label="Uživatel"><input data-testid="login-user" className="mono" value={u} onChange={(x) => setU(x.target.value)} autoFocus autoComplete="username" /></Field>
          <Field label="Heslo"><input data-testid="login-pass" type="password" value={p} onChange={(x) => setP(x.target.value)} autoComplete="current-password" /></Field>
          <Button variant="p" wide type="submit" disabled={busy || !u || !p} testid="login-submit">Přihlásit</Button>
          {e && <PageError testid="login-error">{e}</PageError>}
        </form>
        <p className="muted small">Účet člověka v Keycloaku platformy (realm role <code>human</code>). Agenti se sem nepřihlašují.</p>
        <p className="foot">vstup chráněn Cloudflare Access · přihlášení Keycloak</p>
      </Card>
    </main>
  );
}

// P4-1: keepalive mandátu – živý mandát přihlášeného držitele s < 10 min do konce se prodlouží jeho aktuálním tokenem (auto); vypršelý ne (to je rozhodnutí člověka)
async function keepalive(ts: ThreadState[], user: User) {
  if (!isActive()) return;   // P4-5: zapomenutá záložka bez aktivity (10 min) mandát neprodlužuje
  for (const t of ts) if (needsKeepalive(t, user)) { try { await renewMandat(t.id, true); } catch { /* příští kolo */ } }
}

function MandatBadge({ m, testid, extra }: { m: ThreadState["mandat"]; testid: string; extra?: Record<string, string> }) {
  const expired = !m || m.expired;
  return <Badge tone={expired ? "err" : "done"} dot testid={testid} data-expired={String(expired)} {...extra}>{!m ? "bez mandátu" : m.expired ? `vypršel (${m.name ?? m.sub})` : `${m.name ?? m.sub} · ${Math.max(0, Math.round((m.expires_in_s ?? 0) / 60))} min`}</Badge>;
}

function Threads({ user }: { user: User }) {
  const [list, setList] = useState<ThreadState[] | null>(null); const [e, setE] = useState<string | null>(null); const [at, setAt] = useState<number>(0);
  const [nid, setNid] = useState(() => `Z-${new Date().toISOString().slice(5, 16).replace(/[-T:]/g, "")}`); const [pop, setPop] = useState(""); const [bud, setBud] = useState("");
  const [qs, setQs] = useState<KlasQuestion[]>([]); const [kl, setKl] = useState<Record<string, boolean>>({}); const [live, setLive] = useState(false);
  const load = () => listThreads().then((r) => { setList(r.threads); setE(null); setAt(Date.now()); return r.threads; }).catch((x) => { setE(String(x.message ?? x)); return [] as ThreadState[]; });
  useEffect(() => { load(); klasQuestions().then(setQs).catch(() => setQs([])); const t = setInterval(load, 5000); const k = setInterval(() => load().then((ts) => keepalive(ts, user)), 30000); return () => { clearInterval(t); clearInterval(k); }; }, []);   // eslint-disable-line react-hooks/exhaustive-deps
  const waiting = list?.filter((t) => t.status === "RUNNING" && t.bod).length ?? 0; const running = list?.filter((t) => t.status === "RUNNING" && !t.bod).length ?? 0;
  const cols: Col<ThreadState>[] = [
    { key: "id", label: "ID", wide: true, render: (t) => <><a href={`#/t/${encodeURIComponent(t.id)}`} data-testid="thread-id">{t.id}</a> {t.live && <Badge tone="live" dot testid="thread-live" title="ostrý běh: živý model, skutečný GitHub">ostrý</Badge>}</> },
    { key: "tenant", label: "Tenant", render: (t) => <Badge testid="thread-tenant">{t.tenant}</Badge> },
    { key: "stav", label: "Stav", render: (t) => <Badge tone={statusTone(t.status, t.bod, t.stav)} dot testid="thread-stav" data-status={t.status ?? ""}>{stavLabel(t.stav, t.status)}</Badge> },
    { key: "bod", label: "Bod", render: (t) => t.bod ? <code data-testid="thread-bod">{t.bod}</code> : <span className="muted" data-testid="thread-bod">–</span> },
    { key: "roles", label: "Role", render: (t) => <span className="chips" data-testid="thread-roles" title={Object.entries(t.roles).map(([r, s]) => `${r}: ${s}`).join(", ")}>{Object.entries(t.roles).map(([r, s]) => <i key={r} className={s} />)}</span> },
    { key: "mandat", label: "Mandát", render: (t) => t.status === "RUNNING" ? <MandatBadge m={t.mandat} testid="thread-mandat" /> : <span className="muted">–</span> },
    { key: "spent", label: "Útrata / strop", labelText: "Útrata / strop", right: true, render: (t) => <span data-testid="thread-spent" data-budget={t.budget_usd ?? ""}>{fmtUsd(t.spent_usd)} / {t.budget_usd ?? "?"} USD</span> },
    { key: "started", label: "Založeno", className: "muted", render: (t) => <span data-testid="thread-started">{fmtDate(t.started)}</span> },
  ];
  return (
    <div className="grid2">
      <Card className="stack">
        <CardHeader><h2>Zakázky</h2>{waiting > 0 && <Badge tone="wait" dot>{waiting} čeká na vás</Badge>}{running > 0 && <Badge tone="run" dot>{running} běží</Badge>}<span className="sp" />{at > 0 && <span className="muted xs">obnoveno {fmtTime(at)}</span>}<Button variant="g" size="sm" testid="refresh" onClick={load}>Obnovit</Button></CardHeader>
        {e && <PageError>{e}</PageError>}
        {list === null ? <Skeleton lines={4} /> : <DataTable id="threads-table" rows={list} cols={cols} rowKey={(t) => t.id} emptyText="" rowProps={(t) => ({ "data-testid": `thread-row-${t.id}`, "data-tenant": t.tenant })} />}
        {list !== null && list.length === 0 && <p className="empty" data-testid="threads-empty">zatím žádná zakázka tohoto tenanta</p>}
      </Card>
      <Card className="stack">
        <CardHeader><h2>Nová zakázka</h2></CardHeader>
        <p className="muted small">První zpráva = poptávka; Account z ní sepíše Zadání, které schválíte (H1). Thread = zakázka.</p>
        <form className="stack" onSubmit={(ev) => { ev.preventDefault(); pendingCreate[nid] = { poptavka: pop, budget: bud ? Number(bud) : undefined, klasifikace: Object.fromEntries(qs.map((q) => [q.id, !!kl[q.id]])), live }; window.location.hash = `#/t/${encodeURIComponent(nid)}`; }}>
          <div className="row stretch">
            <Field label="ID zakázky" className="grow"><input data-testid="new-id" className="mono" value={nid} onChange={(x) => setNid(x.target.value)} pattern="[A-Za-z0-9][A-Za-z0-9_.\-]{2,39}" /></Field>
            <Field label="Rozpočet (USD, 30 d)"><input data-testid="new-budget" className="mono" value={bud} onChange={(x) => setBud(x.target.value)} placeholder="výchozí" inputMode="decimal" /></Field>
          </div>
          <Field label="Poptávka"><textarea data-testid="new-poptavka" value={pop} onChange={(x) => setPop(x.target.value)} placeholder="Co má firma dodat? Account z toho sepíše Zadání." /></Field>
          <label className="switch"><input type="checkbox" data-testid="new-live" checked={live} onChange={(x) => setLive(x.target.checked)} /><span><b>Ostrý běh</b> – role jednají s živým modelem (placené volání přes gateway, strop = rozpočet) a artefakty (issue, PR, merge) jdou do skutečného GitHubu repozitáře platformy. Bez zaškrtnutí běží zakázka proti mockům.</span></label>
          <Field label="Klasifikační brána P1a (AI Act) – zaškrtněte, co platí; profil rizika určí platforma">
            {qs.length ? <KlasForm qs={qs} val={kl} onChange={setKl} prefix="new-k" /> : <p className="muted small">otázky brány nedostupné</p>}
          </Field>
          <div className="row"><Button variant="p" type="submit" disabled={!pop.trim() || !nid || !qs.length} testid="new-submit">Založit a sledovat</Button></div>
        </form>
      </Card>
    </div>
  );
}

// --- karta zakázky ---------------------------------------------------------------------------------------------------------------
const BOD_TITLE: Record<string, string> = { H1a: "Stanovisko právníka", H1: "Schválení zadání", H2: "Schválení návrhu (ADR)", H4: "Review před merge PR", H5: "Potvrzení nasazení", rozpocet: "Rozpočet vyčerpán", publikace: "Publikace selhala", role: "Běh role selhal" };

function Thread({ id, user }: { id: string; user: User }) {
  const initial = useMemo<StartOpts | undefined>(() => { const c = pendingCreate[id]; delete pendingCreate[id]; return c ? { messages: [{ id: crypto.randomUUID(), role: "user", content: c.poptavka }], forwardedProps: { ...(c.budget ? { budget_usd: c.budget } : {}), ...(c.klasifikace ? { klasifikace: c.klasifikace } : {}), ...(c.live ? { live: true } : {}) } } : undefined; }, [id]);
  const { view, interrupt, start, resume, action, renew, applyState } = useThreadRun(id, user, initial);
  const toast = useToast();
  const [reason, setReason] = useState(""); const [budget, setBudget] = useState(""); const [kl, setKl] = useState<Record<string, boolean>>({});
  const [stopReason, setStopReason] = useState(""); const [stopOpen, setStopOpen] = useState(false); const [resumeOpen, setResumeOpen] = useState(false);
  const [mandatMsg, setMandatMsg] = useState<string | null>(null);
  const state = view.state; const run = view.run; const subs = selSubagents(view);
  const reasonOk = reason.trim().length >= MIN_REASON;
  const decide = (decision: "approve" | "reject") => {
    if (!interrupt) return;
    const extra = interrupt.metadata?.bod === "rozpocet" && decision === "approve" && budget.trim() ? { budget_usd: Number(budget) } : {};
    resume(interrupt.id, decision === "approve" ? "resolved" : "cancelled", { decision, reason: reason.trim(), ...extra }); setReason(""); setBudget("");
    toast.push({ tone: "ok", title: decision === "approve" ? `Schváleno: ${interrupt.metadata?.bod}` : `Zamítnuto: ${interrupt.metadata?.bod}`, detail: "rozhodnutí se zapisuje do org.approvals; zakázka pokračuje" });
  };
  const mode = state?.live ? <Badge tone="live" dot testid="state-live" title="živý model přes gateway (placeno), artefakty do skutečného GitHubu">ostrý běh</Badge> : state ? <Badge tone="mock" title="role běží proti mockům (žádný živý model ani GitHub)">mock</Badge> : null;
  const runTone = run.status === "running" || run.status === "connecting" ? "run" : run.status === "interrupt" ? "wait" : run.status === "stalled" ? "stalled" : run.status === "error" || run.status === "cancelled" ? "err" : run.status === "finished" ? "done" : "";
  const mandatExpired = !state?.mandat || state.mandat.expired;
  return (
    <>
      <Card className={`stack ${state?.status === "SUSPENDED" ? "irq susp" : ""}`}>
        <CardHeader>
          <a href="#/" className="crumb">Zakázky /</a><h2 className="mono">{id}</h2>
          {mode}
          <Badge tone={runTone} dot={run.status === "running" || run.status === "connecting"} testid="run-status">{run.status}</Badge>
          <span className="muted small">AG-UI <span data-testid="run-protocol">{run.protocol ?? "?"}</span> · run <code data-testid="run-id">{run.id?.slice(0, 8) ?? "-"}</code></span>
          {run.syncing && <Sync>synchronizuji</Sync>}
          <span className="sp" />
          {state?.status === "RUNNING" && !stopOpen && <Button variant="d" testid="stop-button" onClick={() => setStopOpen(true)}>Stop zakázky</Button>}
          {state?.status === "SUSPENDED" && !resumeOpen && <Button variant="p" testid="resume-button" onClick={() => setResumeOpen(true)}>Obnovit běh</Button>}
          {(run.status === "finished" || run.status === "error" || run.status === "cancelled") && <Button variant="g" testid="refresh" onClick={() => start()}>Obnovit pohled</Button>}
        </CardHeader>
        {state?.status === "SUSPENDED" && <p className="muted small">Zakázka je <b>Pozastaveno</b>{state.bod ? <> na bodu <code>{state.bod}</code></> : null} – workflow stojí, čekající schválení zůstává. Obnovit běh = nový run; bod se otevře znovu tam, kde skončil.</p>}
        {resumeOpen && (
          <div className="card irq susp stack tight">
            <div><b>Obnovit běh zakázky</b> – obnoví pozastavený workflow; zastavená role se spustí znovu od checkpointu, čekající schválení pokračuje tam, kde skončilo. Důvod je povinný (T5/T6).</div>
            <textarea data-testid="resume-reason" value={stopReason} onChange={(x) => setStopReason(x.target.value)} placeholder="důvod (≥ 10 znaků)" />
            <div className="row"><Button variant="p" disabled={stopReason.trim().length < MIN_REASON} testid="resume-confirm" onClick={() => { action("resume", stopReason.trim()); setResumeOpen(false); setStopReason(""); }}>Obnovit běh</Button><Button variant="g" onClick={() => setResumeOpen(false)}>Zrušit</Button></div>
          </div>)}
        {stopOpen && (
          <div className="card irq danger stack tight">
            <div><b>Stop zakázky</b> – pozastaví workflow (čekající schválení zůstává) a ukončí běžící sandboxy rolí. Důvod je povinný (T5/T6).</div>
            <textarea data-testid="stop-reason" value={stopReason} onChange={(x) => setStopReason(x.target.value)} placeholder="důvod (≥ 10 znaků)" />
            <div className="row"><Button variant="d" disabled={stopReason.trim().length < MIN_REASON} testid="stop-confirm" onClick={() => { action("stop", stopReason.trim()); setStopOpen(false); setStopReason(""); }}>Zastavit</Button><Button variant="g" onClick={() => setStopOpen(false)}>Zrušit</Button></div>
          </div>)}
        {run.error && <p className="alert err" data-testid="run-error" role="alert">{run.error}</p>}
        {state ? (
          <div className="tiles" data-testid="state">
            <Tile k="stav" tone={state.status === "RUNNING" && state.bod ? "warn" : ""}><span data-testid="state-stav">{stavLabel(state.stav, state.status)}</span></Tile>
            <Tile k="workflow"><code data-testid="state-status">{state.status ?? "?"}</code></Tile>
            {state.bod && <Tile k="bod"><code data-testid="state-bod">{state.bod}</code></Tile>}
            {state.profile && <Tile k="profil rizika" tone={state.profile === "standard" ? "ok" : "err"}><span data-testid="state-profile">{state.profile}</span></Tile>}
            <Tile k="SLA" tone={state.sla_breaches?.length ? "err" : "muted"}>{state.sla_breaches?.length ? <span data-testid="state-sla">SLA překročeno: {state.sla_breaches.join(", ")}</span> : "v limitu"}</Tile>
            <Tile k="útrata / rozpočet (30 d)" span2 tone={state.spent_usd != null && state.budget_usd != null && state.spent_usd > state.budget_usd ? "err" : ""}>
              <span><code data-testid="state-spent">{state.spent_usd != null ? state.spent_usd.toFixed(4) : "-"}</code> <span className="muted">/</span> <code data-testid="state-budget">{state.budget_usd ?? "?"}</code> <span className="muted">USD</span></span>
              <Progress value={state.spent_usd} max={state.budget_usd} />
            </Tile>
            {state.status === "RUNNING" && <Tile k="mandát" tone={mandatExpired ? "err" : "ok"}><MandatBadge m={state.mandat} testid="state-mandat" extra={{ "data-sub": state.mandat?.sub ?? "", "data-source": state.mandat?.source ?? "", "data-expires-in": String(state.mandat?.expires_in_s ?? "") }} /></Tile>}
            {state.wf_version && <Tile k="orchestrátor"><code data-testid="state-wf-version">{state.wf_version}</code></Tile>}
            <Tile k="tenant" tone="muted">{state.tenant}</Tile>
          </div>) : <Skeleton lines={2} />}
        {state?.status === "RUNNING" && user.tenant !== "platform" && (
          <div className={`card tight stack irq ${mandatExpired ? "danger" : "info"}`} data-testid="mandat-card" data-expired={String(mandatExpired)}>
            {mandatExpired
              ? <div><b>Role bez mandátu</b> – {state.mandat ? <>mandát <b>{state.mandat.name ?? state.mandat.sub}</b> vypršel</> : <>zakázka nemá mandát člověka</>}: další role budou jednat bez doloženého „jménem“ (paměť zapíše <code>on_behalf_of null</code>). Obnova = váš aktuální token se stane mandátem pro další role; nic se nezastavuje.</div>
              : <div className="muted small">Mandát: další role jednají jménem <b>{state.mandat!.name ?? state.mandat!.sub}</b> (zdroj {state.mandat!.source}{state.mandat!.auto ? ", keepalive" : ""}), platí ještě {Math.max(0, Math.round((state.mandat!.expires_in_s ?? 0) / 60))} min; dokud má držitel GUI otevřené, prodlužuje se sám.</div>}
            <div className="row"><Button variant={mandatExpired ? "p" : ""} size="sm" testid="mandat-renew" onClick={() => renew().then(setMandatMsg)}>Obnovit mandát</Button>{mandatMsg && <span className="muted small" data-testid="mandat-msg">{mandatMsg}</span>}</div>
          </div>)}
        {state?.stalled && (
          <div className="card tight irq" data-testid="stalled-notice" data-wf-version={state.stalled.wf_version ?? ""}>
            <b>Zakázka je zaseknutá (STALLED)</b> – {state.stalled.hint} Rozhodnutí ani artefakty se neztrácejí; po nasazení verze zakázka pokračuje sama a tento pohled se obnoví.
          </div>)}
        <div className="stack">
          <span className="eyebrow">Role zakázky</span>
          <div className="roles" data-testid="subagents">
            {subs.length === 0 && <span className="muted small">zatím žádná role neběžela</span>}
            {subs.map((s) => (
              <RoleChip key={s.id} name={s.name} status={s.status} testid={`subagent-${s.name}`}>
                {state?.roles_mandat?.[s.name] && <div className="m" data-testid={`mandat-role-${s.name}`} data-sub={state.roles_mandat[s.name].sub ?? ""}>{state.roles_mandat[s.name].sub ? `jménem ${state.roles_mandat[s.name].name ?? state.roles_mandat[s.name].sub}` : "bez mandátu"}</div>}
                {s.result && <div className="m">{fmtUsd(s.result.cost_usd)} USD · nástroje {s.result.tool_uses ?? "?"} · {s.result.via ?? ""}</div>}
                {s.status === "running" && <div className="m">běží…</div>}
                {s.message && <div className="m err-text">{s.message}</div>}
              </RoleChip>))}
          </div>
        </div>
      </Card>

      {interrupt && <InterruptCard it={interrupt} view={view} reason={reason} setReason={setReason} budget={budget} setBudget={setBudget} kl={kl} setKl={setKl} reasonOk={reasonOk} decide={decide} resume={resume} />}

      <div className="grid2">
        <Card className="stack">
          <CardHeader><h3>Průběh</h3><span className="muted small">zprávy rolí, aktivity, rozhodnutí lidí</span></CardHeader>
          <Timeline view={view} />
        </Card>
        <Card className="stack">
          <details>
            <summary>Události AG-UI <Badge>{view.events.length}</Badge></summary>
            <div className="log" data-testid="event-log">{view.events.map((e, i) => <div key={`${e.gen}:${i}`} data-event-type={e.type}>{e.type}{e.outcome ? ` outcome=${e.outcome}` : ""}{e.protocolVersion ? ` protocolVersion=${e.protocolVersion}` : ""}{e.name ? ` ${e.name}` : ""}{e.activityType ? ` ${e.activityType}` : ""}</div>)}</div>
          </details>
          <p className="muted xs">Přihlášen {user.name} · tenant {user.tenant} · run je jen pohled, zdroj pravdy je ledger zakázky.</p>
        </Card>
      </div>
    </>
  );
}

/** Text artefaktu z poslední zprávy role `from` (HANDOFF) pro náhled v kartě rozhodnutí; disclosure zvlášť. */
function artifactPreview(msgs: Msg[], from?: string, hash?: string): { disc: string | null; body: string } | null {
  const m = [...msgs].reverse().find((x) => x.name === from && (!hash || x.text.includes(String(hash)))) ?? [...msgs].reverse().find((x) => x.name === from);
  if (!m) return null; const s = splitDisclosure(m.text); return { disc: s.disc, body: s.body };
}
function splitDisclosure(text: string): { disc: string | null; body: string } {
  const i = text.indexOf("\n\n"); const disc = text.startsWith("> ") && i > 0 ? text.slice(2, i) : null;
  return { disc, body: disc ? text.slice(i + 2) : text };
}

function InterruptCard({ it, view, reason, setReason, budget, setBudget, kl, setKl, reasonOk, decide, resume }: { it: Interrupt; view: ThreadView; reason: string; setReason: (s: string) => void; budget: string; setBudget: (s: string) => void; kl: Record<string, boolean>; setKl: (v: Record<string, boolean>) => void; reasonOk: boolean; decide: (d: "approve" | "reject") => void; resume: (id: string, status: "resolved" | "cancelled", payload: unknown) => void }) {
  const md = it.metadata ?? {}; const bod = String(md.bod ?? ""); const msgs = selMessages(view); const state = view.state;
  const timeout = it.expiresAt ? <span className="muted small">do {new Date(it.expiresAt).toLocaleString("cs-CZ")} · bez rozhodnutí → Pozastaveno; pokračuje po Obnovit běh</span> : null;
  if (it.reason === "klasifikace") {
    const qs = (md.questions ?? []) as KlasQuestion[];
    return (
      <Card className="irq stack" testid="interrupt" data-interrupt-id={it.id} data-kind="klasifikace">
        <CardHeader><span className="eyebrow">Rozhodnutí člověka</span><h2>Klasifikační brána <span data-testid="interrupt-bod">klasifikace</span></h2><Badge tone="wait" dot>čeká na vás</Badge><span className="muted small">P1a · zadani.classify</span>{timeout}</CardHeader>
        <p>{it.message}</p>
        <KlasForm qs={qs} val={kl} onChange={setKl} prefix="klas" />
        <Field label="Poznámka (volitelná)"><textarea data-testid="klas-reason" value={reason} onChange={(x) => setReason(x.target.value)} /></Field>
        <div className="row"><Button variant="p" testid="klas-submit" onClick={() => { resume(it.id, "resolved", { answers: Object.fromEntries(qs.map((q) => [q.id, !!kl[q.id]])), reason: reason.trim() }); setReason(""); setKl({}); }}>Odeslat klasifikaci</Button><span className="muted small">profil rizika určí platforma deterministicky</span></div>
      </Card>);
  }
  if (it.reason === "dialog") {
    return (
      <Card className="irq stack" testid="interrupt" data-interrupt-id={it.id} data-kind="dialog">
        <CardHeader><span className="eyebrow">Rozhodnutí člověka</span><h2>Account se ptá (kolo <span data-testid="dialog-round">{md.round}</span>)</h2><Badge tone="wait" dot>čeká na vás</Badge>{timeout}</CardHeader>
        <div className="inset"><pre className="pre" data-testid="dialog-questions">{md.questions}</pre></div>
        <Field label="Vaše odpovědi (Account je zapracuje do Zadání; max 3 kola)"><textarea data-testid="dialog-answer" value={reason} onChange={(x) => setReason(x.target.value)} /></Field>
        <div className="row"><Button variant="p" disabled={reason.trim().length < 3} testid="dialog-submit" onClick={() => { resume(it.id, "resolved", { answer: reason.trim() }); setReason(""); }}>Odpovědět</Button></div>
      </Card>);
  }
  const prev = bod === "H1a" ? null : artifactPreview(msgs, md.from, md.artifact_hash);
  const klas = selActivities(view).filter((a) => a.type === "klasifikace" && a.content.state === "done").pop();
  const tasks = bod === "H4" ? selReviewTasks(view) : [];
  const unresolved = tasks.filter((t) => t.unresolved);
  const dangerous = bod === "rozpocet" || bod === "publikace" || bod === "role";
  return (
    <Card className={`irq stack ${bod === "rozpocet" ? "budget" : dangerous ? "danger" : ""}`} testid="interrupt" data-interrupt-id={it.id} data-kind="approval">
      <CardHeader><span className="eyebrow">Rozhodnutí člověka</span><h2><span data-testid="interrupt-bod">{bod}</span> · {BOD_TITLE[bod] ?? "Schválení"}</h2><Badge tone={dangerous ? "err" : "wait"} dot>čeká na vás</Badge>{timeout}</CardHeader>
      <p>{it.message}</p>
      <div className="meta">
        {md.from && <span>od role <b>{md.from}</b></span>}
        {md.artifact && <span>artefakt <b className="mono">{md.artifact}</b></span>}
        <span>hash <b className="mono" data-testid="interrupt-hash">{md.artifact_hash}</b></span>
        {md.action && <span>akce <b className="mono">{md.action}</b></span>}
        {md.process && <span>proces <b className="mono">{md.process}</b></span>}
      </div>
      {bod === "H1a" && (
        <div className="inset" data-testid="h1a-box">
          <span className="eyebrow">Poptávka zadavatele</span>
          <pre className="pre">{state?.poptavka ?? "(poptávka není ve stavu threadu)"}</pre>
          <span className="eyebrow">Důvod stanoviska (klasifikace)</span>
          <div className="small">{klas ? <>profil <code>{klas.content.profile}</code>, odpověď ano: <code>{klas.content.yes}</code>{klas.content.by ? <> · klasifikoval <b>{klas.content.by}</b></> : null}</> : "klasifikace zatím není v průběhu"}</div>
          <div className="hint">Stanovisko právníka patří do důvodu rozhodnutí: zda jde o vysoké riziko podle přílohy III (K4 veřejná správa / K5 změna účelu), jaké povinnosti z toho plynou (dokumentace, lidský dohled, informování zákazníka) a za jakých podmínek smí zakázka pokračovat. Schválit = pokračovat k Account s profilem <code>nejasne</code>, Zamítnout = pozastavit.</div>
        </div>)}
      {prev && (
        <div className="inset" data-testid="artifact-preview">
          {prev.disc && <div className="disc">{prev.disc}</div>}
          <pre className="pre">{prev.body.slice(0, 6000)}</pre>
        </div>)}
      {bod === "rozpocet" && (
        <div className="inset" data-testid="budget-box">
          <div><b>Rozpočet vyčerpán</b> – role <code>{md.role}</code>, zdroj <code data-testid="budget-source">{md.source}</code></div>
          <Tile k="útrata / strop (30 d)" tone="err"><span><code data-testid="budget-spent">{md.spent_usd ?? "?"}</code> <span className="muted">/</span> <code data-testid="budget-limit">{md.limit_usd ?? state?.budget_usd ?? "?"}</code> <span className="muted">USD</span></span><Progress value={Number(md.spent_usd ?? 0)} max={Number(md.limit_usd ?? state?.budget_usd ?? 0)} over /></Tile>
          <Field label="Nový strop zakázky (USD, 30 d)" hint="navýšení = N6: zapisuje se do gateway (rozpočty klíčů), registru a schválení; prázdné = jen opakovat pokus"><input data-testid="budget-new" className="mono" type="number" min="0" step="0.01" value={budget} onChange={(x) => setBudget(x.target.value)} placeholder="ponechat = jen opakovat pokus" /></Field>
        </div>)}
      {bod === "H4" && (
        <div className="inset" data-testid="h4-box">
          <div className="row"><b>Review:</b> <code data-testid="h4-verdict">{String(md.verdict ?? "?")}</code>{unresolved.length > 0 && <Badge tone="err" dot testid="h4-unresolved">{unresolved.length} nevyřešeno</Badge>}{md.pr_url && <a href={String(md.pr_url)} target="_blank" rel="noreferrer" data-testid="h4-pr">{String(md.pr_url)}</a>}</div>
          {tasks.length > 0 && <div className="h4tasks" data-testid="h4-tasks">{tasks.map((t) => <div key={t.task}><span>úkol {t.task}{t.nazev ? ` · ${t.nazev}` : ""}</span><Badge tone={t.unresolved ? "err" : t.verdict === "ok" ? "done" : "wait"} dot>{t.unresolved ? "REVIEW_UNRESOLVED" : t.verdict}{t.rounds ? ` · ${t.rounds} ${t.rounds === 1 ? "kolo" : "kola"}` : ""}</Badge></div>)}</div>}
          <div className="muted small">{md.verdict === "changes_requested" || unresolved.length ? "Reviewer žádá změny nebo kola review došla; text review je v Průběhu (zpráva role reviewer). Schválit = merge i přes námitku, Zamítnout = pozastavit." : "Schválit = merge PR (executor), Zamítnout = pozastavit zakázku."}</div>
        </div>)}
      {bod === "role" && (
        <div className="inset" data-testid="role-box">
          <div><b>Běh role selhal</b> – role <code>{String(md.role ?? "?")}</code> (pokus {String(md.attempt ?? 1)}): <code data-testid="role-error">{String(md.error ?? "")}</code></div>
          <div className="muted small">Schválit = jeden opakovaný běh role (platí se znovu), Zamítnout = pozastavit zakázku. Nic se nepublikovalo, další role neběží.</div>
        </div>)}
      {bod === "publikace" && (
        <div className="inset" data-testid="publish-box">
          <div><b>Publikace selhala</b> – {String(md.publish_kind ?? "?")} do GitHubu{md.live ? " (ostrý běh)" : ""}: <code data-testid="publish-error">{String(md.error ?? "")}</code></div>
          <div className="muted small">Schválit = opakovat publikaci (po opravě PAT nebo výpadku), Zamítnout = pozastavit zakázku. Nic se neodeslalo jinam, role znovu neběží.</div>
        </div>)}
      {(bod === "H1" || bod === "H2") && <div className="hint" data-testid="reason-roles-hint">Důvod schválení u {bod} dostanou další role jako závazné rozhodnutí zadavatele (volba varianty, doplnění zadání, předpoklady z ADR) – pište ho tak, aby podle něj mohl Vývojář pracovat.</div>}
      <Field label={`Důvod rozhodnutí · povinný, ≥ ${MIN_REASON} znaků · zapisuje se do org.approvals, podepsaný token nese vaše jméno`}>
        <textarea data-testid="approve-reason" value={reason} onChange={(x) => setReason(x.target.value)} />
        <span className={`cnt ${reasonOk ? "ok" : ""}`}>{reason.trim().length} znaků</span>
      </Field>
      <div className="row">
        <Button variant="p" disabled={!reasonOk} testid="approve-submit" onClick={() => decide("approve")}>Schválit</Button>
        <Button variant="d" disabled={!reasonOk} testid="reject-submit" onClick={() => decide("reject")}>Zamítnout</Button>
        {!reasonOk && <span className="muted small" data-testid="reason-hint">bez důvodu nelze rozhodnout</span>}
        {reasonOk && <span className="muted small">zamítnutí = pozastavit zakázku</span>}
      </div>
    </Card>);
}

// --- časová osa: zprávy rolí (disclosure zvlášť), aktivity jako řádky klíč=hodnota, rozhodnutí lidí zvýrazněná -----------------------
const ACT_LABEL: Record<string, string> = { hitl: "rozhodnutí člověka", approval: "schválení", dialog: "dialog", klasifikace: "klasifikace", sla: "SLA", budget: "rozpočet", budget_gate: "brána rozpočtu", pod: "sandbox", tool: "nástroj", handoff: "předání", published: "publikace", publish: "publikace", role: "role", executor: "executor", stop: "stop", channel: "kanál", task: "úkol", review: "review", mandat: "mandát", registry: "registr", notify: "oznámení", zakazka: "zakázka" };
function Timeline({ view }: { view: ThreadView }) {
  const items = selTimeline(view); const decisions = selDecisions(view);
  if (!items.length) return view.run.status === "connecting" || view.run.status === "running" ? <Skeleton lines={4} /> : <p className="empty">zatím žádný průběh</p>;
  return (
    <div className="tl" data-testid="timeline">
      {items.map((x) => x.kind === "msg" ? <MsgItem key={x.item.id} m={x.item} /> : <ActItem key={x.item.id} a={x.item} decision={x.item.type === "hitl" && x.item.content.state === "wait" ? decisions[String(x.item.content.bod)] : undefined} />)}
    </div>);
}
function MsgItem({ m }: { m: Msg }) {
  const text = m.draft != null && !m.text ? m.draft : m.text; const { disc, body } = splitDisclosure(text);
  return (
    <div className="ev msg" data-testid={`msg-${m.name ?? m.role}`} data-role={m.role}>
      <div className="h"><b>{m.name ?? m.role}</b><span className="muted small">({m.role})</span><span className="t">{fmtTime(m.ts)}</span></div>
      {disc && <div className="disc" data-testid="disclosure">{disc}</div>}
      <div className="body">{body || <span className="muted">(prázdné)</span>}</div>
    </div>);
}
function ActItem({ a, decision }: { a: Act; decision?: { decision: string; by?: string; reason?: string } }) {
  const c = a.content; const st = c.state ? String(c.state) : null;
  const tone = a.type === "hitl" ? (st === "approved" ? "done" : st === "rejected" || st === "timeout" || st === "invalid_token" ? "err" : "wait") : a.type === "sla" || a.type === "budget" ? "err" : a.type === "approval" ? (c.decision === "approve" ? "done" : "err") : a.type === "stop" ? (c.kind === "resume" ? "done" : "err") : null;
  const title = a.type === "hitl" ? `${c.bod} · ${st === "wait" ? "čeká na člověka" : st === "approved" ? "schváleno" : st === "rejected" ? "zamítnuto" : st === "timeout" ? "bez rozhodnutí → Pozastaveno" : st}` : a.type === "approval" ? `${c.bod} · ${c.decision === "approve" ? "schválil" : "zamítl"} ${c.by ?? ""}` : a.type === "sla" ? `SLA překročeno: ${c.bod}` : a.type === "task" ? `úkol ${c.n}/${c.total} · ${c.nazev ?? ""}` : a.type === "review" ? `review úkolu ${c.task} · ${st === "unresolved" ? "REVIEW_UNRESOLVED" : "changes_requested"}` : a.type === "stop" ? (c.kind === "resume" ? `obnoveno (${c.by ?? ""})` : `zastaveno (${c.by ?? ""})`) : null;
  const kv = Object.entries(c).filter(([k, v]) => v != null && typeof v !== "object" && !(title && ["bod", "state", "decision", "by", "n", "total", "nazev", "task", "kind"].includes(k)));
  return (
    <div className={`ev ${a.type}`} data-testid={`act-${a.type}`}>
      <div className="act">
        <span className="k">{a.type}</span>
        {title ? <b>{title}</b> : <span className="muted">{ACT_LABEL[a.type] ?? a.type}</span>}
        {tone && st && a.type === "hitl" && <Badge tone={tone} dot>{st}</Badge>}
        {kv.map(([k, v]) => <span key={k} className="kv">{k}=<code>{String(v)}</code></span>)}
        <span className="t">{fmtTime(a.ts)}</span>
      </div>
      {decision && <div className="muted small">{decision.decision === "approve" ? "schválil" : "zamítl"} <b>{decision.by}</b>{decision.reason ? <> · „{decision.reason}“</> : null}</div>}
      {a.type === "review" && c.review && <div className="disc">{String(c.review).slice(0, 600)}</div>}
    </div>);
}
export type { ReactNode };
