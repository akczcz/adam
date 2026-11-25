"""
gui_screenshots.py – důkaz redesignu GUI (brief gui-redesign-brief.md): screenshoty všech obrazovek v obou motivech (dark/light) a dvou šířkách
(desktop 1280 px, telefon 390 px) nad lokální fixture (gui_fixture.py, bez clusteru). Stavy zakázek připraví skutečnými AG-UI runy přes GUI
(Playwright, třída Gui z gui_checks.py): běžící stream, interrupt H2, interrupt rozpocet, Pozastaveno, Dokonceno, Odmitnuto; pak stránky firmy
jako platform-admin. Spuštění: cd gui && npm run build && PW_CHROMIUM=/opt/pw-browsers/chromium python ../tools/harness_p1_k8s/gui_screenshots.py
Výstup: gui/screenshots/<obrazovka>-<dark|light>-<desktop|mobile>.png (+ index.md).
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

import httpx

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from gui_checks import Gui, hpw   # noqa: E402

SCREENS = [   # (název souboru, route, selektor, čeho se dočkat)
    ("02-zakazky", "#/", "[data-testid=threads-table]"),
    ("03-karta-stream", "#/t/{run}", "[data-testid=subagent-architekt][data-status=running]"),
    ("04-karta-interrupt-h2", "#/t/{h2}", "[data-testid=interrupt][data-kind=approval]"),
    ("05-karta-interrupt-rozpocet", "#/t/{budget}", "[data-testid=budget-box]"),
    ("06-karta-pozastaveno", "#/t/{susp}", "[data-testid=resume-button]"),
    ("07-karta-dokonceno", "#/t/{done}", "[data-testid=state-stav]"),
]
ADMIN_SCREENS = [("08-firma", "#/firma", "[data-testid=wf-versions],[data-testid=roles-table]"), ("09-finops", "#/finops", "[data-testid=finops-tenants]"), ("10-governance", "#/governance", "[data-testid=report-table],[data-testid=report-table-empty]"), ("11-registr", "#/registr", "[data-testid=agents-table],[data-testid=agents-table-empty]"), ("12-audit", "#/audit", "[data-testid=approvals-table],[data-testid=approvals-table-empty]")]
VIEWPORTS = {"desktop": {"width": 1280, "height": 900}, "mobile": {"width": 390, "height": 844}}


def prepare(base, role_s):
    """Stavy zakázek skutečnými runy (dialog Account → H1 → …); vrací id a tokeny (adam, platform-admin)."""
    tag = time.strftime("%H%M%S"); ids = {k: f"Z-{tag}-{k}" for k in ("done", "susp", "h2", "budget", "run", "k1")}
    g = Gui(base + "/gui/").open(); tokens = {}
    try:
        g.login("adam", hpw("adam")); tokens["adam"] = g.token
        def dialog_h1(z, reason):
            if g.wait_any_interrupt(120).get("kind") == "dialog": g.answer_dialog("Soubor do zakazky/<id>/NOTES.md; rozpočet výchozí.")
            g.wait_interrupt("H1", 120); g.decide(reason)
        # Dokonceno
        g.create_thread(ids["done"], "Přidej do repa platformy soubor zakazky/<id>/NOTES.md s krátkou poznámkou (česky), kdo zakázku provedl a kdy.", 5)
        dialog_h1(ids["done"], "Zadání odpovídá poptávce, kritéria jsou měřitelná.")
        g.wait_interrupt("H2", 120); g.decide("Schvaluji variantu A – nejjednodušší a v rozpočtu; Vývojář zapíše NOTES.md podle zadání.")
        g.wait_interrupt("H4", 120); g.decide("Review bez vad, soubory odpovídají zadání – merge.")
        g.wait_interrupt("H5", 120); g.decide("Nasazení schváleno, rollback je v runbooku."); g.wait_finished(120)
        # Odmitnuto (K1)
        g.create_thread(ids["k1"], "Social scoring občanů podle chování na sociálních sítích.", 3, klasifikace={"K1": True}); g.wait_finished(60)
        # Pozastaveno (stop během Architekta)
        g.create_thread(ids["susp"], "Vytvoř Python modul slugify.py s funkcí slugify(text: str) -> str (malá písmena, bez diakritiky, pomlčky), testy a README.", 1)
        dialog_h1(ids["susp"], "Zadání v pořádku, pokračovat k návrhu."); g.wait_subagent("architekt", 60); g.stop("Zákazník pozastavil zakázku do vyjasnění rozpočtu.")
        # rozpočet (strop 0.01 USD → BUDGET_EXCEEDED před Vývojářem)
        g.create_thread(ids["budget"], "Nástroj, který převede CSV export z našeho systému na Markdown tabulku pro wiki (CLI, testy, README).", 0.01)
        dialog_h1(ids["budget"], "Zadání odpovídá poptávce; výstup musí zvládnout cp1250 i UTF-8.")
        g.wait_interrupt("H2", 120); g.decide("Schvaluji variantu A + C (stdlib + CLI). Exit kód ≠ 0 při chybném CSV."); g.wait_interrupt("rozpocet", 120)
        # čeká na H2
        g.create_thread(ids["h2"], "Nástroj, který převede CSV export z našeho systému na Markdown tabulku pro wiki (CLI, testy, README).", 10)
        dialog_h1(ids["h2"], "Zadání odpovídá poptávce; výstup musí zvládnout cp1250 i UTF-8."); g.wait_interrupt("H2", 120)
        g.close(); g = Gui(base + "/gui/").open(); g.login("platform-admin", hpw("platform-admin")); tokens["admin"] = g.token
        g.close(); g = Gui(base + "/gui/").open(); g.login("adam", hpw("adam")); tokens["adam"] = g.token
        # běžící stream (Architekt běží role_s sekund) – založit těsně před focením; focení streamu jde ve všech 4 variantách jako první
        g.create_thread(ids["run"], "Vytvoř Python modul slugify.py s funkcí slugify(text: str) -> str (malá písmena, bez diakritiky, pomlčky), testy a README.", 5, live=False)
        dialog_h1(ids["run"], "Zadání odpovídá poptávce, kritéria jsou měřitelná."); g.wait_subagent("architekt", 60)
    finally:
        g.close()
    return ids, tokens


def shoot(base, ids, tokens, out: Path, chromium):
    from playwright.sync_api import sync_playwright
    out.mkdir(parents=True, exist_ok=True); made = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, executable_path=chromium or None)
        def ctx(theme, size, token):
            c = browser.new_context(viewport=size, locale="cs-CZ", color_scheme=theme, device_scale_factor=1)
            c.add_init_script(f"try{{localStorage.setItem('gui_theme','{theme}');}}catch(e){{}}" + (f"sessionStorage.setItem('agui_token',{token!r});sessionStorage.setItem('agui_exp',String(Date.now()+800000));" if token else "sessionStorage.clear();"))
            return c
        # 1) běžící stream ve všech 4 variantách najednou (role běží jen role_s sekund): stránky otevřít, počkat na běžící roli, pak vyfotit
        run_name, run_route, run_wait = SCREENS[1]; pages = []
        for theme in ("dark", "light"):
            for vp, size in VIEWPORTS.items():
                c = ctx(theme, size, tokens["adam"]); p = c.new_page(); p.goto(base + "/gui/" + run_route.format(**ids)); pages.append((theme, vp, c, p))
        for theme, vp, c, p in pages:
            p.wait_for_selector(run_wait, timeout=60_000); p.wait_for_timeout(300); f = out / f"{run_name}-{theme}-{vp}.png"; p.screenshot(path=str(f), full_page=True); made.append(f.name); c.close()
        for theme in ("dark", "light"):
            for vp, size in VIEWPORTS.items():
                def snap(c, name, route, wait):
                    p = c.new_page(); p.goto(base + "/gui/" + route); p.wait_for_selector(wait, timeout=60_000); p.wait_for_timeout(600)
                    f = out / f"{name}-{theme}-{vp}.png"; p.screenshot(path=str(f), full_page=True); made.append(f.name); p.close()
                c = ctx(theme, size, None); p = c.new_page(); p.goto(base + "/gui/"); p.get_by_test_id("login-user").fill("adam"); p.get_by_test_id("login-pass").fill("spatne"); p.get_by_test_id("login-submit").click(); p.get_by_test_id("login-error").wait_for()
                f = out / f"01-prihlaseni-{theme}-{vp}.png"; p.screenshot(path=str(f), full_page=True); made.append(f.name); c.close()
                c = ctx(theme, size, tokens["adam"])
                for name, route, wait in SCREENS[:1] + SCREENS[2:]: snap(c, name, route.format(**ids), wait)
                c.close(); c = ctx(theme, size, tokens["admin"])
                for name, route, wait in ADMIN_SCREENS: snap(c, name, route, wait)
                c.close()
        browser.close()
    (out / "index.md").write_text("# Screenshoty GUI (fixture, " + time.strftime("%Y-%m-%d") + ")\n\n" + "\n".join(f"- `{n}`" for n in sorted(made)) + "\n", encoding="utf-8")
    return made


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--base", default="http://127.0.0.1:8010"); ap.add_argument("--out", default=str(HERE.parent.parent / "gui/screenshots")); ap.add_argument("--role-s", type=float, default=24.0, help="trvání role ve fixture (běžící stream musí vydržet focení 4 variant)")
    ap.add_argument("--no-fixture", action="store_true", help="nespouštět vlastní fixture (běží už na --base)"); ap.add_argument("--gui", default=str(HERE.parent.parent / "gui/dist"))
    a = ap.parse_args(); proc = None
    if not a.no_fixture:
        port = a.base.rsplit(":", 1)[-1]
        proc = subprocess.Popen([sys.executable, str(HERE / "gui_fixture.py"), "--port", port, "--gui", a.gui, "--role-s", str(a.role_s)], stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
        for _ in range(60):
            try: httpx.get(a.base + "/gui/", timeout=2); break
            except Exception: time.sleep(0.5)
    try:
        ids, tokens = prepare(a.base, a.role_s)
        made = shoot(a.base, ids, tokens, Path(a.out), os.environ.get("PW_CHROMIUM"))
        print(f"screenshotů: {len(made)} → {a.out}")
    finally:
        if proc: proc.terminate()


if __name__ == "__main__":
    main()
