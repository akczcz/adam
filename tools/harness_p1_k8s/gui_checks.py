"""
gui_checks.py – U-1: GUI nad firmou řízené Playwrightem (P3-1). Měří se chování v prohlížeči (SSE AG-UI → DOM), ne JSON API:
přihlášení člověka, založení zakázky z GUI, průběh rolí jako subagentů, disclosure čl. 50 v první zprávě každé role, HITL jako
interrupt s povinným důvodem, stop s důvodem. Harness P1/K8s (harness.py --step p3-1) volá metody třídy Gui a skládá z důkazů checky
U1a–U1g; `--local` spustí tentýž scénář proti gui_fixture.py (vývoj GUI bez clusteru).
Playwright: pip install playwright && playwright install chromium (runner); lokálně PW_CHROMIUM=/opt/pw-browsers/chromium.
"""
from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

ROLES = ["account", "architekt", "vyvojar", "reviewer"]


class Gui:
    def __init__(self, base_url: str, *, headless=True, chromium: str | None = None, shots: Path | None = None, slow_ms=0):
        self.base, self.headless, self.chromium, self.shots, self.slow = base_url.rstrip("/") + "/", headless, chromium or os.environ.get("PW_CHROMIUM"), shots, slow_ms
        self.pw = self.browser = self.page = None; self.log = []

    def open(self):
        from playwright.sync_api import sync_playwright
        self.pw = sync_playwright().start()
        self.browser = self.pw.chromium.launch(headless=self.headless, executable_path=self.chromium or None, slow_mo=self.slow)
        self.page = self.browser.new_context(viewport={"width": 1280, "height": 900}, locale="cs-CZ").new_page()
        self.page.set_default_timeout(30_000)
        self.page.on("console", lambda m: self.log.append(f"[{m.type}] {m.text[:200]}") if m.type in ("error", "warning") else None)
        self.page.goto(self.base)
        return self

    def close(self):
        try:
            if self.browser: self.browser.close()
        finally:
            if self.pw: self.pw.stop()

    def shot(self, name):
        if self.shots:
            self.shots.mkdir(parents=True, exist_ok=True); self.page.screenshot(path=str(self.shots / f"{name}.png"), full_page=True)

    def t(self, tid): return self.page.get_by_test_id(tid)

    # --- přihlášení --------------------------------------------------------------------------------------------------
    def login_fail(self, user, pw):
        self.t("login-user").fill(user); self.t("login-pass").fill(pw); self.t("login-submit").click()
        self.t("login-error").wait_for(); err = self.t("login-error").inner_text()
        return {"error_shown": err, "still_login": self.t("login-submit").count() == 1}

    def login(self, user, pw):
        self.t("login-user").fill(user); self.t("login-pass").fill(pw); self.t("login-submit").click()
        self.t("user-name").wait_for()
        self.shot("login")
        return {"user": self.t("user-name").inner_text(), "tenant": self.t("user-tenant").inner_text(), "token": bool(self.token)}

    @property
    def token(self):
        """Aktuální access token z prohlížeče (GUI ho obnovuje refresh tokenem – 15 min lifespan Keycloaku zakázka v Kata podech přežije)."""
        return self.page.evaluate("sessionStorage.getItem('agui_token')")

    # --- seznam a založení ----------------------------------------------------------------------------------------------
    def threads_list(self):
        self.page.goto(self.base + "#/"); self.page.wait_for_timeout(300)
        self.page.wait_for_function("document.querySelector('[data-testid=threads-table]') || document.querySelector('[data-testid=threads-empty]')")
        rows = self.page.locator("[data-testid^=thread-row-]")
        out = []
        for i in range(rows.count()):
            r = rows.nth(i); out.append({"id": r.get_attribute("data-testid")[len("thread-row-"):], "cells": [c.strip() for c in r.locator("td").all_inner_texts()]})
        self.shot("threads")
        return out

    def create_thread(self, zid, poptavka, budget=None):
        self.page.goto(self.base + "#/"); self.t("new-id").wait_for()
        self.t("new-id").fill(zid); self.t("new-poptavka").fill(poptavka)
        if budget is not None: self.t("new-budget").fill(str(budget))
        self.t("new-submit").click()
        self.page.wait_for_function("document.querySelector('[data-testid=run-protocol]') && document.querySelector('[data-testid=run-protocol]').textContent !== '?'", timeout=60_000)
        return {"protocol": self.t("run-protocol").inner_text(), "run_id": self.t("run-id").inner_text(), "url": self.page.url}

    def open_thread(self, zid):
        self.page.goto(self.base + f"#/t/{zid}")
        self.page.wait_for_function("document.querySelector('[data-testid=run-status]') && !['idle','connecting'].includes(document.querySelector('[data-testid=run-status]').textContent)", timeout=60_000)
        return {"status": self.t("run-status").inner_text(), "error": self.t("run-error").inner_text() if self.t("run-error").count() else None}

    # --- průběh ------------------------------------------------------------------------------------------------------------
    def snapshot(self):
        subs = [{"name": s.get_attribute("data-testid")[len("subagent-"):], "status": s.get_attribute("data-status")} for s in self.page.locator("[data-testid^=subagent-]").all()]
        msgs = []
        for m in self.page.locator("[data-testid^=msg-]").all():
            d = m.locator("[data-testid=disclosure]")
            msgs.append({"name": m.get_attribute("data-testid")[len("msg-"):], "role": m.get_attribute("data-role"), "disclosure": d.inner_text() if d.count() else None})
        evs = [e.get_attribute("data-event-type") for e in self.page.locator("[data-testid=event-log] [data-event-type]").all()]
        st = {k: (self.t(f"state-{k}").inner_text() if self.t(f"state-{k}").count() else None) for k in ("stav", "status", "bod", "spent")}
        return {"run_status": self.t("run-status").inner_text(), "protocol": self.t("run-protocol").inner_text(), "subagents": subs, "messages": msgs, "events": evs, "state": st,
                "interrupt": self.t("interrupt").get_attribute("data-interrupt-id") if self.t("interrupt").count() else None, "error": self.t("run-error").inner_text() if self.t("run-error").count() else None}

    def wait_interrupt(self, bod, timeout_s=900):
        t0 = time.time()
        while time.time() - t0 < timeout_s:
            if self.t("interrupt").count() and self.t("interrupt-bod").inner_text().strip() == bod: break
            rs = self.t("run-status").inner_text() if self.t("run-status").count() else ""
            if rs in ("finished", "cancelled"): break   # "error" = i přechodný výpadek streamu (GUI se znovu připojí) – čekat dál do timeoutu
            self.page.wait_for_timeout(1500)
        self.shot(f"interrupt-{bod}")
        return {"waited_s": round(time.time() - t0, 1), **self.snapshot()}

    def wait_subagent(self, role, timeout_s=900):
        """Čeká, až se role objeví jako běžící subagent (SUBAGENT_STARTED) – pro stop uprostřed role."""
        t0 = time.time()
        while time.time() - t0 < timeout_s:
            s = self.t(f"subagent-{role}")
            if s.count() and s.get_attribute("data-status") == "running": return {"waited_s": round(time.time() - t0, 1), "status": "running"}
            rs = self.t("run-status").inner_text() if self.t("run-status").count() else ""
            if rs in ("finished", "error", "cancelled"): return {"waited_s": round(time.time() - t0, 1), "status": rs}
            self.page.wait_for_timeout(1000)
        return {"waited_s": round(time.time() - t0, 1), "status": "timeout"}

    def decide(self, reason, decision="approve"):
        """Tlačítka jsou bez důvodu (≥ 10 znaků) zakázaná – důkaz T6 v GUI; pak klik a čekání na nový run."""
        btn = self.t("approve-submit" if decision == "approve" else "reject-submit")
        self.t("approve-reason").fill(""); d0 = btn.is_disabled()
        self.t("approve-reason").fill("ok"); d1 = btn.is_disabled()
        self.t("approve-reason").fill(reason); d2 = btn.is_disabled()
        rid0 = self.t("run-id").inner_text()
        btn.click()
        try:
            self.page.wait_for_function(f"document.querySelector('[data-testid=run-id]') && document.querySelector('[data-testid=run-id]').textContent !== {json.dumps(rid0)}", timeout=60_000)
        except Exception as e:
            err = self.t("run-error").inner_text() if self.t("run-error").count() else None; self.shot("decide-failed")
            raise AssertionError(f"rozhodnutí {decision} nespustilo nový run (run-error: {err!r}, status {self.t('run-status').inner_text() if self.t('run-status').count() else '?'})") from e
        return {"disabled_empty": d0, "disabled_short": d1, "disabled_with_reason": d2, "new_run": self.t("run-id").inner_text() != rid0, "error": self.t("run-error").inner_text() if self.t("run-error").count() else None}

    def wait_finished(self, timeout_s=600, want=("finished",)):
        t0 = time.time()
        while time.time() - t0 < timeout_s:
            rs = self.t("run-status").inner_text() if self.t("run-status").count() else ""
            if rs in want or rs in ("error",): break
            self.page.wait_for_timeout(1500)
        self.shot("finished")
        return {"waited_s": round(time.time() - t0, 1), **self.snapshot()}

    def stop(self, reason):
        self.t("stop-button").click(); self.t("stop-reason").fill("x"); d1 = self.t("stop-confirm").is_disabled()
        self.t("stop-reason").fill(reason); d2 = self.t("stop-confirm").is_disabled(); t0 = time.time()
        self.t("stop-confirm").click()
        out = self.wait_finished(120, want=("cancelled",))
        self.shot("stopped")
        return {"disabled_short": d1, "disabled_with_reason": d2, "stop_to_cancelled_s": round(time.time() - t0, 1), **out}


def run_local(base, shots):
    """Scénář U-1 proti gui_fixture.py (bez clusteru): vrací checky stejně jako harness, jen bez důkazů z K8s/DB."""
    import httpx
    tag = time.strftime("%H%M%S"); z1, z2 = f"U1-{tag}-1", f"U1-{tag}-2"; checks = []
    def add(cid, ok, detail): checks.append({"id": cid, "status": "PASS" if ok else "FAIL", "detail": detail}); print(f"  {'✅' if ok else '❌'} {cid} {json.dumps(detail, ensure_ascii=False)[:300]}")
    g = Gui(base + "/gui/", shots=shots).open()
    try:
        lf = g.login_fail("adam", "wrong"); li = g.login("adam", "adam"); t0 = g.threads_list()
        add("U1a", li["user"] == "adam" and li["tenant"] == "acme" and li["token"] and lf["still_login"] and isinstance(t0, list), {"login": li, "fail": lf, "threads": len(t0)})
        cr = g.create_thread(z1, "Přidej do repa soubor NOTES.md s poznámkou o GUI.", 5)
        h1 = g.wait_interrupt("H1", 120)
        api = httpx.post(f"{base}/agui/run", headers={"Authorization": f"Bearer {g.token}"}, json={"threadId": z1, "runId": "x", "messages": [], "resume": [{"interruptId": h1["interrupt"], "status": "resolved", "payload": {"decision": "approve", "reason": "ok"}}]}, timeout=10)
        d1 = g.decide("Zadání odpovídá poptávce, kritéria jsou měřitelná.")
        h2 = g.wait_interrupt("H2", 120); d2 = g.decide("Návrh A je nejjednodušší a v rozpočtu.")
        h4 = g.wait_interrupt("H4", 120); d4 = g.decide("Review bez vad, soubory odpovídají zadání – merge.")
        h5 = g.wait_interrupt("H5", 120); d5 = g.decide("Nasazení schváleno, rollback je v runbooku.")
        fin = g.wait_finished(120)
        add("U1b", [s["name"] for s in fin["subagents"]] == ROLES and all(s["status"] == "done" for s in fin["subagents"]) and fin["state"]["stav"] == "Dokonceno", {"subagents": fin["subagents"], "state": fin["state"]})
        add("U1c", api.status_code == 422 and d1["disabled_empty"] and d1["disabled_short"] and not d1["disabled_with_reason"] and all(d["new_run"] for d in (d1, d2, d4, d5)), {"api_422": api.status_code, "d1": d1})
        add("U1e", all(any(m["name"] == r and m["disclosure"] and "AI agent" in m["disclosure"] for m in fin["messages"]) for r in ROLES), {"messages": fin["messages"]})
        add("U1g", cr["protocol"] == "1.0" and fin["events"][0] == "RUN_STARTED" and fin["events"][-1] == "RUN_FINISHED" and all(h["interrupt"] and h["interrupt"].startswith(f"hitl:{b}:") for h, b in ((h1, "H1"), (h2, "H2"), (h4, "H4"), (h5, "H5"))), {"protocol": cr["protocol"], "events_head": fin["events"][:3], "interrupts": [h["interrupt"] for h in (h1, h2, h4, h5)]})
        # U1d – cizí tenant: zakázka tenanta beta přes interní API; GUI (acme) ji nevidí, run → 404
        zb = f"U1-{tag}-beta"; httpx.post(f"{base}/zakazky", json={"id": zb, "poptavka": "cizí tenant", "tenant": "beta"}, timeout=10)
        lst = g.threads_list(); r404 = httpx.post(f"{base}/agui/run", headers={"Authorization": f"Bearer {g.token}"}, json={"threadId": zb, "runId": "y", "messages": []}, timeout=10)
        ot = g.open_thread(zb)
        add("U1d", zb not in [t["id"] for t in lst] and z1 in [t["id"] for t in lst] and r404.status_code == 404 and ot["status"] == "error" and "404" in (ot["error"] or ""), {"listed": [t["id"] for t in lst], "run_http": r404.status_code, "gui": ot})
        # U1f – stop uprostřed role s důvodem
        g.create_thread(z2, "Druhá zakázka – test stopu.", 5); h1b = g.wait_interrupt("H1", 120); g.decide("Zadání v pořádku, pokračovat k návrhu.")
        ws = g.wait_subagent("architekt", 60); st = g.stop("Zákazník pozastavil zakázku do vyjasnění rozpočtu.")
        z2st = httpx.get(f"{base}/zakazky/{z2}", timeout=10).json()
        add("U1f", ws["status"] == "running" and st["disabled_short"] and not st["disabled_with_reason"] and st["run_status"] == "cancelled" and z2st.get("status") == "SUSPENDED" and st["stop_to_cancelled_s"] < 60, {"subagent": ws, "stop": {k: st[k] for k in ("stop_to_cancelled_s", "run_status", "state")}, "wf": z2st})
    finally:
        g.close()
    n = sum(1 for c in checks if c["status"] == "FAIL"); print(f"== U-1 lokálně: {len(checks) - n}/{len(checks)} PASS; console: {g.log[:5]}")
    return checks


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--local", default="http://127.0.0.1:8010"); ap.add_argument("--shots", default="")
    a = ap.parse_args()
    cs = run_local(a.local, Path(a.shots) if a.shots else None)
    raise SystemExit(1 if any(c["status"] == "FAIL" for c in cs) else 0)
