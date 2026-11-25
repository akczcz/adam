// Životní cyklus runu AG-UI nad reducerem threadView: start/retry bez mazání pohledu, polling stavu při interruptu/STALLED (jen doplňuje),
// keepalive mandátu (P4-1), chyby streamu jako toast (ne přepis obsahu). Zdroj pravdy je ledger – run je jen pohled.
import { useCallback, useEffect, useReducer, useRef } from "react";
import { isActive, needsKeepalive, renewMandat, runAgent, threadState, type RunOptions, type ThreadState, type User } from "./api";
import { initialView, reducer, selOpenInterrupt, type ThreadView } from "./threadView";
import { useToast } from "./ui";

export type StartOpts = Pick<RunOptions, "resume" | "forwardedProps" | "messages">;
const MAX_RETRIES = 30; const RETRY_MS = 3000;

export function useThreadRun(id: string, user: User, initial?: StartOpts) {
  const [view, dispatch] = useReducer(reducer, id, initialView);
  const abort = useRef<AbortController | null>(null); const retries = useRef(0); const toast = useToast();
  const viewRef = useRef(view); viewRef.current = view;

  const start = useCallback(async (opts: StartOpts = {}, meta: { retry?: boolean; resolving?: string | null } = {}) => {
    abort.current?.abort(); const ac = new AbortController(); abort.current = ac;
    dispatch({ type: "run-start", retry: meta.retry, resolvingInterrupt: meta.resolving ?? null });
    try {
      await runAgent({ threadId: id, signal: ac.signal, onEvent: (e) => { if (!ac.signal.aborted) dispatch({ type: "event", event: e }); }, ...opts });
      if (!meta.retry) retries.current = 0;
    } catch (x: any) {
      if (ac.signal.aborted) return;
      const msg = String(x?.message ?? x); const http = /^\d{3}/.test(msg);
      // síťový výpadek streamu (ne 4xx/5xx ze serveru): po chvíli znovu sledovat thread – pohled zůstává, nic se neztratí
      const willRetry = !http && retries.current < MAX_RETRIES;
      dispatch({ type: "run-error", message: msg, willRetry });
      toast.push({ tone: "err", title: http ? "Server odmítl run" : "Stream přerušen", detail: willRetry ? `${msg} · znovu se připojuji (${retries.current + 1}/${MAX_RETRIES}); pohled zůstává, zdroj pravdy je ledger` : msg });
      if (willRetry) { retries.current += 1; setTimeout(() => { if (abort.current === ac) start({}, { retry: true }); }, RETRY_MS); }
    }
  }, [id, toast]);

  useEffect(() => { start(initial ?? {}); return () => abort.current?.abort(); }, [id]);   // eslint-disable-line react-hooks/exhaustive-deps

  // při interruptu / STALLED čte GUI každých 5 s stav threadu (SLA, profil, mandát) – jen doplňuje; STALLED → po nasazení verze nový run-pohled
  const rs = view.run.status;
  useEffect(() => {
    if (rs !== "interrupt" && rs !== "stalled") return;
    const t = setInterval(() => threadState(id).then((s) => { dispatch({ type: "poll", state: s }); if (rs === "stalled" && s.status !== "STALLED") start(); }).catch(() => undefined), 5000);
    return () => clearInterval(t);
  }, [rs, id, start]);

  // P4-1 keepalive: držitel s otevřeným detailem prodlužuje živý mandát sám (každých 30 s); vypršelý obnoví jen kliknutím
  useEffect(() => {
    const t = setInterval(() => threadState(id).then((s) => { dispatch({ type: "poll", state: s }); if (needsKeepalive(s, user) && isActive()) renewMandat(id, true).then((r) => dispatch({ type: "state", state: r.state })).catch(() => undefined); }).catch(() => undefined), 30000);
    return () => clearInterval(t);
  }, [id, user]);

  const renew = useCallback(() => renewMandat(id, false).then((r) => { dispatch({ type: "state", state: r.state }); return `mandát obnoven: ${r.mandat.name ?? r.mandat.sub}`; }).catch((x) => `obnova mandátu selhala: ${String(x?.message ?? x)}`), [id]);
  const resume = useCallback((interruptId: string, status: "resolved" | "cancelled", payload: unknown) => start({ resume: [{ interruptId, status, payload }] }, { resolving: interruptId }), [start]);
  const action = useCallback((act: "stop" | "resume", reason: string) => start({ forwardedProps: { action: act, reason } }), [start]);
  const applyState = useCallback((s: ThreadState) => dispatch({ type: "state", state: s }), []);

  return { view, interrupt: selOpenInterrupt(view), start, resume, action, renew, applyState } as { view: ThreadView; interrupt: ReturnType<typeof selOpenInterrupt>; start: typeof start; resume: typeof resume; action: typeof action; renew: typeof renew; applyState: typeof applyState };
}
