"""
Verze orchestrátoru zakázky (P3-6 E6) – snímky `wf_versions/zakazka_<verze>.py` a jejich registrace v Dapr Workflow runtime.

Verze = sha256 obsahu `zakazka_wf.py` (12 hex). Aplikace registruje všechny snímky pod jménem workflow `zakazka` (`register_versioned_workflow`,
Dapr 1.17+ named versioning) a aktuální `zakazka_wf.py` jako `is_latest`; instance nese svou verzi v historii (`OrchestratorStarted.version`),
takže po nasazení nového obrazu běží dál na kódu, se kterým začala. Snímek se smí smazat, až žádná instance jeho verzi nemá
(`GET /_wf/versions` → `drained`); chybějící verze = instance STALLED (Dapr), ne FAILED.

CLI:  python wf_versions.py freeze   – uloží snímek aktuální verze (pokud chybí); spustit po každé změně zakazka_wf.py (před commitem)
      python wf_versions.py check    – exit 1, když aktuální verze nemá snímek nebo některý snímek neodpovídá svému názvu (CI / harness E6a)
      python wf_versions.py list     – verze a cesty
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCE = HERE / "zakazka_wf.py"
SNAP_DIR = HERE / "wf_versions"
NAME = "zakazka"
_SNAP_RE = re.compile(r"^zakazka_([0-9a-f]{12})\.py$")
NON_TERMINAL = {"RUNNING", "SUSPENDED", "PENDING", "STALLED", "CONTINUED_AS_NEW"}


def file_version(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()[:12]


def current_version() -> str:
    return file_version(SOURCE)


def snapshots() -> dict:
    """{verze: {"path", "ok"}} – ok = obsah souboru odpovídá verzi v názvu (snímek se nesmí editovat; změna = jiná verze = jiný soubor)."""
    out = {}
    if not SNAP_DIR.is_dir(): return out
    for p in sorted(SNAP_DIR.iterdir()):
        m = _SNAP_RE.match(p.name)
        if not m: continue
        out[m.group(1)] = {"path": str(p), "ok": file_version(p) == m.group(1)}
    return out


def freeze() -> dict:
    v = current_version(); SNAP_DIR.mkdir(exist_ok=True)
    p = SNAP_DIR / f"zakazka_{v}.py"
    created = not p.exists()
    if created: p.write_bytes(SOURCE.read_bytes())
    return {"version": v, "path": str(p), "created": created}


def check() -> dict:
    v = current_version(); snaps = snapshots()
    bad = sorted(k for k, s in snaps.items() if not s["ok"])
    return {"current": v, "frozen": v in snaps and snaps[v]["ok"], "snapshots": sorted(snaps), "bad": bad, "ok": v in snaps and snaps[v]["ok"] and not bad}


def _load(path: Path, modname: str):
    spec = importlib.util.spec_from_file_location(modname, path); mod = importlib.util.module_from_spec(spec)
    sys.modules[modname] = mod; spec.loader.exec_module(mod)
    return mod


def _wrap(fn):
    """Čerstvý objekt funkce pro každou registraci: SDK si na funkci zapisuje `_workflow_registered` a druhou registraci odmítá – a `app` se
    importuje i podruhé (aktivity rolí: `import app` v gateway_keys/role_runner vedle `__main__`), s vlastním WorkflowRuntime, který nikdy nestartuje."""
    def zakazka(ctx, z): return (yield from fn(ctx, z))
    return zakazka


def register(rt) -> dict:
    """Registrace všech verzí do WorkflowRuntime: snímky (is_latest=False) + aktuální zakazka_wf.py (is_latest=True). Snímek, který se neshoduje
    se svým názvem, se neregistruje (hlášen v `bad`). Chybí-li snímek aktuální verze (`unfrozen`), běží se dál – ale příští obraz by starou verzi ztratil."""
    import zakazka_wf
    cur = zakazka_wf.VERSION; snaps = snapshots(); registered = []; bad = []
    for v, s in snaps.items():
        if not s["ok"]: bad.append(v); continue
        if v == cur: continue
        mod = sys.modules.get(f"wf_versions.zakazka_{v}") or _load(Path(s["path"]), f"wf_versions.zakazka_{v}")
        rt.register_versioned_workflow(_wrap(mod.zakazka), name=NAME, version_name=v, is_latest=False); registered.append(v)
    rt.register_versioned_workflow(_wrap(zakazka_wf.zakazka), name=NAME, version_name=cur, is_latest=True); registered.append(cur)
    if latest(rt) != cur: raise RuntimeError(f"registr workflow runtime nehlásí latest={cur} (SDK dapr-ext-workflow jiné verze než 1.18.3?)")   # privátní atribut SDK – selhat při startu, ne tiše
    missing = missing_activities(rt, [SOURCE] + [Path(s["path"]) for v, s in snaps.items() if s["ok"] and v != cur])
    if missing: raise RuntimeError(f"orchestrátor volá aktivity, které app.py neregistruje: {missing} (nález E6: smazaná raise_cap → instance FAILED až při navýšení stropu)")
    return {"name": NAME, "current": cur, "versions": sorted(registered), "unfrozen": cur not in snaps or not snaps[cur]["ok"], "bad": bad, "activities_checked": True}


_ACT_RE = re.compile(r'call_activity\(\s*"([a-z_]+)"|run_role\(ctx, z, "[a-z]+", "([a-z_]+)"')


def missing_activities(rt, files) -> list:
    """Jména aktivit volaná v (každé verzi) orchestrátoru vs. aktivity registrované v runtime: chybějící jméno = instance FAILED až v okamžiku volání
    (kontrakt aktivit musí platit pro všechny registrované verze, ne jen pro latest)."""
    used = set()
    for f in files:
        for m in _ACT_RE.finditer(Path(f).read_text()): used.add(m.group(1) or m.group(2))
    have = set(_registry(rt).activities)
    return sorted(used - have)


def _registry(rt):
    """Registr orchestrátorů durabletask workeru uvnitř WorkflowRuntime (privátní atribut SDK dapr-ext-workflow 1.18.3 – pinned; jediná cesta,
    jak za běhu zjistit/změnit `is_latest`)."""
    return getattr(getattr(rt, "_WorkflowRuntime__worker"), "_registry")


def latest(rt) -> str | None:
    return _registry(rt).latest_versioned_orchestrators_version_name.get(NAME)


def set_latest(rt, version: str) -> dict:
    """Přepnutí verze pro NOVÉ instance za běhu (rollback/kanárek bez nového obrazu; běžící instance to nemění – mají verzi v historii).
    Platí do restartu podu (pak latest = zakazka_wf.py obrazu)."""
    reg = _registry(rt); have = reg.versioned_orchestrators.get(NAME, {})
    if version not in have: raise KeyError(f"verze {version} není registrovaná (k dispozici: {sorted(have)})")
    prev = reg.latest_versioned_orchestrators_version_name.get(NAME)
    reg.latest_versioned_orchestrators_version_name[NAME] = version
    return {"name": NAME, "latest": version, "previous": prev}


def report(rt, starts: list, state_of) -> dict:
    """Instance per verze: starts = záznamy ZAKAZKA_START ledgeru (zakazka, wf_version), state_of(zid) → {"status"} nebo None.
    `drained` = žádná ne-terminální instance verze → snímek lze smazat. `legacy` = instance založené před verzováním (bez wf_version; Dapr je
    přehrává na latest – kompatibilní jen pokud se pořadí úloh nezměnilo)."""
    reg = _registry(rt); have = sorted(reg.versioned_orchestrators.get(NAME, {}))
    per = {v: {"registered": True, "instances": {}, "drained": True} for v in have}; legacy = {"instances": {}, "drained": True}
    for e in starts:
        zid, v = e.get("zakazka"), e.get("wf_version")
        so = state_of(zid) or {}; st = so.get("status") or "UNKNOWN"
        slot = per.setdefault(v, {"registered": False, "instances": {}, "drained": True}) if v else legacy
        slot["instances"][st] = slot["instances"].get(st, 0) + 1
        if st in NON_TERMINAL or st == "UNKNOWN": slot["drained"] = False
        if st == "FAILED" and so.get("failure") and len(slot.setdefault("failures", [])) < 3:   # proč (Dapr failureDetails) – vzorek pro diagnostiku replaye
            slot["failures"].append({"zakazka": zid, "type": so["failure"].get("type"), "message": (so["failure"].get("message") or "")[:240]})
    return {"name": NAME, "current": current_version(), "latest": latest(rt), "versions": per, "legacy": legacy, "snapshots": {k: s["ok"] for k, s in snapshots().items()}}


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "list"
    if cmd == "freeze": print(json.dumps(freeze()))
    elif cmd == "check":
        c = check(); print(json.dumps(c))
        if not c["ok"]:
            print(f"zakazka_wf.py verze {c['current']} nemá snímek nebo snímek neodpovídá názvu ({c['bad']}) – spusť `python wf_versions.py freeze`", file=sys.stderr); sys.exit(1)
    else: print(json.dumps({"current": current_version(), "snapshots": snapshots()}, indent=1))
