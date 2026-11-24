// GUI nad celou firmou (P3-3): pohledy z Governance MCP (org.* přes org_reader, RLS per tenant) a akce (posun autonomie, stop tenanta, export).
import { useEffect, useState } from "react";
import { govExport, govGet, govPost, govTool, type User } from "./api";
import { Badge, Button, Card, CardHeader, DataTable, Field, PageError, Progress, Skeleton, fmt, type Col } from "./ui";

type Row = Record<string, any>;

function useTool<T = Row[]>(name: string, args: Record<string, unknown> = {}, deps: unknown[] = []) {
  const [data, setData] = useState<T | null>(null); const [err, setErr] = useState<string | null>(null); const [tick, setTick] = useState(0);
  useEffect(() => { let live = true; govTool<T>(name, args).then((r) => { if (live) { setData(r.result); setErr(null); } }).catch((e) => live && setErr(String(e.message ?? e))); return () => { live = false; }; }, [name, tick, ...deps]);   // eslint-disable-line react-hooks/exhaustive-deps
  return { data, err, reload: () => setTick((t) => t + 1) };
}
const cols = (keys: string[]): Col<Row>[] => keys.map((k) => ({ key: k, label: k, labelText: k, wide: k === keys[0] }));
function Table({ rows, cols: keys, id }: { rows: Row[]; cols: string[]; id: string }) { return <DataTable id={id} rows={rows} cols={cols(keys)} rowKey={(_, i) => String(i)} />; }
function Loading({ err, data, children }: { err: string | null; data: unknown; children: React.ReactNode }) { return <>{err && <PageError>{err}</PageError>}{data == null && !err ? <Skeleton /> : data != null ? children : null}</>; }

export function Nav({ page }: { page: string }) {
  const items: [string, string][] = [["", "Zakázky"], ["firma", "Firma"], ["registr", "Registr agentů"], ["finops", "FinOps"], ["governance", "Governance"], ["audit", "Audit"]];
  return <nav className="nav" data-testid="nav">{items.map(([k, l]) => <a key={k} href={`#/${k}`} data-testid={`nav-${k || "zakazky"}`} aria-current={page === k ? "page" : undefined}>{l}</a>)}</nav>;
}

const statusBadge = (s: string) => <Badge tone={s === "active" ? "done" : s === "suspended" || s === "stopped" ? "err" : ""} dot>{s}</Badge>;

export function FirmaPage({ user }: { user: User }) {
  const roles = useTool("roles"); const tenants = useTool("tenants");
  const [form, setForm] = useState({ role: "", tenant: user.tenant === "platform" ? "acme" : user.tenant, level: "A1", reason: "" });
  const [res, setRes] = useState<any>(null); const [seq, setSeq] = useState(0); const [stopSeq, setStopSeq] = useState(0);
  const [stopForm, setStopForm] = useState({ tenant: user.tenant === "platform" ? "beta" : user.tenant, reason: "" }); const [stopRes, setStopRes] = useState<any>(null);
  const submit = async (ev: React.FormEvent) => { ev.preventDefault(); const r = await govPost("autonomy", form); setRes({ ...r.body, http: r.status }); setSeq((x) => x + 1); roles.reload(); };
  const stop = async (resume: boolean) => { let r: { ok: boolean; status: number; body: any }; try { r = await govPost(`tenant/${stopForm.tenant}/${resume ? "resume" : "stop"}`, { reason: stopForm.reason }); } catch (e) { r = { ok: false, status: 0, body: { detail: `síť: ${String(e)}` } }; } setStopRes({ ...r.body, http: r.status, action: resume ? "resume" : "stop" }); setStopSeq((x) => x + 1); tenants.reload(); };
  const roleCols: Col<Row>[] = [
    { key: "role_id", label: "Role", wide: true, render: (r) => <b>{r.role_id}</b> },
    { key: "version", label: "Verze", render: (r) => <code>{r.version}</code> },
    { key: "status", label: "Stav", render: (r) => statusBadge(r.status) },
    { key: "eval_gates", label: "Eval gate (poslední)", labelText: "Eval gate", className: "wrap", render: (r) => <span className="row">{(r.eval_gates ?? []).map((g: Row) => <Badge key={g.layer} tone={g.passed ? "done" : "err"}>{g.layer} {fmt(g.value)}/{fmt(g.threshold)}</Badge>)}</span> },
    { key: "autonomy", label: "Autonomie per tenant", labelText: "Autonomie", className: "wrap", render: (r) => <span className="row">{Object.entries(r.autonomy ?? {}).map(([t, a]: [string, any]) => <Badge key={t} testid={`autonomy-${r.role_id}-${t}`}>{t}: {a.level}</Badge>)}{!Object.keys(r.autonomy ?? {}).length && <span className="muted">A0 (výchozí)</span>}</span> },
    { key: "autonomy_max", label: "max" },
  ];
  const tenantCols: Col<Row>[] = [
    { key: "tenant_id", label: "Tenant", wide: true, render: (r) => <b>{r.tenant_id}</b> }, { key: "name", label: "Název" }, { key: "profile", label: "Profil" },
    { key: "budget_usd", label: "Strop", right: true }, { key: "spent_usd", label: "Útrata", right: true }, { key: "namespace", label: "Namespace", render: (r) => <code>{r.namespace}</code> }, { key: "status", label: "Stav", render: (r) => statusBadge(String(r.status)) },
  ];
  return (
    <>
      <Card className="stack">
        <CardHeader><h2>Role × tenant</h2><span className="muted small">verze, eval gate, autonomie</span></CardHeader>
        <Loading err={roles.err} data={roles.data}>{roles.data && <DataTable id="roles-table" rows={roles.data} cols={roleCols} rowKey={(r) => `${r.role_id}-${r.version}`} rowProps={(r) => ({ "data-testid": `role-${r.role_id}` })} />}</Loading>
      </Card>
      <div className="grid2">
        <Card className="stack">
          <CardHeader><h3>Posun autonomie</h3><span className="muted small">metriky.md §6 – nahoru jen při splněných podmínkách, vždy s důvodem</span></CardHeader>
          <form onSubmit={submit} className="stack">
            <div className="row stretch">
              <Field label="Role" className="grow"><input data-testid="auto-role" className="mono" value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })} placeholder="vyvojar" /></Field>
              <Field label="Tenant" className="grow"><input data-testid="auto-tenant" className="mono" value={form.tenant} onChange={(e) => setForm({ ...form, tenant: e.target.value })} /></Field>
              <Field label="Cílová úroveň"><select data-testid="auto-level" value={form.level} onChange={(e) => setForm({ ...form, level: e.target.value })}>{["A0", "A1", "A2", "A3"].map((l) => <option key={l}>{l}</option>)}</select></Field>
            </div>
            <Field label="Důvod (≥ 10 znaků)"><input data-testid="auto-reason" value={form.reason} onChange={(e) => setForm({ ...form, reason: e.target.value })} /></Field>
            <div className="row"><Button variant="p" type="submit" disabled={!form.role || form.reason.trim().length < 10} testid="auto-submit">Změnit</Button></div>
          </form>
          {res && (
            <div className={`alert ${res.ok ? "ok" : "err"}`} data-testid="auto-result" data-ok={String(!!res.ok)} data-seq={seq}>
              {res.ok ? <span>zapsáno: {res.current} → {res.target}</span> : <span>odmítnuto ({res.http}): {(res.reasons ?? [res.detail]).join("; ")}</span>}
              {res.metrics && <div className="muted xs">úkolů {res.metrics.tasks} · odmítnutí {res.metrics.reject_rate} · porušení A {res.metrics.violations_A} · eval {JSON.stringify(res.metrics.eval_gates)}</div>}
            </div>)}
        </Card>
        <Card className="stack">
          <CardHeader><h3>Tenanti</h3></CardHeader>
          <Loading err={tenants.err} data={tenants.data}>{tenants.data && <DataTable id="tenants-table" rows={tenants.data} cols={tenantCols} rowKey={(r) => String(r.tenant_id)} />}</Loading>
          <span className="eyebrow">Stop / resume tenanta · T5</span>
          <p className="muted small">pozastaví všechny zakázky tenanta, ukončí sandboxy, zablokuje klíče gateway a paměť</p>
          <div className="row stretch">
            <Field label="Tenant"><input data-testid="tstop-tenant" className="mono" value={stopForm.tenant} onChange={(e) => setStopForm({ ...stopForm, tenant: e.target.value })} /></Field>
            <Field label="Důvod (≥ 10 znaků)" className="grow"><input data-testid="tstop-reason" value={stopForm.reason} onChange={(e) => setStopForm({ ...stopForm, reason: e.target.value })} /></Field>
          </div>
          <div className="row"><Button variant="d" disabled={stopForm.reason.trim().length < 10} onClick={() => stop(false)} testid="tstop-submit">Stop tenanta</Button><Button disabled={stopForm.reason.trim().length < 10} onClick={() => stop(true)} testid="tresume-submit">Resume</Button></div>
          {stopRes && <div className={`alert ${stopRes.ok ? "ok" : "err"}`} data-testid="tstop-result" data-ok={String(!!stopRes.ok)} data-seq={stopSeq}>{stopRes.ok ? <span>{stopRes.action}: zakázky {JSON.stringify(stopRes.paused ?? stopRes.resumed)} · pody {JSON.stringify(stopRes.pods_killed ?? [])} · klíče {String(stopRes.keys_blocked ?? stopRes.keys_unblocked)}</span> : <span>chyba ({stopRes.http}): {stopRes.detail ?? "bez odpovědi serveru (požadavek vypršel – stav zakázek zkontroluj v seznamu Zakázky)"}</span>}</div>}
        </Card>
      </div>
      {user.tenant === "platform" && <WfVersions />}
    </>
  );
}

// P3-6 E13: verze orchestrátoru v běžící aplikaci a instance per verze (provoz, jen tenant platform). Verze bez registrace s živými instancemi =
// zaseknuté zakázky (Dapr STALLED) → nasadit obraz se snímkem wf_versions/zakazka_<verze>.py; `drained` = snímek verze lze smazat.
function WfVersions() {
  const [data, setData] = useState<Row | null>(null); const [err, setErr] = useState<string | null>(null); const [tick, setTick] = useState(0);
  useEffect(() => { let live = true; govGet("wf/versions").then((r) => { if (live) { setData(r); setErr(null); } }).catch((e) => live && setErr(String(e.message ?? e))); const t = setInterval(() => setTick((x) => x + 1), 15000); return () => { live = false; clearInterval(t); }; }, [tick]);
  const rows = data ? Object.entries(data.versions ?? {}).map(([v, s]: [string, any]) => ({ version: v, ...s })) : [];
  const wfCols: Col<Row>[] = [
    { key: "version", label: "Verze", wide: true, render: (r) => <span data-testid="wf-col-version"><code>{r.version}</code> {r.version === data?.latest && <Badge tone="done">latest</Badge>}</span> },
    { key: "registered", label: "Registrovaná", render: (r) => <Badge tone={r.registered ? "done" : "err"} dot testid="wf-col-registered">{r.registered ? "ano" : "ne"}</Badge> },
    { key: "instances", label: "Instance (stav: počet)", labelText: "Instance", className: "wrap", render: (r) => <span className="row" data-testid="wf-col-instances">{Object.entries(r.instances ?? {}).map(([st, n]) => <Badge key={st} tone={st === "STALLED" ? "stalled" : st === "FAILED" ? "err" : st === "COMPLETED" ? "done" : st === "RUNNING" ? "run" : ""}>{st}: {String(n)}</Badge>)}</span> },
    { key: "stalled", label: "Zaseknuté", className: "wrap", render: (r) => <span className="row" data-testid="wf-col-stalled">{(r.stalled ?? []).map((z: string) => <a key={z} href={`#/t/${encodeURIComponent(z)}`}>{z}</a>)}{r.missing && <span className="err-text small">chybí verze – zakázky čekají na nasazení</span>}</span> },
    { key: "drained", label: "Drained (snímek lze smazat)", labelText: "Drained", render: (r) => <span data-testid="wf-col-drained">{r.drained ? "ano" : "ne"}</span> },
  ];
  return (
    <Card className="stack">
      <CardHeader><h3>Verze orchestrátoru zakázky</h3><span className="muted small">Dapr named versioning · instance per verze</span></CardHeader>
      {err && <PageError>{err}</PageError>}
      {data && (<>
        <p className="muted small" data-testid="wf-summary" data-stalled={(data.stalled ?? []).length} data-missing={(data.missing ?? []).join(",")}>
          latest <code>{data.latest}</code> · obraz <code>{data.current}</code> · zaseknuté zakázky <b data-testid="wf-stalled-count" className={(data.stalled ?? []).length ? "err-text" : ""}>{(data.stalled ?? []).length}</b>
          {!!(data.missing ?? []).length && <span className="err-text" data-testid="wf-missing"> · chybí verze {(data.missing ?? []).join(", ")} → nasadit obraz se snímkem wf_versions/zakazka_&lt;verze&gt;.py</span>}
        </p>
        <DataTable id="wf-versions" rows={rows} cols={wfCols} rowKey={(r) => r.version} rowProps={(r) => ({ "data-testid": `wf-version-${r.version}`, "data-registered": String(!!r.registered), "data-stalled": (r.stalled ?? []).length, "data-missing": String(!!r.missing) })} />
        {!!Object.keys(data.legacy?.instances ?? {}).length && <p className="muted small">instance před verzováním (jedou na latest): {JSON.stringify(data.legacy.instances)}</p>}
      </>)}
    </Card>
  );
}

export function RegistrPage() {
  const agents = useTool("agents"); const events = useTool("agent_events");
  return (
    <>
      <Card className="stack"><CardHeader><h2>Registr agentů</h2><span className="muted small">T12 · instance rolí</span></CardHeader><Loading err={agents.err} data={agents.data}>{agents.data && <Table id="agents-table" rows={agents.data} cols={["agent_id", "tenant_id", "role_id", "role_version", "zakazka_id", "on_behalf_of", "model", "gateway_key_id", "sandbox_profile", "node", "cost_usd", "created_at"]} />}</Loading></Card>
      <Card className="stack"><CardHeader><h3>Události registru</h3></CardHeader><Loading err={events.err} data={events.data}>{events.data && <Table id="events-table" rows={events.data} cols={["created_at", "kind", "tenant_id", "role_id", "agent_id", "reason", "actor"]} />}</Loading></Card>
    </>
  );
}

export function FinopsPage() {
  const f = useTool<Row>("finops"); const l = useTool<Row>("ledger");
  const tenants: Row[] = f.data?.tenants ?? []; const byRole = Object.entries(f.data?.by_role ?? {}).map(([role, usd]) => ({ role, usd: Number(usd) })).sort((a, b) => b.usd - a.usd); const maxRole = Math.max(0.000001, ...byRole.map((r) => r.usd));
  const spent = tenants.reduce((s, t) => s + Number(t.spent_usd ?? 0), 0); const budget = tenants.reduce((s, t) => s + Number(t.budget_usd ?? 0), 0); const alerts = tenants.filter((t) => t.alert);
  const tenantCols: Col<Row>[] = [
    { key: "tenant_id", label: "Tenant", wide: true, render: (t) => <><b>{t.tenant_id}</b> {t.alert && <Badge tone="err">≥ 80 %</Badge>}</> },
    { key: "budget_usd", label: "Strop", right: true }, { key: "spent_usd", label: "Útrata", right: true },
    { key: "pct", label: "%", className: "wrap", render: (t) => <span className="stack"><span>{t.pct ?? ""}{t.pct != null ? " %" : ""}</span><Progress value={Number(t.spent_usd ?? 0)} max={Number(t.budget_usd ?? 0)} over={!!t.alert} /></span> },
    { key: "status", label: "Stav", render: (t) => statusBadge(String(t.status)) },
  ];
  return (
    <>
      <div className="kpis">
        <div className="kpi"><div className="k">útrata 30 d</div><div className="v">{f.data ? spent.toFixed(2) : "–"} <small>USD</small></div></div>
        <div className="kpi"><div className="k">strop tenantů</div><div className="v">{f.data ? budget.toFixed(0) : "–"} <small>USD</small></div><Progress value={spent} max={budget} /></div>
        <div className="kpi"><div className="k">zakázek v okně</div><div className="v">{f.data ? (f.data.zakazky ?? []).length : "–"}</div></div>
        <div className="kpi"><div className="k">tenanti ≥ 80 %</div><div className={`v ${alerts.length ? "err-text" : ""}`}>{f.data ? alerts.length : "–"} <small>{alerts.map((t) => t.tenant_id).join(", ")}</small></div></div>
      </div>
      <div className="grid2">
        <Card className="stack">
          <CardHeader><h2>FinOps</h2><span className="muted small">30 d okno · zdroj: útrata klíčů v gateway → org.zakazky</span></CardHeader>
          <Loading err={f.err} data={f.data}>{f.data && (<>
            <h3>Tenanti</h3>
            <DataTable id="finops-tenants" rows={tenants} cols={tenantCols} rowKey={(t) => String(t.tenant_id)} rowProps={(t) => ({ "data-alert": String(t.alert) })} />
            <h3>Zakázky</h3>
            <Table id="finops-zakazky" rows={f.data.zakazky ?? []} cols={["zakazka_id", "tenant_id", "status", "budget_usd", "spent_usd", "pct", "spent_by_role"]} />
          </>)}</Loading>
        </Card>
        <div className="stack">
          <Card className="stack">
            <CardHeader><h3>Per role (součet)</h3></CardHeader>
            <Loading err={null} data={f.data}>{f.data && (byRole.length ? <div className="stack" data-testid="finops-roles" data-rows={byRole.length}>{byRole.map((r) => <div key={r.role} className="hbar"><span>{r.role}</span><div className="b"><i style={{ width: `${(r.usd / maxRole) * 100}%` }} /></div><span className="r">{r.usd.toFixed(4)} USD</span></div>)}</div> : <p className="empty" data-testid="finops-roles-empty">žádné řádky</p>)}</Loading>
          </Card>
        </div>
      </div>
      <Card className="stack">
        <CardHeader><h3>Per-request ledger z gateway</h3>{l.data && <Badge tone={l.data.error ? "err" : "done"} dot>{String(l.data.source ?? "").split(" ")[0]}</Badge>}</CardHeader>
        <Loading err={l.err} data={l.data}>{l.data && (<>
          <p className="muted small" data-testid="ledger-source">{l.data.source}{l.data.error ? ` · ${l.data.error}` : ""} · okno {l.data.window_days} d</p>
          <p className="muted xs">ClickHouse, nezávisle na budget_usage; proti rozpočtům gateway bývá opožděný o desítky sekund.</p>
          <Table id="finops-ledger-zakazky" rows={(l.data.by_zakazka ?? []).map((z: Row) => ({ ...z, roles: undefined }))} cols={["zakazka_id", "tenant_id", "status", "requests", "ledger_usd", "spent_usd", "delta_usd"]} />
          <Table id="finops-ledger" rows={l.data.rows ?? []} cols={["tenant_id", "zakazka_id", "role", "requests", "cost_usd", "input_tokens", "output_tokens", "last"]} />
        </>)}</Loading>
      </Card>
    </>
  );
}

export function GovernancePage() {
  const rep = useTool<Row>("governance_report"); const risks = useTool("risk_register"); const sla = useTool("sla_events"); const [exp, setExp] = useState<string | null>(null);
  const repCols: Col<Row>[] = [
    { key: "zakazka_id", label: "Zakázka", wide: true, render: (z) => <a href={`#/t/${encodeURIComponent(z.zakazka_id)}`}>{z.zakazka_id}</a> }, { key: "tenant_id", label: "Tenant" }, { key: "status", label: "Stav" },
    { key: "missing", label: "Chybí", className: "wrap", render: (z) => <span className="row">{(z.missing ?? []).map((m: string) => <Badge key={m} tone="wait">{m}</Badge>)}{!z.missing?.length && <span className="ok-text">úplné</span>}</span> },
    { key: "spent", label: "Útrata / strop", labelText: "Útrata / strop", right: true, render: (z) => `${fmt(z.spent_usd)} / ${fmt(z.budget_usd)}` },
  ];
  return (
    <>
      <Card className="stack">
        <CardHeader><h2>Governance report</h2><span className="muted small">metriky.md §5 · úplnost T11–T15 · AI Act čl. 13</span></CardHeader>
        <Loading err={rep.err} data={rep.data}>{rep.data && (<>
          <p data-testid="report-summary">zakázek <b>{rep.data.summary.zakazky}</b>, úplných <b>{rep.data.summary.complete}</b>, s mezerami <b data-testid="report-gaps">{rep.data.summary.with_gaps}</b> · pohled tenanta {rep.data.tenant_view} · {rep.data.generated_at}</p>
          <DataTable id="report-table" rows={rep.data.zakazky} cols={repCols} rowKey={(z) => String(z.zakazka_id)} rowProps={(z) => ({ "data-testid": `report-${z.zakazka_id}`, "data-missing": (z.missing ?? []).join(",") })} />
          <h4>Role a eval gate</h4>
          <Table id="report-roles" rows={rep.data.roles} cols={["role_id", "version", "status", "eval_gate"]} />
          <details><summary>Položky T11–T15</summary><ul>{Object.entries(rep.data.summary.t_items).map(([k, v]) => <li key={k}><b>{k}</b> – {String(v)}</li>)}</ul></details>
        </>)}</Loading>
      </Card>
      <Card className="stack"><CardHeader><h3>Risk register</h3><span className="muted small">T11</span></CardHeader><Loading err={risks.err} data={risks.data}>{risks.data && <Table id="risks-table" rows={risks.data} cols={["risk_id", "tenant_id", "use_case_id", "ai_act_class", "category", "likelihood", "impact", "status", "owner", "review_at"]} />}</Loading></Card>
      <Card className="stack"><CardHeader><h3>SLA bodů</h3><span className="muted small">procesy.md · překročení a eskalace</span></CardHeader><Loading err={sla.err} data={sla.data}>{sla.data && <Table id="sla-table" rows={sla.data} cols={["created_at", "tenant_id", "zakazka_id", "process_id", "bod", "sla_s", "escalated_to"]} />}</Loading></Card>
      <Card className="stack">
        <CardHeader><h3>Export pro deployera</h3><span className="muted small">čl. 13(3)(f) · JSONL, jen řádky tenanta (RLS)</span></CardHeader>
        <div className="row"><Button onClick={async () => setExp(await govExport())} testid="export-button">Stáhnout export</Button>{exp != null && <span data-testid="export-lines" data-lines={exp.split("\n").filter(Boolean).length}>řádků: {exp.split("\n").filter(Boolean).length}</span>}</div>
        {exp != null && <pre className="log" data-testid="export-preview">{exp.slice(0, 4000)}</pre>}
      </Card>
    </>
  );
}

export function AuditPage() {
  const a = useTool("approvals");
  return <Card className="stack"><CardHeader><h2>Audit</h2><span className="muted small">rozhodnutí lidí · org.approvals, T6</span></CardHeader><Loading err={a.err} data={a.data}>{a.data && <Table id="approvals-table" rows={a.data} cols={["decided_at", "tenant_id", "workflow_instance", "process_id", "action", "decision", "approver", "reason", "channel"]} />}</Loading></Card>;
}
