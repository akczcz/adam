// Stavový model karty zakázky (brief „Datový tok a proč dnes nedokresluje“): jeden reducer nad AG-UI událostmi s normalizovanými entitami
// (zprávy, aktivity, subagenti podle id) a odvozené selektory. Nový run pohled NEMAŽE – server při každém runu přehrává celý ledger, takže
// entity se stejným id se jen nahradí; co nový run nepotvrdí do RUN_FINISHED, se odstraní (generace). Otevřený interrupt je odvozený z aktivit
// stejně jako `pending_interrupt` na serveru (poslední *_WAIT bez pozdějšího rozhodnutí/timeoutu), detail (zpráva, metadata) nese RUN_FINISHED.
import { EventType } from "@ag-ui/core";
import type { ThreadState } from "./api";

export type Ev = Record<string, any>;
export type Msg = { id: string; role: string; name?: string; text: string; draft: string | null; sub?: string; ts: number; idx: number; gen: number };
export type Act = { id: string; type: string; content: Record<string, any>; sub?: string; ts: number; idx: number; gen: number };
export type Sub = { id: string; name: string; status: "running" | "done" | "error"; result?: any; message?: string; gen: number; ts: number };
export type Interrupt = { id: string; reason: string; message?: string; metadata?: Record<string, any>; expiresAt?: string };
export type RunStatus = "idle" | "connecting" | "running" | "interrupt" | "finished" | "cancelled" | "stalled" | "error";

export type ThreadView = {
  id: string;
  gen: number;                                   // generace = pořadí runu v tomto pohledu
  events: { type: string; gen: number; outcome?: string; protocolVersion?: string; name?: string; activityType?: string }[];
  messages: Record<string, Msg>;
  activities: Record<string, Act>;
  subagents: Record<string, Sub>;
  state: ThreadState | null;
  run: { status: RunStatus; id: string | null; protocol: string | null; error: string | null; syncing: boolean; retries: number };
  lastInterrupt: Interrupt | null;               // z posledního RUN_FINISHED outcome=interrupt
  resolving: string | null;                      // interrupt, o kterém člověk právě rozhodl (optimisticky skrytý do potvrzení streamem)
  custom: Record<string, any>;                   // CUSTOM události (thread_created, stopped, resumed)
};

export type Action =
  | { type: "run-start"; resolvingInterrupt?: string | null; retry?: boolean }
  | { type: "event"; event: Ev }
  | { type: "run-error"; message: string; willRetry: boolean }
  | { type: "poll"; state: ThreadState }
  | { type: "state"; state: ThreadState };

export function initialView(id: string): ThreadView {
  return { id, gen: 0, events: [], messages: {}, activities: {}, subagents: {}, state: null, run: { status: "idle", id: null, protocol: null, error: null, syncing: false, retries: 0 }, lastInterrupt: null, resolving: null, custom: {} };
}

const idx = (messageId: string) => Number(String(messageId).split(":")[1] ?? 0);   // id aktivit/zpráv = `<zakazka>:<index ledgeru>[:msg]`

export function reducer(v: ThreadView, a: Action): ThreadView {
  switch (a.type) {
    case "run-start": {
      const gen = a.retry ? v.gen : v.gen + 1;
      return { ...v, gen, run: { ...v.run, status: "connecting", error: null, syncing: true, retries: a.retry ? v.run.retries + 1 : 0 }, resolving: a.resolvingInterrupt ?? (a.retry ? v.resolving : null) };
    }
    case "run-error": return { ...v, run: { ...v.run, status: "error", error: a.message, syncing: false } };
    case "state": return { ...v, state: a.state };
    case "poll": {
      // polling jen doplňuje: při běžícím streamu nepřepisuje stav ze snapshotu (závod snapshot × polling), jinak nahradí celý stav threadu
      if (v.run.status === "connecting" || v.run.status === "running") {
        if (!v.state) return v;
        const { mandat, roles_mandat, sla_breaches, stalled, status } = a.state;
        return { ...v, state: { ...v.state, mandat, roles_mandat, sla_breaches, stalled, status: status ?? v.state.status } };
      }
      return { ...v, state: a.state };
    }
    case "event": return onEvent(v, a.event);
    default: return v;
  }
}

function onEvent(v: ThreadView, e: Ev): ThreadView {
  const gen = v.gen; const ts = Number(e.timestamp ?? 0);
  const events = [...v.events, { type: e.type, gen, outcome: e.outcome?.type, protocolVersion: e.protocolVersion, name: e.name, activityType: e.activityType }];
  switch (e.type) {
    case EventType.RUN_STARTED:
      return { ...v, events, run: { ...v.run, status: "running", id: e.runId ?? null, protocol: e.protocolVersion ?? null, error: null, syncing: true, retries: 0 } };
    case EventType.STATE_SNAPSHOT:
      return { ...v, events, state: e.snapshot ?? v.state, run: { ...v.run, syncing: false } };
    case EventType.STATE_DELTA:
      return { ...v, events };
    case EventType.TEXT_MESSAGE_START: {
      const prev = v.messages[e.messageId];
      const m: Msg = prev ? { ...prev, draft: "", gen, role: e.role ?? prev.role, name: e.name ?? prev.name } : { id: e.messageId, role: e.role, name: e.name, text: "", draft: "", sub: e.subagentRunId, ts, idx: idx(e.messageId), gen };
      return { ...v, events, messages: { ...v.messages, [m.id]: m } };
    }
    case EventType.TEXT_MESSAGE_CONTENT: {
      const prev = v.messages[e.messageId]; if (!prev) return { ...v, events };
      return { ...v, events, messages: { ...v.messages, [prev.id]: { ...prev, draft: (prev.draft ?? "") + (e.delta ?? "") } } };
    }
    case EventType.TEXT_MESSAGE_END: {
      const prev = v.messages[e.messageId]; if (!prev) return { ...v, events };
      return { ...v, events, messages: { ...v.messages, [prev.id]: { ...prev, text: prev.draft ?? prev.text, draft: null } } };
    }
    case EventType.ACTIVITY_SNAPSHOT: {
      const act: Act = { id: e.messageId, type: e.activityType, content: e.content ?? {}, sub: e.subagentRunId, ts, idx: idx(e.messageId), gen };
      return { ...v, events, activities: { ...v.activities, [act.id]: act } };
    }
    case EventType.SUBAGENT_STARTED: {
      const prev = v.subagents[e.subagentRunId];
      // replay dřívějšího runu: hotová role se znovu „nerozběhne“ (status drží, dokud replay nedojde k FINISHED/ERROR téhož runu)
      const s: Sub = prev ? { ...prev, name: e.name ?? prev.name, gen } : { id: e.subagentRunId, name: e.name, status: "running", gen, ts };
      return { ...v, events, subagents: { ...v.subagents, [s.id]: s } };
    }
    case EventType.SUBAGENT_FINISHED: {
      const prev = v.subagents[e.subagentRunId];
      const s: Sub = { ...(prev ?? { id: e.subagentRunId, name: e.name ?? "?", ts }), status: "done", result: e.result, message: undefined, gen };
      return { ...v, events, subagents: { ...v.subagents, [s.id]: s } };
    }
    case EventType.SUBAGENT_ERROR: {
      const prev = v.subagents[e.subagentRunId];
      const s: Sub = { ...(prev ?? { id: e.subagentRunId, name: e.name ?? "?", ts }), status: "error", message: e.message, gen };
      return { ...v, events, subagents: { ...v.subagents, [s.id]: s } };
    }
    case EventType.CUSTOM:
      return { ...v, events, custom: { ...v.custom, [e.name]: e.value } };
    case EventType.RUN_ERROR:
      return { ...v, events, run: { ...v.run, status: "error", error: e.message ?? "RUN_ERROR", syncing: false } };
    case EventType.RUN_FINISHED: {
      const o = e.outcome ?? {};
      const status: RunStatus = o.type === "interrupt" ? "interrupt" : o.type === "cancelled" ? "cancelled" : e.result?.status === "STALLED" || e.metadata?.stalled ? "stalled" : "finished";
      const it: Interrupt | null = o.type === "interrupt" ? (o.interrupts?.[0] ?? null) : null;
      const prune = <T extends { gen: number }>(m: Record<string, T>) => Object.fromEntries(Object.entries(m).filter(([, x]) => x.gen === gen));   // co replay tohoto runu nepotvrdil, už v ledgeru není
      const messages = Object.fromEntries(Object.entries(prune(v.messages)).map(([k, m]) => [k, m.draft != null ? { ...m, text: m.draft, draft: null } : m]));
      return { ...v, events, messages, activities: prune(v.activities), subagents: prune(v.subagents), state: e.result ?? v.state, lastInterrupt: it, resolving: it && v.resolving === it.id ? null : v.resolving,
        run: { ...v.run, status, syncing: false } };
    }
    default: return { ...v, events };
  }
}

// --- selektory ----------------------------------------------------------------------------------------------------------------
export const selMessages = (v: ThreadView) => Object.values(v.messages).sort((a, b) => a.idx - b.idx || a.ts - b.ts);
export const selActivities = (v: ThreadView) => Object.values(v.activities).sort((a, b) => a.idx - b.idx || a.ts - b.ts);
export const selSubagents = (v: ThreadView) => Object.values(v.subagents).sort((a, b) => a.ts - b.ts);

/** Časová osa = zprávy + aktivity v pořadí ledgeru (index v id), stabilní klíč = id entity. */
export function selTimeline(v: ThreadView): ({ kind: "msg"; item: Msg } | { kind: "act"; item: Act })[] {
  const xs: ({ kind: "msg"; item: Msg } | { kind: "act"; item: Act })[] = [...selMessages(v).map((m) => ({ kind: "msg" as const, item: m })), ...selActivities(v).map((a) => ({ kind: "act" as const, item: a }))];
  return xs.sort((a, b) => a.item.idx - b.item.idx || (a.kind === "msg" ? -1 : 1));
}

/** Čekající bod odvozený z aktivit jako `pending_interrupt` na serveru (agui.py): poslední hitl/dialog/klasifikace „wait“ bez pozdějšího
    rozhodnutí/odpovědi/timeoutu. Aktivity dialogu a klasifikace hash artefaktu nenesou, proto se s interruptem páruje podle druhu a bodu. */
export type PendingWait = { kind: "hitl" | "dialog" | "klasifikace"; bod: string | null; hash: string | null };
export function selPendingWait(v: ThreadView): PendingWait | null {
  const acts = selActivities(v);
  const waits = acts.map((a, i) => [i, a] as const).filter(([, a]) => (a.type === "hitl" || a.type === "dialog" || a.type === "klasifikace") && a.content.state === "wait");
  if (!waits.length) return null;
  const [i, w] = waits[waits.length - 1]; const after = acts.slice(i + 1);
  if (w.type === "klasifikace") return after.some((a) => a.type === "klasifikace" && ["done", "answered", "timeout"].includes(a.content.state)) ? null : { kind: "klasifikace", bod: "klasifikace", hash: null };
  if (w.type === "dialog") return after.some((a) => a.type === "dialog" && ["answer", "timeout", "limit"].includes(a.content.state)) ? null : { kind: "dialog", bod: "dialog", hash: null };
  const later = after.some((a) => a.type === "hitl" && ["approved", "timeout", "invalid_token", "rejected"].includes(a.content.state) && a.content.bod === w.content.bod);
  return later ? null : { kind: "hitl", bod: w.content.bod ?? null, hash: w.content.artifact_hash ?? null };
}
export function matchesPending(it: Interrupt, p: PendingWait): boolean {
  if (p.kind === "dialog") return it.reason === "dialog";
  if (p.kind === "klasifikace") return it.reason === "klasifikace";
  return it.reason !== "dialog" && it.reason !== "klasifikace" && String(it.metadata?.bod ?? "") === String(p.bod ?? "") && (p.hash == null || it.metadata?.artifact_hash == null || String(it.metadata.artifact_hash) === String(p.hash));
}

/** Otevřený interrupt = detail z RUN_FINISHED, pokud ho aktivity potvrzují jako čekající a člověk o něm právě nerozhodl (optimistické skrytí). */
export function selOpenInterrupt(v: ThreadView): Interrupt | null {
  const it = v.lastInterrupt; if (!it) return null;
  if (v.resolving === it.id) return null;
  const pending = selPendingWait(v);
  if (pending && !matchesPending(it, pending)) return null;   // aktivity říkají, že čeká jiný bod – detail přijde s dalším RUN_FINISHED
  if (!pending && v.run.status !== "interrupt") return null;
  return it;
}

/** Souhrn review per úkol pro kartu H4 (P4-11: REVIEW_LOOP / REVIEW_UNRESOLVED, handoff s verdict a task). */
export function selReviewTasks(v: ThreadView): { task: number; nazev?: string; rounds: number; verdict: string; unresolved: boolean }[] {
  const tasks = new Map<number, { task: number; nazev?: string; rounds: number; verdict: string; unresolved: boolean }>();
  for (const a of selActivities(v)) {
    if (a.type === "task" && a.content.n != null) tasks.set(Number(a.content.n), { task: Number(a.content.n), nazev: a.content.nazev, rounds: 0, verdict: "?", unresolved: false });
    if (a.type === "handoff" && a.content.task != null && a.content.verdict) { const t = tasks.get(Number(a.content.task)) ?? { task: Number(a.content.task), rounds: 0, verdict: "?", unresolved: false }; t.verdict = String(a.content.verdict); t.rounds = Math.max(t.rounds, Number(a.content.round ?? 0)); tasks.set(t.task, t); }
    if (a.type === "review") { const t = tasks.get(Number(a.content.task)) ?? { task: Number(a.content.task), rounds: 0, verdict: "?", unresolved: false }; if (a.content.state === "unresolved") { t.unresolved = true; t.verdict = String(a.content.verdict ?? "unresolved"); t.rounds = Number(a.content.rounds ?? t.rounds); } else t.rounds = Math.max(t.rounds, Number(a.content.round ?? 0)); tasks.set(t.task, t); }
  }
  return [...tasks.values()].sort((a, b) => a.task - b.task);
}

/** Rozhodnutí člověka v bodě (approval z ledgeru) – pro časovou osu a nálezy scénáře 5 (H1a bez textu/důvodu). */
export function selDecisions(v: ThreadView): Record<string, { decision: string; by?: string; reason?: string }> {
  const out: Record<string, { decision: string; by?: string; reason?: string }> = {};
  for (const a of selActivities(v)) if (a.type === "approval" && a.content.bod) out[String(a.content.bod)] = { decision: a.content.decision, by: a.content.by, reason: a.content.reason };
  return out;
}
