// Klient AG-UI serveru platformy: login (Keycloak přes server), seznam threadů (zakázek), run = SSE stream událostí AG-UI 1.0,
// rozhodnutí člověka = RunAgentInput.resume, stop = forwardedProps.action. Vlastní SSE parser (fetch + ReadableStream) – bez frameworku.
import { PROTOCOL_VERSION, type BaseEvent } from "@ag-ui/core";

export type User = { sub: string; name: string; tenant: string; roles: string[] };
export type ThreadState = {
  id: string; tenant: string; status: string | null; stav: string | null; bod: string | null;
  budget_usd: number | null; spent_usd: number | null; roles: Record<string, string>; started: number | null; poptavka?: string;
};

const BASE = (import.meta.env.VITE_AGUI_BASE as string | undefined) ?? "";
let token: string | null = sessionStorage.getItem("agui_token");

export function setToken(t: string | null) {
  token = t;
  if (t) sessionStorage.setItem("agui_token", t); else sessionStorage.removeItem("agui_token");
}
export function hasToken() { return !!token; }
function auth(): Record<string, string> { return token ? { Authorization: `Bearer ${token}` } : {}; }

export async function login(username: string, password: string): Promise<User> {
  const r = await fetch(`${BASE}/agui/login`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ username, password }) });
  if (!r.ok) throw new Error(`přihlášení odmítnuto (${r.status})`);
  const j = await r.json();
  setToken(j.access_token);
  return j.user as User;
}

export async function me(): Promise<User> {
  const r = await fetch(`${BASE}/agui/me`, { headers: auth() });
  if (!r.ok) throw new Error(`me ${r.status}`);
  return (await r.json()) as User;
}

export async function listThreads(): Promise<{ tenant: string; threads: ThreadState[] }> {
  const r = await fetch(`${BASE}/agui/threads`, { headers: auth() });
  if (!r.ok) throw new Error(`threads ${r.status}`);
  return r.json();
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
