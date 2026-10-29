// GUI nad celou firmou (P3-3): pohledy z Governance MCP (org.* přes org_reader, RLS per tenant) a akce (posun autonomie, stop tenanta, export).
import { useEffect, useState } from "react";
import { govExport, govPost, govTool, type User } from "./api";

type Row = Record<string, any>;

function useTool<T = Row[]>(name: string, args: Record<string, unknown> = {}, deps: unknown[] = []) {
  const [data, setData] = useState<T | null>(null); const [err, setErr] = useState<string | null>(null); const [tick, setTick] = useState(0);
  useEffect(() => { let live = true; govTool<T>(name, args).then((r) => { if (live) { setData(r.result); setErr(null); } }).catch((e) => live && setErr(String(e.message ?? e))); return () => { live = false; }; }, [name, tick, ...deps]);   // eslint-disable-line react-hooks/exhaustive-deps
  return { data, err, reload: () => setTick((t) => t + 1) };
}

function Table({ rows, cols, id }: { rows: Row[]; cols: string[]; id: string }) {
  if (!rows.length) return <p className="muted" data-testid={`${id}-empty`}>žádné řádky</p>;
  return (
    <table data-testid={id} data-rows={rows.length}>
      <thead><tr>{cols.map((c) => <th key={c}>{c}</th>)}</tr></thead>
      <tbody>{rows.map((r, i) => <tr key={i}>{cols.map((c) => <td key={c}>{fmt(r[c])}</td>)}</tr>)}</tbody>
    </table>
  );
}
function fmt(v: any): string { if (v == null) return ""; if (typeof v === "number") return Number.isInteger(v) ? String(v) : v.toFixed(4); if (typeof v === "object") return JSON.stringify(v); return String(v); }

export function Nav({ page }: { page: string }) {
  const items: [string, string][] = [["", "Zakázky"], ["firma", "Firma"], ["registr", "Registr agentů"], ["finops", "FinOps"], ["governance", "Governance"], ["audit", "Audit"]];
  return <nav className="row" data-testid="nav">{items.map(([k, l]) => <a key={k} href={`#/${k}`} data-testid={`nav-${k || "zakazky"}`} style={{ fontWeight: page === k ? 700 : 400 }}>{l}</a>)}</nav>;
}

export function FirmaPage({ user }: { user: User }) {
  const roles = useTool("roles"); const tenants = useTool("tenants");
  const [form, setForm] = useState({ role: "", tenant: user.tenant === "platform" ? "acme" : user.tenant, level: "A1", reason: "" });
  const [res, setRes] = useState<any>(null); const [seq, setSeq] = useState(0); const [stopSeq, setStopSeq] = useState(0);
  const [stopForm, setStopForm] = useState({ tenant: user.tenant === "platform" ? "beta" : user.tenant, reason: "" }); const [stopRes, setStopRes] = useState<any>(null);
  const submit = async (ev: React.FormEvent) => { ev.preventDefault(); const r = await govPost("autonomy", form); setRes({ ...r.body, http: r.status }); setSeq((x) => x + 1); roles.reload(); };
  const stop = async (resume: boolean) => { const r = await govPost(`tenant/${stopForm.tenant}/${resume ? "resume" : "stop"}`, { reason: stopForm.reason }); setStopRes({ ...r.body, http: r.status, action: resume ? "resume" : "stop" }); setStopSeq((x) => x + 1); tenants.reload(); };
  return (
    <>
      <div className="card">
        <h2 style={{ marginTop: 0 }}>Role × tenant: verze, eval gate, autonomie</h2>
        {roles.err && <p className="err">{roles.err}</p>}
        {roles.data && (
          <table data-testid="roles-table" data-rows={roles.data.length}>
            <thead><tr><th>Role</th><th>Verze</th><th>Stav</th><th>Eval gate (poslední)</th><th>Autonomie per tenant</th><th>max</th></tr></thead>
            <tbody>{roles.data.map((r: Row) => (
              <tr key={`${r.role_id}-${r.version}`} data-testid={`role-${r.role_id}`}>
                <td><b>{r.role_id}</b></td><td>{r.version}</td><td><span className={`badge ${r.status === "active" ? "done" : r.status === "suspended" ? "error" : ""}`}>{r.status}</span></td>
                <td>{(r.eval_gates ?? []).map((g: Row) => <span key={g.layer} className={`badge ${g.passed ? "done" : "error"}`} style={{ marginRight: 4 }}>{g.layer} {fmt(g.value)}/{fmt(g.threshold)}</span>)}</td>
                <td>{Object.entries(r.autonomy ?? {}).map(([t, a]: [string, any]) => <span key={t} className="badge" style={{ marginRight: 4 }} data-testid={`autonomy-${r.role_id}-${t}`}>{t}: {a.level}</span>)}{!Object.keys(r.autonomy ?? {}).length && <span className="muted">A0 (výchozí)</span>}</td>
                <td>{r.autonomy_max ?? ""}</td>
              </tr>))}</tbody>
          </table>)}
      </div>
      <div className="card">
        <h3 style={{ marginTop: 0 }}>Posun autonomie (metriky.md §6 – nahoru jen při splněných podmínkách, vždy s důvodem)</h3>
        <form onSubmit={submit} className="row">
          <div><label>Role</label><input data-testid="auto-role" value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })} placeholder="vyvojar" /></div>
          <div><label>Tenant</label><input data-testid="auto-tenant" value={form.tenant} onChange={(e) => setForm({ ...form, tenant: e.target.value })} /></div>
          <div><label>Cílová úroveň</label><select data-testid="auto-level" value={form.level} onChange={(e) => setForm({ ...form, level: e.target.value })}>{["A0", "A1", "A2", "A3"].map((l) => <option key={l}>{l}</option>)}</select></div>
          <div style={{ flex: 1 }}><label>Důvod (≥ 10 znaků)</label><input data-testid="auto-reason" value={form.reason} onChange={(e) => setForm({ ...form, reason: e.target.value })} /></div>
          <button className="primary" type="submit" disabled={!form.role || form.reason.trim().length < 10} data-testid="auto-submit">Změnit</button>
        </form>
        {res && (
          <div className={`ev ${res.ok ? "" : "stop"}`} style={{ marginTop: 8 }} data-testid="auto-result" data-ok={String(!!res.ok)} data-seq={seq}>
            {res.ok ? <span className="ok">zapsáno: {res.current} → {res.target}</span> : <span className="err">odmítnuto ({res.http}): {(res.reasons ?? [res.detail]).join("; ")}</span>}
            {res.metrics && <div className="muted">úkolů {res.metrics.tasks} · odmítnutí {res.metrics.reject_rate} · porušení A {res.metrics.violations_A} · eval {JSON.stringify(res.metrics.eval_gates)}</div>}
          </div>)}
      </div>
      <div className="card">
        <h3 style={{ marginTop: 0 }}>Tenanti</h3>
        {tenants.err && <p className="err">{tenants.err}</p>}
        {tenants.data && <Table id="tenants-table" rows={tenants.data} cols={["tenant_id", "name", "profile", "budget_usd", "spent_usd", "namespace", "status"]} />}
        <h4>Stop / resume tenanta (T5 – pozastaví všechny zakázky tenanta, ukončí sandboxy, zablokuje klíče gateway a paměť)</h4>
        <div className="row">
          <div><label>Tenant</label><input data-testid="tstop-tenant" value={stopForm.tenant} onChange={(e) => setStopForm({ ...stopForm, tenant: e.target.value })} /></div>
          <div style={{ flex: 1 }}><label>Důvod (≥ 10 znaků)</label><input data-testid="tstop-reason" value={stopForm.reason} onChange={(e) => setStopForm({ ...stopForm, reason: e.target.value })} /></div>
          <button className="danger" disabled={stopForm.reason.trim().length < 10} onClick={() => stop(false)} data-testid="tstop-submit">Stop tenanta</button>
          <button disabled={stopForm.reason.trim().length < 10} onClick={() => stop(true)} data-testid="tresume-submit">Resume</button>
        </div>
        {stopRes && <div className="ev stop" style={{ marginTop: 8 }} data-testid="tstop-result" data-ok={String(!!stopRes.ok)} data-seq={stopSeq}>{stopRes.ok ? <span className="ok">{stopRes.action}: zakázky {JSON.stringify(stopRes.paused ?? stopRes.resumed)} · pody {JSON.stringify(stopRes.pods_killed ?? [])} · klíče {String(stopRes.keys_blocked ?? stopRes.keys_unblocked)}</span> : <span className="err">chyba ({stopRes.http}): {stopRes.detail}</span>}</div>}
      </div>
    </>
  );
}

export function RegistrPage() {
  const agents = useTool("agents"); const events = useTool("agent_events");
  return (
    <>
      <div className="card"><h2 style={{ marginTop: 0 }}>Registr agentů (T12) – instance rolí</h2>{agents.err && <p className="err">{agents.err}</p>}{agents.data && <Table id="agents-table" rows={agents.data} cols={["agent_id", "tenant_id", "role_id", "role_version", "zakazka_id", "on_behalf_of", "model", "gateway_key_id", "sandbox_profile", "node", "cost_usd", "created_at"]} />}</div>
      <div className="card"><h3 style={{ marginTop: 0 }}>Události registru</h3>{events.data && <Table id="events-table" rows={events.data} cols={["created_at", "kind", "tenant_id", "role_id", "agent_id", "reason", "actor"]} />}</div>
    </>
  );
}

export function FinopsPage() {
  const f = useTool<Row>("finops"); const l = useTool<Row>("ledger");
  return (
    <div className="card">
      <h2 style={{ marginTop: 0 }}>FinOps – 30d okno (zdroj: útrata klíčů v gateway → org.zakazky)</h2>
      {f.err && <p className="err">{f.err}</p>}
      {f.data && (<>
        <h3>Tenanti</h3>
        <table data-testid="finops-tenants" data-rows={f.data.tenants.length}><thead><tr><th>Tenant</th><th>Strop</th><th>Útrata</th><th>%</th><th>Stav</th></tr></thead>
          <tbody>{f.data.tenants.map((t: Row) => <tr key={t.tenant_id} data-alert={String(t.alert)}><td>{t.tenant_id}</td><td>{fmt(t.budget_usd)}</td><td>{fmt(t.spent_usd)}</td><td>{t.pct ?? ""}{t.alert && <span className="badge error" style={{ marginLeft: 6 }}>≥ 80 %</span>}</td><td>{t.status}</td></tr>)}</tbody></table>
        <h3>Zakázky</h3>
        <Table id="finops-zakazky" rows={f.data.zakazky} cols={["zakazka_id", "tenant_id", "status", "budget_usd", "spent_usd", "pct", "spent_by_role"]} />
        <h3>Per role (součet)</h3>
        <Table id="finops-roles" rows={Object.entries(f.data.by_role).map(([role, usd]) => ({ role, usd }))} cols={["role", "usd"]} />
      </>)}
      <h3>Per-request ledger z gateway (ClickHouse, nezávisle na budget_usage)</h3>
      {l.err && <p className="err">{l.err}</p>}
      {l.data && (<>
        <p className="muted" data-testid="ledger-source">{l.data.source}{l.data.error ? ` · ${l.data.error}` : ""} · okno {l.data.window_days} d</p>
        <Table id="finops-ledger-zakazky" rows={(l.data.by_zakazka ?? []).map((z: Row) => ({ ...z, roles: undefined }))} cols={["zakazka_id", "tenant_id", "status", "requests", "ledger_usd", "spent_usd", "delta_usd"]} />
        <Table id="finops-ledger" rows={l.data.rows ?? []} cols={["tenant_id", "zakazka_id", "role", "requests", "cost_usd", "input_tokens", "output_tokens", "last"]} />
      </>)}
    </div>
  );
}

export function GovernancePage() {
  const rep = useTool<Row>("governance_report"); const risks = useTool("risk_register"); const sla = useTool("sla_events"); const [exp, setExp] = useState<string | null>(null);
  return (
    <>
      <div className="card">
        <h2 style={{ marginTop: 0 }}>Governance report (metriky.md §5 – úplnost T11–T15)</h2>
        {rep.err && <p className="err">{rep.err}</p>}
        {rep.data && (<>
          <p data-testid="report-summary">zakázek <b>{rep.data.summary.zakazky}</b>, úplných <b>{rep.data.summary.complete}</b>, s mezerami <b data-testid="report-gaps">{rep.data.summary.with_gaps}</b> · pohled tenanta {rep.data.tenant_view} · {rep.data.generated_at}</p>
          <table data-testid="report-table" data-rows={rep.data.zakazky.length}><thead><tr><th>Zakázka</th><th>Tenant</th><th>Stav</th><th>Chybí</th><th>Útrata / strop</th></tr></thead>
            <tbody>{rep.data.zakazky.map((z: Row) => <tr key={z.zakazka_id} data-testid={`report-${z.zakazka_id}`} data-missing={(z.missing ?? []).join(",")}><td>{z.zakazka_id}</td><td>{z.tenant_id}</td><td>{z.status}</td><td>{(z.missing ?? []).map((m: string) => <span key={m} className="badge waiting" style={{ marginRight: 4 }}>{m}</span>)}{!z.missing?.length && <span className="ok">úplné</span>}</td><td>{fmt(z.spent_usd)} / {fmt(z.budget_usd)}</td></tr>)}</tbody></table>
          <h4>Role a eval gate</h4>
          <Table id="report-roles" rows={rep.data.roles} cols={["role_id", "version", "status", "eval_gate"]} />
          <details><summary>Položky T11–T15</summary><ul>{Object.entries(rep.data.summary.t_items).map(([k, v]) => <li key={k}><b>{k}</b> – {String(v)}</li>)}</ul></details>
        </>)}
      </div>
      <div className="card"><h3 style={{ marginTop: 0 }}>Risk register (T11)</h3>{risks.data && <Table id="risks-table" rows={risks.data} cols={["risk_id", "tenant_id", "use_case_id", "ai_act_class", "category", "likelihood", "impact", "status", "owner", "review_at"]} />}</div>
      <div className="card"><h3 style={{ marginTop: 0 }}>SLA bodů (procesy.md) – překročení a eskalace</h3>{sla.data && <Table id="sla-table" rows={sla.data} cols={["created_at", "tenant_id", "zakazka_id", "process_id", "bod", "sla_s", "escalated_to"]} />}</div>
      <div className="card">
        <h3 style={{ marginTop: 0 }}>Export pro deployera (čl. 13(3)(f)) – JSONL, jen řádky tenanta (RLS)</h3>
        <button onClick={async () => setExp(await govExport())} data-testid="export-button">Stáhnout export</button>
        {exp != null && <div style={{ marginTop: 8 }}><span data-testid="export-lines" data-lines={exp.split("\n").filter(Boolean).length}>řádků: {exp.split("\n").filter(Boolean).length}</span><pre className="log" data-testid="export-preview">{exp.slice(0, 4000)}</pre></div>}
      </div>
    </>
  );
}

export function AuditPage() {
  const a = useTool("approvals");
  return <div className="card"><h2 style={{ marginTop: 0 }}>Audit – rozhodnutí lidí (org.approvals, T6)</h2>{a.err && <p className="err">{a.err}</p>}{a.data && <Table id="approvals-table" rows={a.data} cols={["decided_at", "tenant_id", "workflow_instance", "process_id", "action", "decision", "approver", "reason", "channel"]} />}</div>;
}
