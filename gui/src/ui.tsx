// Komponentová vrstva GUI (brief: Card, Badge, Button, Table, Field, Timeline, InterruptCard, RoleChip, Skeleton, Toast). Vzhled jen přes třídy
// ze styles.css a tokeny z tokens.css – žádné inline style={{…}}; data-testid se předávají beze změny (harness je drží jako kontrakt).
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { currentTheme, toggleTheme, type Theme } from "./theme";

type Div = React.HTMLAttributes<HTMLDivElement> & { testid?: string };
const cx = (...xs: (string | false | null | undefined)[]) => xs.filter(Boolean).join(" ");

export function Card({ className, testid, children, ...rest }: Div) {
  return <div className={cx("card", className)} data-testid={testid} {...rest}>{children}</div>;
}
export function CardHeader({ children, className }: { children: ReactNode; className?: string }) { return <div className={cx("ch", className)}>{children}</div>; }

export type Tone = "run" | "wait" | "done" | "susp" | "err" | "stalled" | "live" | "mock" | "acc" | "";
export function Badge({ tone = "", dot, children, testid, className, ...rest }: { tone?: Tone; dot?: boolean; children: ReactNode; testid?: string; className?: string } & Omit<React.HTMLAttributes<HTMLSpanElement>, "children">) {
  return <span className={cx("bd", tone, className)} data-testid={testid} {...rest}>{dot && <i className="dot" />}{children}</span>;
}
/** Odznak stavu zakázky podle stavu workflow a bodu (brief: RUNNING, čekání na člověka, SUSPENDED, COMPLETED, FAILED, STALLED). */
export function statusTone(status: string | null | undefined, bod?: string | null, stav?: string | null): Tone {
  if (status === "RUNNING") return bod ? "wait" : "run";
  if (status === "COMPLETED") return stav && stav !== "Dokonceno" ? "err" : "done";
  if (status === "SUSPENDED") return "susp";
  if (status === "STALLED") return "stalled";
  if (status === "FAILED" || status === "TERMINATED") return "err";
  return "";
}

/** Popisek stavu zakázky: server dává `stav` z výstupu workflow (Dokonceno, Pozastaveno, Odmitnuto, „čeká na H2“, „běží“), u pozastavené instance bez výstupu
    jen status SUSPENDED → česky Pozastaveno (eval scénář 5, nález 23: stav Pozastaveno s vlastním stylem). */
export function stavLabel(stav: string | null | undefined, status: string | null | undefined): string {
  if (stav === "SUSPENDED" || (!stav && status === "SUSPENDED")) return "Pozastaveno";
  return stav ?? status ?? "?";
}

export function Button({ variant = "", size, wide, className, testid, type = "button", ...rest }: React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "p" | "d" | "g" | ""; size?: "sm"; wide?: boolean; testid?: string }) {
  return <button type={type} className={cx("btn", variant, size, wide && "wide", className)} data-testid={testid} {...rest} />;
}

export function Field({ label, children, className, hint }: { label: ReactNode; children: ReactNode; className?: string; hint?: ReactNode }) {
  return <div className={cx("fld", className)}><label>{label}</label>{children}{hint && <span className="muted xs">{hint}</span>}</div>;
}
export function Checkbox({ label, testid, className, ...rest }: React.InputHTMLAttributes<HTMLInputElement> & { label: ReactNode; testid?: string }) {
  return <label className={cx("chk", className)}><input type="checkbox" data-testid={testid} {...rest} /><span>{label}</span></label>;
}

export function Tile({ k, children, tone = "", span2, className, testid, ...rest }: { k: ReactNode; children: ReactNode; tone?: "ok" | "warn" | "err" | "muted" | ""; span2?: boolean; className?: string; testid?: string } & Omit<Div, "children">) {
  return <div className={cx("tile", tone, span2 && "span2", className)} data-testid={testid} {...rest}><div className="k">{k}</div><div className="v">{children}</div></div>;
}
export function Progress({ value, max, over }: { value: number | null | undefined; max: number | null | undefined; over?: boolean }) {
  const pct = value != null && max ? Math.min(100, Math.max(0, (value / max) * 100)) : 0;
  return <div className={cx("pb", (over || (value != null && max != null && value > max)) && "over")}><b style={{ width: `${pct}%` }} /></div>;   // šířka pruhu = data, ne vzhled
}

export function RoleChip({ name, status, children, testid, ...rest }: { name: string; status: "running" | "done" | "error" | "pending"; children?: ReactNode; testid?: string } & Omit<Div, "children">) {
  return (
    <div className="role" data-testid={testid} data-status={status} {...rest}>
      <div className="n"><span>{name}</span><span className={cx("dot", status)} /></div>
      {children}
    </div>);
}

export function Skeleton({ lines = 3 }: { lines?: number }) {
  return <div className="stack" aria-busy="true">{Array.from({ length: lines }, (_, i) => <div key={i} className="sk" style={{ width: `${90 - i * 18}%` }} />)}</div>;   // šířky = rytmus skeletonu
}
export function Sync({ children }: { children: ReactNode }) { return <span className="sync"><i />{children}</span>; }

/** Chyba stránky (nahrazuje `.err` v původním GUI – harness čte [data-testid=page-error]). */
export function PageError({ children, testid = "page-error" }: { children: ReactNode; testid?: string }) { return <p className="alert err" data-testid={testid} role="alert">{children}</p>; }
export function Empty({ children, testid }: { children: ReactNode; testid?: string }) { return <p className="empty" data-testid={testid}>{children}</p>; }

// --- tabulky: na telefonu karty řádků (každá buňka nese data-l = popisek sloupce) ---------------------------------------------
export type Col<T> = { key: string; label: ReactNode; render?: (row: T, i: number) => ReactNode; className?: string; wide?: boolean; right?: boolean; labelText?: string };
function fmt(v: unknown): string { if (v == null) return ""; if (typeof v === "number") return Number.isInteger(v) ? String(v) : v.toFixed(4); if (typeof v === "object") return JSON.stringify(v); return String(v); }
export function Td({ col, children, className, testid }: { col: string; children: ReactNode; className?: string; testid?: string }) { return <td data-l={col} className={className} data-testid={testid}>{children}</td>; }
export function DataTable<T extends Record<string, any>>({ rows, cols, id, rowKey, rowProps, emptyText = "žádné řádky" }: { rows: T[]; cols: Col<T>[]; id: string; rowKey?: (r: T, i: number) => string; rowProps?: (r: T, i: number) => React.HTMLAttributes<HTMLTableRowElement> & Record<string, unknown>; emptyText?: string }) {
  if (!rows.length) return <Empty testid={`${id}-empty`}>{emptyText}</Empty>;
  return (
    <div className="tw"><table className="cards" data-testid={id} data-rows={rows.length}>
      <thead><tr>{cols.map((c) => <th key={c.key} className={cx(c.right && "r")}>{c.label}</th>)}</tr></thead>
      <tbody>{rows.map((r, i) => (
        <tr key={rowKey ? rowKey(r, i) : String(r.id ?? r[cols[0].key] ?? i)} {...(rowProps?.(r, i) ?? {})}>
          {cols.map((c) => <td key={c.key} data-l={c.labelText ?? (typeof c.label === "string" ? c.label : c.key)} className={cx(c.className, c.wide && "w", c.right && "r")}>{c.render ? c.render(r, i) : fmt(r[c.key])}</td>)}
        </tr>))}</tbody>
    </table></div>);
}
export { fmt };

// --- toasty (chyby streamu a akcí jako přechodné oznámení, ne přepis obsahu) ---------------------------------------------------
type ToastItem = { id: number; tone: "err" | "ok" | "warn" | ""; title: ReactNode; detail?: ReactNode; sticky?: boolean };
const ToastCtx = createContext<{ push: (t: Omit<ToastItem, "id">) => number; remove: (id: number) => void }>({ push: () => 0, remove: () => undefined });
export function ToastHost({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]); const seq = useRef(0);
  const remove = useCallback((id: number) => setItems((xs) => xs.filter((x) => x.id !== id)), []);
  const push = useCallback((t: Omit<ToastItem, "id">) => { const id = ++seq.current; setItems((xs) => [...xs.slice(-3), { ...t, id }]); if (!t.sticky) setTimeout(() => remove(id), 8000); return id; }, [remove]);
  const v = useMemo(() => ({ push, remove }), [push, remove]);
  return (
    <ToastCtx.Provider value={v}>
      {children}
      <div className="toasts" data-testid="toasts" aria-live="polite">{items.map((t) => <div key={t.id} className={cx("toast", t.tone)} data-tone={t.tone} onClick={() => remove(t.id)}><b>{t.title}</b>{t.detail && <div className="t">{t.detail}</div>}</div>)}</div>
    </ToastCtx.Provider>);
}
export function useToast() { return useContext(ToastCtx); }

// --- přepínač motivu (hlavička) ---------------------------------------------------------------------------------------------------
export function ThemeToggle() {
  const [t, setT] = useState<Theme>(() => currentTheme());
  useEffect(() => { setT(currentTheme()); }, []);
  return (
    <button type="button" className="tgl" data-testid="theme-toggle" data-theme={t} aria-label={t === "dark" ? "Přepnout na světlý motiv" : "Přepnout na tmavý motiv"} title={t === "dark" ? "Světlý motiv" : "Tmavý motiv"} onClick={() => setT(toggleTheme())}>
      <svg className="moon" viewBox="0 0 24 24" aria-hidden="true"><path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z" /></svg>
      <svg className="sun" viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="4" /><path d="M12 2v3M12 19v3M2 12h3M19 12h3M4.9 4.9l2.1 2.1M17 17l2.1 2.1M4.9 19.1 7 17M17 7l2.1-2.1" stroke="currentColor" strokeWidth="2" fill="none" /></svg>
    </button>);
}

export function Orb({ lg }: { lg?: boolean }) { return <span className={cx("orb", lg && "lg")} aria-hidden="true" />; }
export function fmtUsd(v: number | null | undefined, digits = 4): string { return v == null ? "–" : v.toFixed(digits); }
export function fmtTime(ms?: number | null): string { if (!ms) return ""; const d = new Date(ms); return d.toLocaleTimeString("cs-CZ", { hour: "2-digit", minute: "2-digit", second: "2-digit" }); }
export function fmtDate(s?: number | null): string { return s ? new Date(s * 1000).toLocaleString("cs-CZ", { day: "numeric", month: "numeric", year: "numeric", hour: "2-digit", minute: "2-digit" }) : ""; }
