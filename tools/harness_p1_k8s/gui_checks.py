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
import re
import time
from pathlib import Path

ROLES = ["account", "architekt", "vyvojar", "reviewer"]
KLAS_KEYS = ["K1", "K2", "K3", "K4", "K5", "K6"]
KLAS_NO = {k: False for k in KLAS_KEYS}   # P3-4: dogfooding = vše „ne“ → profil standard


class Gui:
    def __init__(self, base_url: str, *, headless=True, chromium: str | None = None, shots: Path | None = None, slow_ms=0):
        self.base, self.headless, self.chromium, self.shots, self.slow = base_url.rstrip("/") + "/", headless, chromium or os.environ.get("PW_CHROMIUM"), shots, slow_ms
        self.pw = self.browser = self.page = None; self.log = []; self.keepalive = None   # harness dodá obnovu port-forwardu (fetch z prohlížeče nemá retry)
        self.cur = None; self._err_t = None; self.recoveries = []   # otevřený thread + obnova pohledu po vyčerpání retry GUI (E11 3. běh: „error Failed to fetch“ 50 min)

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
        self.shot("login"); self.creds = (user, pw)
        return {"user": self.t("user-name").inner_text(), "tenant": self.t("user-tenant").inner_text(), "token": bool(self.token)}

    def relogin(self):
        """P3-6 E10 nález: po neúspěšném refreshi GUI token zahodí (api.ts ensureFresh), stav `user` v paměti ale zůstane → další akce jde bez Authorization (401 „chybí Bearer token“).
        Harness se přihlásí znovu stejnými údaji (sessionStorage pryč → login stránka)."""
        self.page.evaluate("sessionStorage.clear()"); self.page.reload(); self.t("login-user").wait_for()
        return self.login(*self.creds)

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

    def create_thread(self, zid, poptavka, budget=None, klasifikace=None):
        """Nová zakázka z GUI: poptávka + dotazník K1–K6 (P3-4; výchozí vše „ne“) → první run s forwardedProps.klasifikace."""
        self.page.goto(self.base + "#/"); self.t("new-id").wait_for(); self.t("new-k-form").wait_for(timeout=30_000)
        self.t("new-id").fill(zid); self.t("new-poptavka").fill(poptavka); self.cur = zid
        if budget is not None: self.t("new-budget").fill(str(budget))
        for k, v in (klasifikace or {}).items():
            if v: self.t(f"new-k-{k}").check()
        if self.keepalive:
            try: self.keepalive()   # port-forward po dlouhém scénáři (U-2 ~15 min) občas spadne – fetch z prohlížeče nemá retry (E7 2. běh: RUN_STARTED nepřišel)
            except Exception: pass
        self.t("new-submit").click()
        try: self.page.wait_for_function("document.querySelector('[data-testid=run-protocol]') && document.querySelector('[data-testid=run-protocol]').textContent !== '?'", timeout=60_000)
        except Exception:
            if self.keepalive:
                try: self.keepalive()
                except Exception: pass
            self.open_thread(zid)   # zakázka už existuje (POST prošel, SSE ne) → nový run nad threadem
            self.page.wait_for_function("document.querySelector('[data-testid=run-protocol]') && document.querySelector('[data-testid=run-protocol]').textContent !== '?'", timeout=60_000)
        return {"protocol": self.t("run-protocol").inner_text(), "run_id": self.t("run-id").inner_text(), "url": self.page.url}

    def open_thread(self, zid):
        """Otevře thread s NOVÝM runem: navigace jen změnou hashe na tutéž URL stránku nereloaduje (React komponenta zůstane se starým stavem – po resume
        tenanta GUI ukazovalo run „cancelled“ ze stopu; nález P3-5 O3c) → nejdřív seznam, pak thread."""
        if self.page.url.endswith(f"#/t/{zid}"): self.page.goto(self.base + "#/"); self.page.wait_for_timeout(300)
        self.page.goto(self.base + f"#/t/{zid}"); self.cur = zid
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
        st["profile"] = self.t("state-profile").inner_text().strip() if self.t("state-profile").count() else None
        acts = {t: self.page.locator(f"[data-testid=act-{t}]").count() for t in ("klasifikace", "sla", "channel")}
        return {"run_status": self.t("run-status").inner_text(), "protocol": self.t("run-protocol").inner_text(), "subagents": subs, "messages": msgs, "events": evs, "state": st, "acts": acts,
                "interrupt": self.t("interrupt").get_attribute("data-interrupt-id") if self.t("interrupt").count() else None, "error": self.t("run-error").inner_text() if self.t("run-error").count() else None}

    def _recover(self, rs, after_s=100):
        """GUI po síťovém výpadku streamu (ne 4xx/5xx ze serveru) zkouší znovu jen 30× po 3 s (~90 s, App.tsx start()) a pak zůstane v „error“
        (E11 3. běh: „Failed to fetch“, workflow přitom čekal na dialog 50 min). Když „error“ bez HTTP kódu trvá déle než retry GUI, obnovit
        port-forward (keepalive) a znovu otevřít thread = nový run-pohled (run je jen pohled, zdroj pravdy je ledger)."""
        err = (self.t("run-error").inner_text() if self.t("run-error").count() else "") if rs == "error" else ""
        if rs != "error" or re.match(r"^\d{3}", err.strip()): self._err_t = None; return False
        self._err_t = self._err_t or time.time()
        if time.time() - self._err_t < after_s or not self.cur: return False
        if self.keepalive:
            try: self.keepalive()
            except Exception: pass
        try: self.open_thread(self.cur); self.recoveries.append({"t": time.strftime("%H:%M:%S"), "thread": self.cur, "error": err[:120]})
        except Exception as e: self.recoveries.append({"t": time.strftime("%H:%M:%S"), "thread": self.cur, "error": err[:120], "reopen_failed": type(e).__name__})
        self._err_t = None; return True

    def wait_interrupt(self, bod, timeout_s=900):
        t0 = time.time()
        while time.time() - t0 < timeout_s:
            if self.t("interrupt").count() and self.t("interrupt-bod").inner_text().strip() == bod: break
            rs = self.t("run-status").inner_text() if self.t("run-status").count() else ""
            if rs in ("finished", "cancelled"): break   # "error" = i přechodný výpadek streamu (GUI se znovu připojí; po vyčerpání jeho retry obnoví pohled _recover)
            self._recover(rs); self.page.wait_for_timeout(1500)
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

    def decide(self, reason, decision="approve", budget=None):
        """Tlačítka jsou bez důvodu (≥ 10 znaků) zakázaná – důkaz T6 v GUI; pak klik a čekání na nový run. budget (P3-6 E3): nový strop u bodu rozpocet."""
        btn = self.t("approve-submit" if decision == "approve" else "reject-submit")
        if budget is not None: self.t("budget-new").fill(str(budget))
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

    def wait_any_interrupt(self, timeout_s=900):
        """Čeká na libovolný interrupt (dialog Account nebo HITL) – P3-3: před H1 může přijít kolo otázek."""
        t0 = time.time()
        while time.time() - t0 < timeout_s:
            if self.t("interrupt").count(): return {"waited_s": round(time.time() - t0, 1), "kind": self.t("interrupt").get_attribute("data-kind"), "bod": self.t("interrupt-bod").inner_text().strip() if self.t("interrupt-bod").count() else "dialog", **self.snapshot()}
            rs = self.t("run-status").inner_text() if self.t("run-status").count() else ""
            if rs in ("finished", "cancelled"): break
            self._recover(rs); self.page.wait_for_timeout(1500)
        return {"waited_s": round(time.time() - t0, 1), "kind": None, "bod": None, **self.snapshot()}

    def classify(self, answers, reason=""):
        """P3-4: interrupt reason=klasifikace (zakázka založená bez dotazníku, např. interním API) – zaškrtnout „ano“, odeslat, nový run."""
        self.t("klas-form").wait_for(); q = self.page.locator("[data-testid^=klas-K]").count()
        for k, v in (answers or {}).items():
            if v: self.t(f"klas-{k}").check()
        if reason: self.t("klas-reason").fill(reason)
        rid0 = self.t("run-id").inner_text(); self.t("klas-submit").click()
        self.page.wait_for_function(f"document.querySelector('[data-testid=run-id]') && document.querySelector('[data-testid=run-id]').textContent !== {json.dumps(rid0)}", timeout=60_000)
        self.shot("klasifikace-answered")
        return {"questions_shown": q, "new_run": True}

    def wait_profile(self, timeout_s=120):
        """Čeká na profil rizika ve stavu zakázky (STATE_SNAPSHOT.profile z KLASIFIKACE) nebo konec runu."""
        t0 = time.time()
        while time.time() - t0 < timeout_s:
            if self.t("state-profile").count(): break
            rs = self.t("run-status").inner_text() if self.t("run-status").count() else ""
            if rs in ("finished", "cancelled"): break
            self.page.wait_for_timeout(1000)
        self.shot("profile")
        return {"waited_s": round(time.time() - t0, 1), "profile": self.t("state-profile").inner_text().strip() if self.t("state-profile").count() else None, **self.snapshot()}

    def wait_sla(self, timeout_s=120):
        """Čeká na indikaci překročení SLA (state-sla / aktivita sla) – zakázka přitom dál čeká na rozhodnutí."""
        t0 = time.time()
        while time.time() - t0 < timeout_s:
            if self.t("state-sla").count() or self.t("act-sla").count(): break
            self.page.wait_for_timeout(1000)
        self.shot("sla")
        return {"waited_s": round(time.time() - t0, 1), "sla_text": self.t("state-sla").inner_text() if self.t("state-sla").count() else None, "act_sla": self.t("act-sla").count(), "interrupt": self.t("interrupt").get_attribute("data-interrupt-id") if self.t("interrupt").count() else None}

    def answer_dialog(self, text):
        """Odpověď na otázky Account (P3-3): tlačítko bez textu zakázané, pak nový run."""
        self.t("dialog-answer").fill(""); d0 = self.t("dialog-submit").is_disabled(); q = self.t("dialog-questions").inner_text()
        self.t("dialog-answer").fill(text); rid0 = self.t("run-id").inner_text(); self.t("dialog-submit").click()
        self.page.wait_for_function(f"document.querySelector('[data-testid=run-id]') && document.querySelector('[data-testid=run-id]').textContent !== {json.dumps(rid0)}", timeout=60_000)
        self.shot("dialog-answered")
        return {"disabled_empty": d0, "questions": q[:300], "new_run": True}

    def page_rows(self, page, table_ids, timeout_s=60):
        """Stránka firmy (P3-3): počty řádků tabulek (data-rows) nebo prázdné stavy."""
        self.page.goto(self.base + f"#/{page}"); self.page.wait_for_timeout(500); out = {}
        for tid in table_ids:
            try:
                self.page.wait_for_function(f"document.querySelector('[data-testid={tid}]') || document.querySelector('[data-testid={tid}-empty]')", timeout=timeout_s * 1000)
                out[tid] = int(self.t(tid).get_attribute("data-rows")) if self.t(tid).count() else 0
            except Exception as e: out[tid] = f"err:{type(e).__name__}"
        self.shot(f"page-{page}")
        return out

    def autonomy(self, role, tenant, level, reason):
        self.page.goto(self.base + "#/firma"); self.t("auto-role").wait_for()
        self.t("auto-role").fill(role); self.t("auto-tenant").fill(tenant); self.t("auto-level").select_option(level); self.t("auto-reason").fill(reason)
        seq0 = self.t("auto-result").get_attribute("data-seq") if self.t("auto-result").count() else None
        self.t("auto-submit").click()
        try: self.page.wait_for_function(f"(() => {{ const e = document.querySelector('[data-testid=auto-result]'); return e && e.getAttribute('data-seq') !== {json.dumps(seq0)}; }})()", timeout=60_000)   # nový výsledek, ne starý z předchozího odeslání
        except Exception:   # P3-5 nález: spadlý port-forward → fetch z GUI bez odpovědi; obnovit tunel (keepalive harnessu), znovu odeslat
            if self.keepalive: self.keepalive()
            self.page.reload(); self.t("auto-role").wait_for(); self.t("auto-role").fill(role); self.t("auto-tenant").fill(tenant); self.t("auto-level").select_option(level); self.t("auto-reason").fill(reason)
            seq0 = self.t("auto-result").get_attribute("data-seq") if self.t("auto-result").count() else None; self.t("auto-submit").click()
            self.page.wait_for_function(f"(() => {{ const e = document.querySelector('[data-testid=auto-result]'); return e && e.getAttribute('data-seq') !== {json.dumps(seq0)}; }})()", timeout=90_000)
        self.shot(f"autonomy-{role}-{tenant}-{level}")
        return {"ok": self.t("auto-result").get_attribute("data-ok") == "true", "text": self.t("auto-result").inner_text()[:400]}

    def tenant_stop(self, tenant, reason, resume=False, _retry=True):
        self.page.goto(self.base + "#/firma"); self.t("tstop-tenant").wait_for()
        self.t("tstop-tenant").fill(tenant); self.t("tstop-reason").fill(""); d0 = self.t("tstop-submit").is_disabled(); self.t("tstop-reason").fill(reason)
        seq0 = self.t("tstop-result").get_attribute("data-seq") if self.t("tstop-result").count() else None
        self.t("tresume-submit" if resume else "tstop-submit").click()
        try: self.page.wait_for_function(f"(() => {{ const e = document.querySelector('[data-testid=tstop-result]'); return e && e.getAttribute('data-seq') !== {json.dumps(seq0)}; }})()", timeout=120_000)
        except Exception:
            if self.keepalive: self.keepalive()
            self.page.reload(); self.t("tstop-tenant").wait_for(); self.t("tstop-tenant").fill(tenant); self.t("tstop-reason").fill(reason)
            seq0 = self.t("tstop-result").get_attribute("data-seq") if self.t("tstop-result").count() else None; self.t("tresume-submit" if resume else "tstop-submit").click()
            self.page.wait_for_function(f"(() => {{ const e = document.querySelector('[data-testid=tstop-result]'); return e && e.getAttribute('data-seq') !== {json.dumps(seq0)}; }})()", timeout=120_000)
        self.shot(f"tenant-{'resume' if resume else 'stop'}-{tenant}")
        out = {"disabled_empty": d0, "ok": self.t("tstop-result").get_attribute("data-ok") == "true", "text": self.t("tstop-result").inner_text()[:400]}
        if not out["ok"] and "(401)" in out["text"] and _retry and getattr(self, "creds", None):   # 1. běh E10: GUI bez tokenu po neúspěšném refreshi → přihlásit znovu a jednou opakovat
            self.relogin(); return {**self.tenant_stop(tenant, reason, resume, _retry=False), "relogin_after": out["text"]}
        return out

    def report(self):
        self.page.goto(self.base + "#/governance"); self.t("report-summary").wait_for(timeout=60_000)
        rows = self.page.locator("[data-testid^=report-][data-missing]")
        out = [{"id": r.get_attribute("data-testid")[len("report-"):], "missing": (r.get_attribute("data-missing") or "").split(",") if r.get_attribute("data-missing") else []} for r in rows.all()]
        self.t("export-button").click(); self.t("export-lines").wait_for(timeout=60_000)
        self.shot("governance")
        return {"gaps": int(self.t("report-gaps").inner_text()), "rows": out, "export_lines": int(self.t("export-lines").get_attribute("data-lines")), "export_preview": self.t("export-preview").inner_text()[:2000]}

    def wait_finished(self, timeout_s=600, want=("finished",)):
        t0 = time.time()
        while time.time() - t0 < timeout_s:
            rs = self.t("run-status").inner_text() if self.t("run-status").count() else ""
            if rs in want or rs in ("error",): break
            self.page.wait_for_timeout(1500)
        self.shot("finished")
        return {"waited_s": round(time.time() - t0, 1), **self.snapshot()}

    def stop(self, reason):
        try: self.t("stop-button").wait_for(timeout=15_000)
        except Exception:   # run po výpadku SSE/port-forwardu ve stavu error → tlačítko není; obnovit spojení a otevřít thread novým runem (E8 1. běh, T1e)
            if self.keepalive:
                try: self.keepalive()
                except Exception: pass
            self.open_thread(self.page.url.split("#/t/")[-1]); self.t("stop-button").wait_for(timeout=30_000)
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
        w0 = g.wait_any_interrupt(120); dlg = g.answer_dialog("Soubor do zakazky/<id>/NOTES.md; rozpočet výchozí.") if w0.get("kind") == "dialog" else None   # P3-3: dialog Account
        h1 = g.wait_interrupt("H1", 120)
        api = httpx.post(f"{base}/agui/run", headers={"Authorization": f"Bearer {g.token}"}, json={"threadId": z1, "runId": "x", "messages": [], "resume": [{"interruptId": h1["interrupt"], "status": "resolved", "payload": {"decision": "approve", "reason": "ok"}}]}, timeout=10)
        d1 = g.decide("Zadání odpovídá poptávce, kritéria jsou měřitelná.")
        h2 = g.wait_interrupt("H2", 120); d2 = g.decide("Návrh A je nejjednodušší a v rozpočtu.")
        h4 = g.wait_interrupt("H4", 120); d4 = g.decide("Review bez vad, soubory odpovídají zadání – merge.")
        h5 = g.wait_interrupt("H5", 120); d5 = g.decide("Nasazení schváleno, rollback je v runbooku.")
        fin = g.wait_finished(120)
        add("U1b", list(dict.fromkeys(s["name"] for s in fin["subagents"])) == ROLES and all(s["status"] == "done" for s in fin["subagents"]) and fin["state"]["stav"] == "Dokonceno", {"subagents": fin["subagents"], "state": fin["state"]})
        add("U1c", api.status_code == 422 and d1["disabled_empty"] and d1["disabled_short"] and not d1["disabled_with_reason"] and all(d["new_run"] for d in (d1, d2, d4, d5)), {"api_422": api.status_code, "d1": d1})
        add("U1e", all(any(m["name"] == r and m["disclosure"] and "AI agent" in m["disclosure"] for m in fin["messages"]) for r in ROLES), {"messages": fin["messages"]})
        add("U1g", cr["protocol"] == "1.0" and fin["events"][0] == "RUN_STARTED" and fin["events"][-1] == "RUN_FINISHED" and all(h["interrupt"] and h["interrupt"].startswith(f"hitl:{b}:") for h, b in ((h1, "H1"), (h2, "H2"), (h4, "H4"), (h5, "H5"))), {"protocol": cr["protocol"], "events_head": fin["events"][:3], "interrupts": [h["interrupt"] for h in (h1, h2, h4, h5)]})
        # U1d – cizí tenant: zakázka tenanta beta přes interní API; GUI (acme) ji nevidí, run → 404
        zb = f"U1-{tag}-beta"; httpx.post(f"{base}/zakazky", json={"id": zb, "poptavka": "cizí tenant", "tenant": "beta"}, timeout=10)
        lst = g.threads_list(); r404 = httpx.post(f"{base}/agui/run", headers={"Authorization": f"Bearer {g.token}"}, json={"threadId": zb, "runId": "y", "messages": []}, timeout=10)
        ot = g.open_thread(zb)
        add("U1d", zb not in [t["id"] for t in lst] and z1 in [t["id"] for t in lst] and r404.status_code == 404 and ot["status"] == "error" and "404" in (ot["error"] or ""), {"listed": [t["id"] for t in lst], "run_http": r404.status_code, "gui": ot})
        # U1f – stop uprostřed role s důvodem
        g.create_thread(z2, "Druhá zakázka – test stopu.", 5)
        if g.wait_any_interrupt(120).get("kind") == "dialog": g.answer_dialog("Soubor do zakazky/<id>/NOTES.md; rozpočet výchozí.")
        h1b = g.wait_interrupt("H1", 120); g.decide("Zadání v pořádku, pokračovat k návrhu.")
        ws = g.wait_subagent("architekt", 60); st = g.stop("Zákazník pozastavil zakázku do vyjasnění rozpočtu.")
        z2st = httpx.get(f"{base}/zakazky/{z2}", timeout=10).json()
        add("U1f", ws["status"] == "running" and st["disabled_short"] and not st["disabled_with_reason"] and st["run_status"] == "cancelled" and z2st.get("status") == "SUSPENDED" and st["stop_to_cancelled_s"] < 60, {"subagent": ws, "stop": {k: st[k] for k in ("stop_to_cancelled_s", "run_status", "state")}, "wf": z2st})
        add("U2b-local", dlg is not None and dlg["disabled_empty"] and "otázky" in dlg["questions"].lower() and h1["interrupt"] is not None, {"dialog": dlg})
        # U-2 lokálně (falešný Governance MCP ve fixture): stránky firmy, autonomie, stop tenanta, report + export
        g.close(); g = Gui(base + "/gui/", shots=shots).open(); g.login("platform-admin", "platform-admin")
        pages = {"firma": g.page_rows("firma", ["roles-table", "tenants-table"]), "registr": g.page_rows("registr", ["agents-table", "events-table"]), "finops": g.page_rows("finops", ["finops-tenants", "finops-zakazky"]), "audit": g.page_rows("audit", ["approvals-table"])}
        add("U2a-local", pages["firma"]["roles-table"] == 5 and pages["firma"]["tenants-table"] == 3 and isinstance(pages["registr"]["agents-table"], int) and pages["audit"]["approvals-table"] >= 4, pages)
        r1 = g.autonomy("vyvojar", "beta", "A1", "Zkouška posunu bez podmínek – odmítnout."); r2 = g.autonomy("account", "acme", "A1", "Account má přes 10 běhů – posun na A1.")
        add("U2c-local", not r1["ok"] and r2["ok"], {"beta": r1, "acme": r2})
        st2 = g.tenant_stop("beta", "Zákazník beta pozastavil spolupráci – stop tenanta."); rs2 = g.tenant_stop("beta", "Beta zpět do provozu.", resume=True)
        add("U2d-local", st2["ok"] and st2["disabled_empty"] and rs2["ok"], {"stop": st2, "resume": rs2})
        rp = g.report(); add("U2e-local", rp["gaps"] >= 1 and rp["export_lines"] >= 1 and not any("T15:klasifikace" in r["missing"] for r in rp["rows"] if r["id"] == z1), {k: rp[k] for k in ("gaps", "export_lines")})
        # K-1 lokálně (P3-4): klasifikační brána, čl. 50 kanály, SLA
        g.close(); g = Gui(base + "/gui/", shots=shots).open(); g.login("adam", "adam")
        ch = httpx.get(f"{base}/channels/_debug/messages", timeout=10).json()["messages"]; mine = [m for m in ch if m.get("zakazka") == z1]
        add("K1d-local", fin["acts"]["channel"] >= 2 and any(m["channel"] == "email" and "AI agent" in m["body"] and m.get("generated_by", {}).get("generated_by") == "ai-agent:account" for m in mine) and any(m["channel"] == "ticket" and "AI agent" in m["body"] and (m.get("generated_by") or {}).get("generated_by") == "ai-agent:sre" for m in mine), {"channel_acts": fin["acts"]["channel"], "messages": [(m["channel"], m["body"][:60], (m.get("generated_by") or {}).get("generated_by")) for m in mine]})
        z3 = f"U1-{tag}-hr"; g.create_thread(z3, "Agent bude přidělovat úkoly lidem v týmu.", klasifikace={"K2": True}); pr3 = g.wait_profile(60)
        auto = httpx.post(f"{base}/agui/gov/autonomy", headers={"Authorization": f"Bearer {g.token}"}, json={"role": "account", "tenant": "acme", "level": "A1", "reason": "Zkouška – high-risk zamyká posun."}, timeout=10)
        st3 = g.stop("High-risk zakázka – lokální test, zastavit.")
        add("K1a-local", pr3["profile"] == "high-risk-III/4" and pr3["acts"]["klasifikace"] >= 1 and st3["run_status"] == "cancelled", {"profile": pr3["profile"], "autonomy_http": auto.status_code, "stop": st3["run_status"]})
        z4 = f"U1-{tag}-k1"; g.create_thread(z4, "Social scoring občanů.", klasifikace={"K1": True}); f4 = g.wait_finished(60)
        add("K1b-local", f4["state"]["stav"] == "Odmitnuto" and f4["state"]["profile"] == "odmitnout" and not f4["subagents"], {"state": f4["state"], "subagents": f4["subagents"]})
        z5 = f"U1-{tag}-api"; httpx.post(f"{base}/zakazky", json={"id": z5, "poptavka": "Zakázka z interního API bez dotazníku.", "tenant": "acme"}, timeout=10); ot5 = g.open_thread(z5); w5 = g.wait_any_interrupt(60)
        c5 = g.classify({"K4": True}, "Zákazník je obecní úřad."); h1a = g.wait_interrupt("H1a", 60); d1a = g.decide("Stanovisko právníka: veřejná správa mimo přílohu III – pokračovat jako high-risk do doplnění smlouvy.")
        pr5 = g.wait_profile(30); st5 = g.stop("Lokální test – zastavit po stanovisku.")
        add("K1c-local", w5.get("kind") == "klasifikace" and c5["questions_shown"] == 6 and h1a["interrupt"] and h1a["interrupt"].startswith("hitl:H1a:") and d1a["new_run"] and pr5["profile"] == "nejasne", {"first_interrupt": w5.get("kind"), "h1a": h1a["interrupt"], "profile": pr5["profile"], "stop": st5["run_status"]})
        z6 = f"U1-{tag}-sla"; httpx.post(f"{base}/zakazky", json={"id": z6, "poptavka": "Zakázka s krátkým SLA H1.", "tenant": "acme", "klasifikace": KLAS_NO, "sla": {"H1": 3}}, timeout=10); g.open_thread(z6)
        if g.wait_any_interrupt(60).get("kind") == "dialog": g.answer_dialog("Soubor do zakazky/<id>/NOTES.md; rozpočet výchozí.")
        h6 = g.wait_interrupt("H1", 60); sla6 = g.wait_sla(30); d6 = g.decide("SLA překročeno, ale zadání je v pořádku – schvaluji."); ws6 = g.wait_subagent("architekt", 30); g.stop("Lokální test SLA – zastavit.")
        add("K1f-local", h6["interrupt"] and sla6["sla_text"] and "H1" in sla6["sla_text"] and sla6["interrupt"] == h6["interrupt"] and d6["new_run"] and ws6["status"] == "running", {"sla": sla6, "after_decide": ws6})
    finally:
        g.close()
    n = sum(1 for c in checks if c["status"] == "FAIL"); print(f"== U-1 lokálně: {len(checks) - n}/{len(checks)} PASS; console: {g.log[:5]}")
    return checks


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--local", default="http://127.0.0.1:8010"); ap.add_argument("--shots", default="")
    a = ap.parse_args()
    cs = run_local(a.local, Path(a.shots) if a.shots else None)
    raise SystemExit(1 if any(c["status"] == "FAIL" for c in cs) else 0)
