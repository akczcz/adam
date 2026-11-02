"""
record.py – natočí průlet řídicím pultem firmy (GUI nad AKS přes kubectl port-forward) podle tools/promo/scenes.py.

Výstup (--out, výchozí tools/promo/out):
  video.webm          souvislá nahrávka prohlížeče 1920×1080 (Playwright record_video)
  scenes.json         časové značky scén {id: {t0, t1}} v sekundách od začátku nahrávky + co se podařilo
  cards/<id>.png      titulní karty (render z HTML, bez videa)

Zakázka pro video běží na mock modelu (žádná útrata), stejná cesta jako měření: založení z GUI s dotazníkem K1–K6 → Account (Kata pod) →
H1 (adam, s důvodem) → architekt → H2 → vývojář → PR → H4. Nahrává se do H4 (nebo do timeoutu), pak stránky Firma / FinOps / Governance / Audit
jako platform-admin. Nic se nepublikuje ven (mock GitHub). Po natočení se zakázka zastaví (úklid).

Spuštění (runner s kubectl kontextem clusteru, viz .github/workflows/promo.yml):
  python tools/promo/record.py --context aks-platform-dev-admin --out tools/promo/out
"""
from __future__ import annotations

import argparse
import html
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import httpx

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "harness_p1_k8s")); sys.path.insert(0, str(HERE))
from gui_checks import Gui   # noqa: E402  – stejný klient GUI jako měření (test id, čekání na interrupty, obnova po výpadku tunelu)
from scenes import SCENES   # noqa: E402

NS = "platform-data"
APP = "http://127.0.0.1:18010"
W, H = 1920, 1080

CARD_CSS = """
*{box-sizing:border-box;margin:0;padding:0} html,body{width:1920px;height:1080px;overflow:hidden;font-family:'DejaVu Sans','Segoe UI',system-ui,sans-serif;color:#e8eef7}
body{background:radial-gradient(1200px 700px at 20% 10%,#1b2a4a 0%,#0b1020 55%,#070a14 100%);position:relative}
.grid{position:absolute;inset:0;background-image:linear-gradient(rgba(120,160,255,.07) 1px,transparent 1px),linear-gradient(90deg,rgba(120,160,255,.07) 1px,transparent 1px);background-size:64px 64px}
.glow{position:absolute;width:900px;height:900px;border-radius:50%;filter:blur(120px);opacity:.35;background:#2f6bff;right:-250px;bottom:-350px}
.wrap{position:relative;padding:120px 140px}
.layer{display:inline-block;font-size:26px;letter-spacing:.18em;text-transform:uppercase;color:#8fb3ff;border:1px solid rgba(143,179,255,.5);border-radius:999px;padding:10px 26px;margin-bottom:34px}
h1{font-size:84px;line-height:1.05;font-weight:700;letter-spacing:-.01em;max-width:1500px}
.sub{font-size:36px;color:#9fb0c8;margin-top:26px;max-width:1500px;line-height:1.3}
ul{margin-top:70px;list-style:none;display:grid;gap:22px}
li{font-size:34px;line-height:1.3;padding-left:46px;position:relative;color:#dce6f5}
li::before{content:'';position:absolute;left:0;top:16px;width:18px;height:18px;border-radius:4px;background:linear-gradient(135deg,#6aa0ff,#38e8c6);box-shadow:0 0 18px rgba(106,160,255,.8)}
.foot{position:absolute;left:140px;bottom:70px;font-size:26px;color:#6f81a0;letter-spacing:.06em}
.foot b{color:#9fb0c8}
"""


def card_html(s):
    layer = f"<div class='layer'>vrstva {html.escape(s['layer'])}</div>" if s.get("layer") else "<div class='layer'>adam · platforma</div>"
    bullets = "".join(f"<li>{html.escape(b)}</li>" for b in s.get("bullets", []))
    return (f"<!doctype html><html><head><meta charset='utf-8'><style>{CARD_CSS}</style></head><body><div class='grid'></div><div class='glow'></div>"
            f"<div class='wrap'>{layer}<h1>{html.escape(s['title'])}</h1><div class='sub'>{html.escape(s.get('sub', ''))}</div><ul>{bullets}</ul></div>"
            f"<div class='foot'><b>Autonomní firma</b> · AKS · Dapr · agentgateway · Keycloak · SPIRE · OPA · OpenBao · ClickHouse · Kata</div></body></html>")


class PortForward:
    def __init__(self, kubectl, context, svc, local, remote, log_dir: Path):
        self.args = [kubectl, "--context", context, "-n", NS, "port-forward", f"svc/{svc}", f"{local}:{remote}"]; self.local = local; self.p = None
        self.log = open(log_dir / f"pf-{svc}.log", "a"); self.start()

    def start(self):
        import socket
        if self.p and self.p.poll() is None: self.p.terminate()
        self.p = subprocess.Popen(self.args, stdout=subprocess.DEVNULL, stderr=self.log)
        for _ in range(60):
            with socket.socket() as so:
                if so.connect_ex(("127.0.0.1", self.local)) == 0: return True
            time.sleep(0.5)
        return False

    def stop(self):
        if self.p: self.p.terminate()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--context", required=True); ap.add_argument("--kubectl", default="kubectl")
    ap.add_argument("--out", default=str(HERE / "out")); ap.add_argument("--tag", default=time.strftime("PROMO-%m%d%H%M"))
    ap.add_argument("--max-role-wait", type=int, default=1200, help="s – čekání na jednu roli (Kata pod + mock model)")
    a = ap.parse_args()
    out = Path(a.out); (out / "cards").mkdir(parents=True, exist_ok=True); (out / "shots").mkdir(exist_ok=True)
    pf = PortForward(a.kubectl, a.context, "zakazka", 18010, 8010, out)

    def http(method, url, **kw):
        for i in range(8):
            try: return httpx.request(method, url, **kw)
            except (httpx.ConnectError, httpx.RemoteProtocolError, httpx.ReadError, httpx.ReadTimeout):
                if i == 7: raise
                time.sleep(4); pf.start()

    health = http("GET", f"{APP}/health", timeout=20).status_code
    print(f"app health {health}")
    marks = {}; notes = {"tag": a.tag, "health": health}
    t_rec = [None]

    def now(): return round(time.time() - t_rec[0], 2)
    def mark(sid, **kv):
        m = marks.setdefault(sid, {}); m.update(kv); print(f"  scene {sid}: {m}", flush=True)
    def hold(sec): g.page.wait_for_timeout(int(sec * 1000))

    # --- karty (bez videa) -------------------------------------------------------------------------------------------------------
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=True, executable_path=os.environ.get("PW_CHROMIUM") or None); pg = b.new_page(viewport={"width": W, "height": H})
        for s in SCENES:
            if s["kind"] != "card": continue
            pg.set_content(card_html(s)); pg.wait_for_timeout(200); pg.screenshot(path=str(out / "cards" / f"{s['id']}.png"))
        b.close()
    print("cards ok")

    # --- nahrávka GUI ----------------------------------------------------------------------------------------------------------------
    g = Gui(f"{APP}/gui/", shots=out / "shots"); g.keepalive = lambda: http("GET", f"{APP}/health", timeout=10)
    g.pw = sync_playwright().start(); g.browser = g.pw.chromium.launch(headless=True, executable_path=os.environ.get("PW_CHROMIUM") or None)
    ctx = g.browser.new_context(viewport={"width": W, "height": H}, locale="cs-CZ", record_video_dir=str(out / "video"), record_video_size={"width": W, "height": H})
    g.page = ctx.new_page(); g.page.set_default_timeout(30_000); t_rec[0] = time.time(); g.page.goto(g.base)
    z = f"{a.tag}-demo"
    try:
        # 02 – pult: přihlášení adam, seznam zakázek
        mark("02-pult", t0=now()); g.login("adam", "adam"); g.threads_list(); hold(6); g.page.mouse.wheel(0, 400); hold(4); mark("02-pult", t1=now())
        # 03 – založení: poptávka, rozpočet, dotazník K1–K6 (vše „ne“ = standardní profil), odeslat; chvíli nechat běžet první run
        mark("03-zalozeni", t0=now())
        g.page.goto(g.base + "#/"); g.t("new-id").wait_for(); g.t("new-k-form").wait_for(timeout=30_000)
        g.t("new-id").type(z, delay=40); g.t("new-poptavka").type(f"Přidej do repozitáře platformy soubor zakazky/{z}/NOTES.md s krátkým shrnutím, jak zakázka prošla rolemi firmy.", delay=12)
        g.t("new-budget").type("2", delay=80); g.cur = z; hold(2.5); g.t("new-submit").click()
        g.page.wait_for_function("document.querySelector('[data-testid=run-protocol]') && document.querySelector('[data-testid=run-protocol]').textContent !== '?'", timeout=60_000)
        hold(6); mark("03-zalozeni", t1=now())
        # 05 – role Account běží jako subagent (Kata pod) – počkat na running, nechat 20 s záběru
        r = g.wait_subagent("account", timeout_s=a.max_role_wait); notes["account"] = r
        mark("05-role", t0=now()); hold(20); mark("05-role", t1=now())
        # 07 – H1 (nebo napřed otázky Account): interrupt v GUI, důvod, schválit
        w = g.wait_any_interrupt(timeout_s=a.max_role_wait); notes["first_interrupt"] = {k: w.get(k) for k in ("kind", "bod", "waited_s")}
        if w.get("kind") == "dialog":
            mark("07-h1", t0=now()); hold(4); g.answer_dialog("Ano, stačí jeden soubor NOTES.md v adresáři zakázky, bez dalších závislostí."); hold(3)
            w = g.wait_any_interrupt(timeout_s=a.max_role_wait)
        if "07-h1" not in marks: mark("07-h1", t0=now())
        if w.get("bod") == "H1":
            hold(5); g.t("approve-reason").type("Zadání odpovídá poptávce, rozsah je jeden soubor – schvaluji vstup zakázky.", delay=14); hold(1.5); g.t("approve-submit").click(); hold(6)
        mark("07-h1", t1=now())
        # 09 – architekt → H2 → vývojář → PR → H4 (dle času); nahrávat průběžně, značky od startu architekta
        mark("09-navrh-pr", t0=now())
        r2 = g.wait_subagent("architekt", timeout_s=a.max_role_wait); notes["architekt"] = r2; hold(12)
        w2 = g.wait_interrupt("H2", timeout_s=a.max_role_wait); notes["h2"] = {k: w2.get(k) for k in ("waited_s", "interrupt")}
        if (w2.get("interrupt") or "").startswith("hitl:H2:"): hold(3); g.decide("Návrh je přiměřený rozsahu zakázky – schvaluji.", "approve"); hold(5)
        r3 = g.wait_subagent("vyvojar", timeout_s=a.max_role_wait); notes["vyvojar"] = r3; hold(12)
        w4 = g.wait_interrupt("H4", timeout_s=a.max_role_wait); notes["h4"] = {k: w4.get(k) for k in ("waited_s", "interrupt")}
        if (w4.get("interrupt") or "").startswith("hitl:H4:"): hold(6); g.page.mouse.wheel(0, 600); hold(5)
        mark("09-navrh-pr", t1=now())
        # 10–12 – Firma jako platform-admin: Firma (verze, tenanti, autonomie), FinOps, Governance, Audit
        g.relogin_as("platform-admin", "platform-admin")
        mark("10-firma", t0=now()); g.page.goto(g.base + "#/firma"); g.page.wait_for_function("document.querySelector('[data-testid=wf-versions]')", timeout=60_000); hold(7); g.page.mouse.wheel(0, 500); hold(5); g.page.mouse.wheel(0, 600); hold(5); mark("10-firma", t1=now())
        mark("11-finops", t0=now()); g.page_rows("finops", ["finops-tenants", "finops-ledger"], timeout_s=90); hold(7); g.page.mouse.wheel(0, 700); hold(6); mark("11-finops", t1=now())
        mark("12-governance", t0=now()); g.page_rows("governance", ["report-table"], timeout_s=90); hold(7); g.page.mouse.wheel(0, 700); hold(4)
        g.page.goto(g.base + "#/audit"); g.page.wait_for_function("document.querySelector('[data-testid=approvals-table]') || document.querySelector('[data-testid=approvals-table-empty]')", timeout=60_000); hold(6); mark("12-governance", t1=now())
    except Exception as e:
        notes["error"] = f"{type(e).__name__}: {str(e)[:300]}"; print("CHYBA:", notes["error"], flush=True)
        for sid in list(marks):
            if "t1" not in marks[sid]: marks[sid]["t1"] = now()
    finally:
        try: g.shot("final")
        except Exception: pass
        video_path = None
        try:
            video_path = g.page.video.path() if g.page and g.page.video else None
            ctx.close(); g.browser.close(); g.pw.stop()
        except Exception as e: notes["close_error"] = f"{type(e).__name__}: {str(e)[:200]}"
        if video_path and Path(video_path).exists(): Path(video_path).replace(out / "video.webm")
        try: notes["stop"] = http("POST", f"{APP}/zakazky/{z}/stop", json={"by": "harness", "reason": "promo: úklid po natáčení"}, timeout=60).json()   # zakázka dál neběží (pody rolí končí)
        except Exception as e: notes["stop"] = f"{type(e).__name__}: {str(e)[:120]}"
        pf.stop()
    (out / "scenes.json").write_text(json.dumps({"marks": marks, "notes": notes, "zakazka": z, "recorded_s": now() if t_rec[0] else None}, ensure_ascii=False, indent=1))
    print(json.dumps({"marks": marks, "notes": {k: v for k, v in notes.items() if k in ("error", "stop", "health")}}, ensure_ascii=False))


if __name__ == "__main__":
    main()
