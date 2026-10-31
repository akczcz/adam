// Klient AG-UI serveru platformy: login (Keycloak přes server), seznam threadů (zakázek), run = SSE stream událostí AG-UI 1.0,
// rozhodnutí člověka = RunAgentInput.resume, stop = forwardedProps.action. Vlastní SSE parser (fetch + ReadableStream) – bez frameworku.
import { PROTOCOL_VERSION, type BaseEvent } from "@ag-ui/core";

export type User = { sub: string; name: string; tenant: string; roles: string[] };
export type ThreadState = {
  id: string; tenant: string; status: string | null; stav: string | null; bod: string | null;
  budget_usd: number | null; spent_usd: number | null; roles: Record<string, string>; started: number | null; poptavka?: string;
  profile?: string | null; sensitivity?: string | null; sla_breaches?: string[];
  wf_version?: string | null; stalled?: { wf_version: string | null; hint: string } | null;   // P3-6 E13: STALLED = chybí verze orchestrátoru
};
export type KlasQuestion = { id: string; text: string; yes: string };

const BASE = (import.meta.env.VITE_AGUI_BASE as string | undefined) ?? "";
let token: string | null = sessionStorage.getItem("agui_token");
let refreshToken: string | null = sessionStorage.getItem("agui_refresh");
let expiresAt = Number(sessionStorage.getItem("agui_exp") ?? 0);

export function setToken(t: string | null, refresh?: string | null, expiresIn?: number) {
  token = t;
  if (t) sessionStorage.setItem("agui_token", t); else sessionStorage.removeItem("agui_token");
  if (refresh !== undefined) { refreshToken = refresh; if (refresh) sessionStorage.setItem("agui_refresh", refresh); else sessionStorage.removeItem("agui_refresh"); }
  expiresAt = t && expiresIn ? Date.now() + expiresIn * 1000 : 0; sessionStorage.setItem("agui_exp", String(expiresAt));
}
export function hasToken() { return !!token; }
function auth(): Record<string, string> { return token ? { Authorization: `Bearer ${token}` } : {}; }

/** Access token Keycloaku žije 15 min; dlouhá zakázka (role v Kata podech) ho přežije → před každým voláním obnovit, když zbývá < 90 s (P3-2 nález). */
async function ensureFresh(): Promise<void> {
  if (!token || !refreshToken || !expiresAt || Date.now() < expiresAt - 90_000) return;
  const r = await fetch(`${BASE}/agui/refresh`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ refresh_token: refreshToken }) });
  if (!r.ok) { setToken(null, null); throw new Error(`přihlášení vypršelo (${r.status})`); }
  const j = await r.json(); setToken(j.access_token, j.refresh_token ?? refreshToken, j.expires_in ?? 900);
}

export async function login(username: string, password: string): Promise<User> {
  const r = await fetch(`${BASE}/agui/login`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ username, password }) });
  if (!r.ok) throw new Error(`přihlášení odmítnuto (${r.status})`);
  const j = await r.json();
  setToken(j.access_token, j.refresh_token ?? null, j.expires_in ?? 900);
  return j.user as User;
}

export async function me(): Promise<User> {
  await ensureFresh();
  const r = await fetch(`${BASE}/agui/me`, { headers: auth() });
  if (!r.ok) throw new Error(`me ${r.status}`);
  return (await r.json()) as User;
}

export async function klasQuestions(): Promise<KlasQuestion[]> {
  await ensureFresh();
  const r = await fetch(`${BASE}/agui/klasifikace`, { headers: auth() });
  if (!r.ok) throw new Error(`klasifikace: ${r.status}`);
  return (await r.json()).questions as KlasQuestion[];
}

/** Stav threadu mimo run (P3-4): při otevřeném interruptu GUI dotazuje stav – SLA překročení a profil přijdou i bez nového runu. */
export async function threadState(id: string): Promise<ThreadState> {
  await ensureFresh();
  const r = await fetch(`${BASE}/agui/threads/${encodeURIComponent(id)}`, { headers: auth() });
  if (!r.ok) throw new Error(`thread ${r.status}`);
  return (await r.json()).state as ThreadState;
}

export async function listThreads(): Promise<{ tenant: string; threads: ThreadState[] }> {
  await ensureFresh();
  const r = await fetch(`${BASE}/agui/threads`, { headers: auth() });
  if (!r.ok) throw new Error(`threads ${r.status}`);
  return r.json();
}

// --- governance (P3-3): čtení přes Governance MCP (proxy AG-UI serveru, token člověka), akce přes aplikaci ---------------------------
export async function govTool<T = any>(name: string, args: Record<string, unknown> = {}): Promise<{ tenant: string; result: T }> {
  await ensureFresh();
  const r = await fetch(`${BASE}/agui/gov/tools/${name}`, { method: "POST", headers: { "Content-Type": "application/json", ...auth() }, body: JSON.stringify(args) });
  if (!r.ok) { let d = `${r.status}`; try { d = `${r.status}: ${(await r.json()).detail}`; } catch { /* */ } throw new Error(d); }
  return r.json();
}

export async function govPost(path: string, body: Record<string, unknown>): Promise<{ ok: boolean; status: number; body: any }> {
  await ensureFresh();
  const r = await fetch(`${BASE}/agui/gov/${path}`, { method: "POST", headers: { "Content-Type": "application/json", ...auth() }, body: JSON.stringify(body) });
  let j: any = null; try { j = await r.json(); } catch { /* */ }
  return { ok: r.ok, status: r.status, body: j };
}

export async function govGet<T = any>(path: string): Promise<T> {
  await ensureFresh();
  const r = await fetch(`${BASE}/agui/gov/${path}`, { headers: auth() });
  if (!r.ok) { let d = `${r.status}`; try { d = `${r.status}: ${(await r.json()).detail}`; } catch { /* */ } throw new Error(d); }
  return r.json();
}

export async function govExport(): Promise<string> {
  await ensureFresh();
  const r = await fetch(`${BASE}/agui/gov/export.jsonl`, { headers: auth() });
  if (!r.ok) throw new Error(`export ${r.status}`);
  return r.text();
}

export type RunOptions = {
  threadId: string;
  runId?: string;
  messages?: { id: string; role: "user"; content: string }[];
  forwardedProps?: Record<string, unknown>;
  resume?: { interruptId: string; status: "resolved" | "cancelled"; payload?: unknown }[];
  onEvent: (e: BaseEvent & Record<string, unknown>) => void;
  signal?: AbortSignal;
};

/** POST /agui/run → SSE; každé `data:` je jedna AG-UI událost (JSON, camelCase). Vrací až po konci streamu. Při HTTP chybě vyhodí Error s textem serveru. */
export async function runAgent(o: RunOptions): Promise<void> {
  await ensureFresh();
  const body = {
    threadId: o.threadId, runId: o.runId ?? crypto.randomUUID(), protocolVersion: PROTOCOL_VERSION,
    messages: o.messages ?? [], tools: [], context: [], state: {}, forwardedProps: o.forwardedProps ?? {}, resume: o.resume,
  };
  const r = await fetch(`${BASE}/agui/run`, { method: "POST", headers: { "Content-Type": "application/json", Accept: "text/event-stream", ...auth() }, body: JSON.stringify(body), signal: o.signal });
  if (!r.ok || !r.body) {
    let detail = `${r.status}`;
    try { const j = await r.json(); detail = `${r.status}: ${j.detail ?? JSON.stringify(j)}`; } catch { /* text */ }
    throw new Error(detail);
  }
  const reader = r.body.getReader(); const dec = new TextDecoder(); let buf = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    let idx: number;
    while ((idx = buf.indexOf("\n\n")) >= 0) {
      const chunk = buf.slice(0, idx); buf = buf.slice(idx + 2);
      const data = chunk.split("\n").filter((l) => l.startsWith("data:")).map((l) => l.slice(5).trimStart()).join("\n");
      if (!data) continue;   // komentář (`: ping`) = keep-alive
      try { o.onEvent(JSON.parse(data)); } catch (e) { console.warn("AG-UI: nečitelná událost", e, data.slice(0, 200)); }
    }
  }
}
