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


REBASE = None     # P4-4: harness dodá funkci → aktuální základ URL GUI (quick tunnel Cloudflare mění hostname s každým restartem podu aplikace)
_ACTIVE: list = []   # otevřené instance (běh 3 P4-4: neuzavřený Playwright po výjimce v M1 → L1c „Sync API inside the asyncio loop“)


class Gui:
    def __init__(self, base_url: str, *, headless=True, chromium: str | None = None, shots: Path | None = None, slow_ms=0):
        self.base, self.headless, self.chromium, self.shots, self.slow = base_url.rstrip("/") + "/", headless, chromium or os.environ.get("PW_CHROMIUM"), shots, slow_ms
        self.pw = self.browser = self.page = None; self.log = []; self.keepalive = None   # harness dodá obnovu port-forwardu (fetch z prohlížeče nemá retry)
        self.cur = None; self._err_t = None; self.recoveries = []; self.rebase = REBASE   # otevřený thread + obnova pohledu po vyčerpání retry GUI (E11 3. běh: „error Failed to fetch“ 50 min)

    def open(self):
        from playwright.sync_api import sync_playwright
        for g in list(_ACTIVE):   # zapomenutá instance z předchozího toku (výjimka před close) by zablokovala nový start sync API
            try: g.close()
            except Exception: pass
        self.pw = sync_playwright().start(); _ACTIVE.append(self)
        self.browser = self.pw.chromium.launch(headless=self.headless, executable_path=self.chromium or None, slow_mo=self.slow)
        self.page = self.browser.new_context(viewport={"width": 1280, "height": 900}, locale="cs-CZ").new_page()
        self.page.set_default_timeout(30_000)
        self.page.on("console", lambda m: self.log.append(f"[{m.type}] {m.text[:200]}") if m.type in ("error", "warning") else None)
        self.goto("")
        return self

    def close(self):
        if self in _ACTIVE: _ACTIVE.remove(self)
        try:
            if self.browser: self.browser.close()
        finally:
            if self.pw: self.pw.stop()
            self.pw = self.browser = None

    def _nav(self, fn, where, frag=None):
        """Navigace s obnovou základu URL: quick tunnel Cloudflare má po restartu podu aplikace nový hostname (P4-4 běh 3: ERR_NAME_NOT_RESOLVED
        v E13/M1/L1) → při síťové chybě prohlížeče zjistit novou URL (rebase) a jít na tutéž stránku (hash) znovu."""
        try:
            resp = fn()
            if self.rebase and resp is not None and getattr(resp, "status", 0) >= 500: raise RuntimeError(f"net::HTTP {resp.status} (chybová stránka Cloudflare – tunel starého podu)")   # běh 5 P4-4: mrtvý quick tunnel = 502/530 stránka, ne síťová chyba
            return resp
        except Exception as e:
            if not self.rebase or not re.search(r"ERR_NAME_NOT_RESOLVED|ERR_CONNECTION|ERR_ADDRESS|ERR_TUNNEL|net::", str(e)): raise
            nb = self.rebase()
            if not nb: raise
            if frag is None: old = self.page.url; frag = ("#" + old.split("#", 1)[1]) if "#" in old else ""
            self.base = nb.rstrip("/") + "/"; self.recoveries.append({"t": time.strftime("%H:%M:%S"), "thread": self.cur, "error": str(e)[:100], "where": f"rebase:{where}", "base": self.base})
            self.page.wait_for_timeout(700)   # prohlížeč ještě dokončuje navigaci na chybovou stránku – okamžité goto by přerušila
            for i in range(2):
                try: self.page.goto(self.base + frag); return None
                except Exception as e2:
                    if i or "interrupted" not in str(e2): raise
                    self.page.wait_for_timeout(1000)

    def goto(self, path):
        return self._nav(lambda: self.page.goto(self.base + path), f"goto:{path[:20]}", frag=path)

    def rebase_now(self, where="explicit"):
        """Po známém restartu podu aplikace (E13c) nečekat na chybu: tunel ukončovaného podu ještě chvíli odpovídá (běh 6 P4-4: login přes
        umírající pod → timeout) → rovnou zjistit aktuální URL a přejít na tutéž stránku pod ní."""
        if not self.rebase: return False
        nb = self.rebase()
        if not nb or nb.rstrip("/") + "/" == self.base: return False
        old = self.page.url; self.base = nb.rstrip("/") + "/"
        self.recoveries.append({"t": time.strftime("%H:%M:%S"), "thread": self.cur, "where": f"rebase:{where}", "base": self.base})
        self.page.goto(self.base + (("#" + old.split("#", 1)[1]) if "#" in old else "")); return True

    def reload(self):
        return self._nav(lambda: self.page.reload(), "reload")

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
        self.rebase_now("relogin"); self.page.evaluate("sessionStorage.clear()"); self.reload(); self.t("login-user").wait_for()
        return self.login(*self.creds)

    @property
    def token(self):
        """Aktuální access token z prohlížeče (GUI ho obnovuje refresh tokenem – 15 min lifespan Keycloaku zakázka v Kata podech přežije)."""
        return self.page.evaluate("sessionStorage.getItem('agui_token')")

    # --- seznam a založení ----------------------------------------------------------------------------------------------
    def _goto_wait(self, path, js, timeout_s=30, where="goto"):
        """Navigace + čekání na prvek; po delší pasivní fázi bez provozu (dotazy do DB, sondy) bývá tunel port-forward mrtvý a fetch z GUI nic nevrátí
        (P4-3 běh 3: threads_list v T1e timeout 30 s) → keepalive před navigací a při timeoutu jednou keepalive + reload + delší čekání."""
        if self.keepalive:
            try: self.keepalive()
            except Exception: pass
        self.goto(path); self.page.wait_for_timeout(300)
        try: self.page.wait_for_function(js, timeout=timeout_s * 1000)
        except Exception as e:
            self.recoveries.append({"t": time.strftime("%H:%M:%S"), "thread": self.cur, "error": f"{type(e).__name__}", "where": where})
            if self.keepalive:
                try: self.keepalive()
                except Exception: pass
            self.reload(); self.page.wait_for_timeout(500); self.page.wait_for_function(js, timeout=2 * timeout_s * 1000)

    def threads_list(self):
        self._goto_wait("#/", "document.querySelector('[data-testid=threads-table]') || document.querySelector('[data-testid=threads-empty]')", where="threads_list")
        rows = self.page.locator("[data-testid^=thread-row-]")
        out = []
        for i in range(rows.count()):
            r = rows.nth(i); out.append({"id": r.get_attribute("data-testid")[len("thread-row-"):], "cells": [c.strip() for c in r.locator("td").all_inner_texts()]})
        self.shot("threads")
        return out

    def create_thread(self, zid, poptavka, budget=None, klasifikace=None, live=False):
        """Nová zakázka z GUI: poptávka + dotazník K1–K6 (P3-4; výchozí vše „ne“) → první run s forwardedProps.klasifikace; live (P4-2) = ostrý běh."""
        self.goto("#/"); self.t("new-id").wait_for(); self.t("new-k-form").wait_for(timeout=30_000)
        self.t("new-id").fill(zid); self.t("new-poptavka").fill(poptavka); self.cur = zid
        if budget is not None: self.t("new-budget").fill(str(budget))
        if live: self.t("new-live").check()
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
        for attempt in range(2):
            if self.page.url.endswith(f"#/t/{zid}"): self.goto("#/"); self.page.wait_for_timeout(300)
            self.goto(f"#/t/{zid}"); self.cur = zid
            self.page.wait_for_function("document.querySelector('[data-testid=run-status]') && !['idle','connecting'].includes(document.querySelector('[data-testid=run-status]').textContent)", timeout=60_000)
            st, err = self.t("run-status").inner_text(), (self.t("run-error").inner_text() if self.t("run-error").count() else None)
            if st != "error" or re.match(r"^\d{3}", (err or "").strip()) or not self.keepalive or attempt: break
            try: self.keepalive()   # „Failed to fetch“ hned při otevření = spadlý port-forward (2. běh P4-1, E13b) → obnovit a otevřít znovu
            except Exception: pass
            self.recoveries.append({"t": time.strftime("%H:%M:%S"), "thread": zid, "error": (err or "")[:120], "where": "open_thread"})
        return {"status": st, "error": err}

    def relogin_as(self, user, pw):
        """Odhlášení a přihlášení jiným člověkem: napřed obnova port-forwardu (keepalive) a návrat z případné chybové stránky prohlížeče
        (po ERR_CONNECTION_REFUSED nejde číst sessionStorage – 2. běh P4-1, E13b/E13c), pak sessionStorage pryč → login."""
        if self.keepalive:
            try: self.keepalive()
            except Exception: pass
        self.rebase_now("relogin_as"); self.goto("#/")
        try: self.page.evaluate("sessionStorage.clear()")
        except Exception: pass
        self.reload(); self.t("login-user").wait_for()
        return self.login(user, pw)

    # --- průběh ------------------------------------------------------------------------------------------------------------
    def snapshot(self):
        subs = [{"name": s.get_attribute("data-testid")[len("subagent-"):], "status": s.get_attribute("data-status")} for s in self.page.locator("[data-testid^=subagent-]").all() if s.get_attribute("data-status") is not None]   # jen řádky subagentů (mají data-status), ne vnořené prvky s podobným prefixem
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
        if rs == "error" and self.rebase and re.match(r"^(502|503|530)", err.strip()) and self.cur:   # 5xx z Cloudflare = tunel podu, který už neběží (běh 5 P4-4 E13b) → nová URL a thread znovu
            nb = self.rebase()
            if nb and nb.rstrip("/") + "/" != self.base:
                self.base = nb.rstrip("/") + "/"; self.recoveries.append({"t": time.strftime("%H:%M:%S"), "thread": self.cur, "error": err[:60], "where": "rebase:recover", "base": self.base})
                try: self.open_thread(self.cur); self._err_t = None; return True
                except Exception as e: self.recoveries[-1]["reopen_failed"] = type(e).__name__
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

    def decide(self, reason, decision="approve", budget=None, _retry=True):
        """Tlačítka jsou bez důvodu (≥ 10 znaků) zakázaná – důkaz T6 v GUI; pak klik a čekání na nový run. budget (P3-6 E3): nový strop u bodu rozpocet.
        P4-2 běhy 5–6 (O3): po minutách bez provozu přes port-forward (sonda E5) tunel na AKS umřel → klik = „Failed to fetch“, nový run nepřišel;
        proto napřed keepalive (obnoví port-forward) a při síťové chybě (ne HTTP kód) jednou znovu otevřít thread a rozhodnout znovu."""
        if self.keepalive:
            try: self.keepalive()
            except Exception: pass
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
            if _retry and self.cur and err and not re.match(r"^\d{3}", err.strip()):   # síťový výpadek (ne odpověď serveru) → obnovit tunel a pohled, rozhodnout znovu
                self.recoveries.append({"t": time.strftime("%H:%M:%S"), "thread": self.cur, "error": err[:120], "where": "decide"})
                if self.keepalive:
                    try: self.keepalive()
                    except Exception: pass
                self.open_thread(self.cur); self.t("approve-submit" if decision == "approve" else "reject-submit").wait_for(timeout=60_000)
                return {**self.decide(reason, decision, budget, _retry=False), "retried_after": err[:120]}
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
        t0 = time.time(); tk = t0
        while time.time() - t0 < timeout_s:
            if self.t("state-profile").count(): break
            rs = self.t("run-status").inner_text() if self.t("run-status").count() else ""
            if rs in ("finished", "cancelled"): break
            self.page.wait_for_timeout(1000); tk = self._tunnel_tick(tk)
        self.shot("profile")
        return {"waited_s": round(time.time() - t0, 1), "profile": self.t("state-profile").inner_text().strip() if self.t("state-profile").count() else None, **self.snapshot()}

    def wait_sla(self, timeout_s=120):
        """Čeká na indikaci překročení SLA (state-sla / aktivita sla) – zakázka přitom dál čeká na rozhodnutí."""
        t0 = time.time(); tk = t0
        while time.time() - t0 < timeout_s:
            if self.t("state-sla").count() or self.t("act-sla").count(): break
            self.page.wait_for_timeout(1000); tk = self._tunnel_tick(tk)   # P4-3 běh 2 (K1f): 90 s jen čtení DOM → tunel port-forward umřel, stav z GUI se neobnovil (nález 8 P4-2)
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
        out = {}
        try: self._goto_wait(f"#/{page}", f"document.querySelector('[data-testid={table_ids[0]}]') || document.querySelector('[data-testid={table_ids[0]}-empty]')", timeout_s=timeout_s, where=f"page_rows:{page}")
        except Exception: pass   # chybu zachytí smyčka níže (per tabulka)
        for tid in table_ids:
            try:
                self.page.wait_for_function(f"document.querySelector('[data-testid={tid}]') || document.querySelector('[data-testid={tid}-empty]')", timeout=timeout_s * 1000)
                out[tid] = int(self.t(tid).get_attribute("data-rows")) if self.t(tid).count() else 0
            except Exception as e:
                out[tid] = f"err:{type(e).__name__}"
                try: out.setdefault("page_errors", sorted({t.strip()[:160] for t in self.page.locator(".err").all_inner_texts() if t.strip()}))   # proč tabulka chybí (chyba nástroje / fetch)
                except Exception: pass
        self.shot(f"page-{page}")
        return out

    # --- P3-6 E13: zaseknutá zakázka (Dapr STALLED – chybí verze orchestrátoru) -----------------------------------------------------
    def thread_status(self, zid):
        """Řádek zakázky v seznamu: text badge stavu + status workflow (data-status) – STALLED má badge „zaseknuto – chybí verze orchestrátoru“."""
        self.goto("#/"); self.page.wait_for_timeout(300)
        self.page.wait_for_function("document.querySelector('[data-testid=threads-table]') || document.querySelector('[data-testid=threads-empty]')")
        b = self.page.locator(f"[data-testid=thread-row-{zid}] [data-testid=thread-stav]")
        self.shot(f"threads-{zid}")
        return {"found": b.count() == 1, "stav": b.inner_text().strip() if b.count() else None, "status": b.get_attribute("data-status") if b.count() else None, "class": b.get_attribute("class") if b.count() else None}

    def wait_run_status(self, want, timeout_s=90):
        """Čeká, až run-status je v `want` (např. stalled/finished); mezitím obnova pohledu po síťovém výpadku jako wait_interrupt."""
        t0 = time.time(); rs = ""
        while time.time() - t0 < timeout_s:
            rs = self.t("run-status").inner_text() if self.t("run-status").count() else ""
            if rs in want: break
            self._recover(rs); self.page.wait_for_timeout(1500)
        return {"waited_s": round(time.time() - t0, 1), "run_status": rs}

    def stalled_view(self, zid, timeout_s=90):
        """Detail zaseknuté zakázky: run skončí stavem `stalled`, karta stalled-notice nese verzi orchestrátoru a nápovědu, stav „zaseknuto…“."""
        self.open_thread(zid); w = self.wait_run_status(("stalled", "finished", "cancelled"), timeout_s)
        n = self.t("stalled-notice")
        try: n.wait_for(timeout=10_000)
        except Exception: pass
        self.shot(f"stalled-{zid}")
        return {**w, "notice": n.inner_text()[:300] if n.count() else None, "notice_wf_version": n.get_attribute("data-wf-version") if n.count() else None,
                "state_wf_version": self.t("state-wf-version").inner_text().strip() if self.t("state-wf-version").count() else None, **{k: v for k, v in self.snapshot().items() if k in ("state", "error", "interrupt")}}

    # --- P4-1 mandát (subject pro exchange rolí) -----------------------------------------------------------------------------------
    def mandat_view(self):
        """Mandát v detailu: badge state-mandat (data-expired/sub/source/expires-in), karta mandat-card, per role „jménem“ (mandat-role-<role>; 2. běh P4-1:
        prefix subagent-mandat-* se pletl do výčtu subagentů U1b → přejmenováno)."""
        m, c = self.t("state-mandat"), self.t("mandat-card")
        roles = {x.get_attribute("data-testid")[len("mandat-role-"):]: (x.get_attribute("data-sub") or None) for x in self.page.locator("[data-testid^=mandat-role-]").all()}
        ei = m.get_attribute("data-expires-in") if m.count() else None
        return {"present": m.count() == 1, "expired": (m.get_attribute("data-expired") == "true") if m.count() else None, "sub": (m.get_attribute("data-sub") or None) if m.count() else None,
                "source": (m.get_attribute("data-source") or None) if m.count() else None, "expires_in_s": int(ei) if ei not in (None, "") else None, "text": m.inner_text().strip() if m.count() else None,
                "card": c.count() == 1, "card_expired": (c.get_attribute("data-expired") == "true") if c.count() else None, "card_text": c.inner_text()[:200] if c.count() else None, "roles": roles}

    def _tunnel_tick(self, last, every_s=10):
        """Pasivní čekání na GUI: tunel port-forward na AKS se v klidu rozpadne (běh 8 p4-2, M1c: GUI po ~20 s přestalo stav číst, fetch z prohlížeče
        nemá retry) → každých `every_s` keepalive harnessu (GET /health přes helper `http`, který forwardy obnoví); GUI se pak samo chytí."""
        if self.keepalive and time.time() - last >= every_s:
            try: self.keepalive()
            except Exception: pass
            return time.time()
        return last

    def wait_mandat(self, pred, timeout_s=90):
        """Čeká, až mandat_view() splní pred (GUI čte stav každých 30 s = keepalive); mezitím drží tunel (_tunnel_tick)."""
        t0 = time.time(); m = {}; tk = t0
        while time.time() - t0 < timeout_s:
            m = self.mandat_view()
            if pred(m): break
            self.page.wait_for_timeout(2000); tk = self._tunnel_tick(tk)
        return {**m, "waited_s": round(time.time() - t0, 1)}

    def mandat_renew(self):
        """Kliknutí „Obnovit mandát“ → zpráva mandat-msg."""
        self.t("mandat-renew").click(); self.t("mandat-msg").wait_for(timeout=20_000); self.shot("mandat-renew")
        return {"msg": self.t("mandat-msg").inner_text().strip(), **self.mandat_view()}

    def wf_versions_card(self, timeout_s=60):
        """Firma (tenant platform): karta verzí orchestrátoru – souhrn (zaseknuté, chybějící verze) a řádky per verze."""
        self.goto("#/firma"); self.page.wait_for_timeout(500); out = {"rows": {}}
        try:
            self.page.wait_for_function("document.querySelector('[data-testid=wf-versions]')", timeout=timeout_s * 1000)
            s = self.t("wf-summary"); out["stalled"] = int(s.get_attribute("data-stalled") or 0); out["missing"] = [m for m in (s.get_attribute("data-missing") or "").split(",") if m]
            out["missing_text"] = self.t("wf-missing").inner_text()[:200] if self.t("wf-missing").count() else None
            for r in self.page.locator("[data-testid^=wf-version-]").all():
                out["rows"][r.get_attribute("data-testid")[len("wf-version-"):]] = {"registered": r.get_attribute("data-registered") == "true", "stalled": int(r.get_attribute("data-stalled") or 0), "missing": r.get_attribute("data-missing") == "true", "cells": [c.strip()[:120] for c in r.locator("td").all_inner_texts()]}
        except Exception as e:
            out["error"] = f"{type(e).__name__}"
            try: out["page_errors"] = sorted({t.strip()[:160] for t in self.page.locator(".err").all_inner_texts() if t.strip()})
            except Exception: pass
        self.shot("wf-versions")
        return out

    def autonomy(self, role, tenant, level, reason):
        self.goto("#/firma"); self.t("auto-role").wait_for()
        self.t("auto-role").fill(role); self.t("auto-tenant").fill(tenant); self.t("auto-level").select_option(level); self.t("auto-reason").fill(reason)
        seq0 = self.t("auto-result").get_attribute("data-seq") if self.t("auto-result").count() else None
        self.t("auto-submit").click()
        try: self.page.wait_for_function(f"(() => {{ const e = document.querySelector('[data-testid=auto-result]'); return e && e.getAttribute('data-seq') !== {json.dumps(seq0)}; }})()", timeout=60_000)   # nový výsledek, ne starý z předchozího odeslání
        except Exception:   # P3-5 nález: spadlý port-forward → fetch z GUI bez odpovědi; obnovit tunel (keepalive harnessu), znovu odeslat
            if self.keepalive: self.keepalive()
            self.reload(); self.t("auto-role").wait_for(); self.t("auto-role").fill(role); self.t("auto-tenant").fill(tenant); self.t("auto-level").select_option(level); self.t("auto-reason").fill(reason)
            seq0 = self.t("auto-result").get_attribute("data-seq") if self.t("auto-result").count() else None; self.t("auto-submit").click()
            self.page.wait_for_function(f"(() => {{ const e = document.querySelector('[data-testid=auto-result]'); return e && e.getAttribute('data-seq') !== {json.dumps(seq0)}; }})()", timeout=90_000)
        self.shot(f"autonomy-{role}-{tenant}-{level}")
        return {"ok": self.t("auto-result").get_attribute("data-ok") == "true", "text": self.t("auto-result").inner_text()[:400]}

    def tenant_stop(self, tenant, reason, resume=False, _retry=True):
        self.goto("#/firma"); self.t("tstop-tenant").wait_for()
        self.t("tstop-tenant").fill(tenant); self.t("tstop-reason").fill(""); d0 = self.t("tstop-submit").is_disabled(); self.t("tstop-reason").fill(reason)
        seq0 = self.t("tstop-result").get_attribute("data-seq") if self.t("tstop-result").count() else None
        self.t("tresume-submit" if resume else "tstop-submit").click()
        try: self.page.wait_for_function(f"(() => {{ const e = document.querySelector('[data-testid=tstop-result]'); return e && e.getAttribute('data-seq') !== {json.dumps(seq0)}; }})()", timeout=120_000)
        except Exception:
            if self.keepalive: self.keepalive()
            self.reload(); self.t("tstop-tenant").wait_for(timeout=120_000); self.t("tstop-tenant").fill(tenant); self.t("tstop-reason").fill(reason)   # P4-2 běh 4: po reloadu formulář do 30 s nebyl (aplikace dušená dumpem ledgeru) → shodilo celý běh
            seq0 = self.t("tstop-result").get_attribute("data-seq") if self.t("tstop-result").count() else None; self.t("tresume-submit" if resume else "tstop-submit").click()
            self.page.wait_for_function(f"(() => {{ const e = document.querySelector('[data-testid=tstop-result]'); return e && e.getAttribute('data-seq') !== {json.dumps(seq0)}; }})()", timeout=120_000)
        self.shot(f"tenant-{'resume' if resume else 'stop'}-{tenant}")
        out = {"disabled_empty": d0, "ok": self.t("tstop-result").get_attribute("data-ok") == "true", "text": self.t("tstop-result").inner_text()[:400]}
        if not out["ok"] and "(401)" in out["text"] and _retry and getattr(self, "creds", None):   # 1. běh E10: GUI bez tokenu po neúspěšném refreshi → přihlásit znovu a jednou opakovat
            self.relogin(); return {**self.tenant_stop(tenant, reason, resume, _retry=False), "relogin_after": out["text"]}
        m = re.search(r"\((\d{3})\)", out["text"]); code = int(m.group(1)) if m else None
        if not out["ok"] and _retry and (code is None or code >= 500 or code == 429):   # 2. běh P4-5: resume z GUI přes tunel selhal rychlou HTTP chybou → přechodná 5xx tunelu / 429 refreshe → jednou opakovat (po 5xx nejdřív rebase)
            time.sleep(65 if code == 429 else 5)
            if code is None or code >= 500: self.rebase_now("tenant_stop")
            return {**self.tenant_stop(tenant, reason, resume, _retry=False), "retry_after": out["text"]}
        return out

    def report(self):
        self.goto("#/governance"); self.t("report-summary").wait_for(timeout=60_000)
        rows = self.page.locator("[data-testid^=report-][data-missing]")
        out = [{"id": r.get_attribute("data-testid")[len("report-"):], "missing": (r.get_attribute("data-missing") or "").split(",") if r.get_attribute("data-missing") else []} for r in rows.all()]
        self.t("export-button").click(); self.t("export-lines").wait_for(timeout=60_000)
        self.shot("governance")
        return {"gaps": int(self.t("report-gaps").inner_text()), "rows": out, "export_lines": int(self.t("export-lines").get_attribute("data-lines")), "export_preview": self.t("export-preview").inner_text()[:2000]}

    def wait_finished(self, timeout_s=600, want=("finished",)):
        t0 = time.time(); tk = t0
        while time.time() - t0 < timeout_s:
            rs = self.t("run-status").inner_text() if self.t("run-status").count() else ""
            if rs in want or rs in ("error",): break
            self.page.wait_for_timeout(1500); tk = self._tunnel_tick(tk, 15)
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
