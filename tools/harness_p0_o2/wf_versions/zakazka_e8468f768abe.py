"""
Orchestrátor zakázky (Dapr Workflow) – **verzovaný modul** (P3-6 E6) – KANDIDÁT příští verze (registrovaný, není latest): navíc úlohy
`notify WORKFLOW_VERSION` na startu a `notify KLASIFIKACE_DONE` po klasifikaci (orchestrátor sám zapisuje svou verzi do ledgeru). Jiné pořadí úloh
než aktuální verze = přesně ta změna, která bez verzování končí FAILED (nález P3-5); zde ji nese jen instance, která pod touto verzí začala
(harness E6b: přepne latest, založí zakázku, vrátí latest, restartuje pod – instance dojede na této verzi). Povýšení na latest = zkopírovat
přes zakazka_wf.py, až budou instance z doby před verzováním (`legacy` v GET /_wf/versions) terminální.

Proč samostatný soubor: Dapr Workflow přehrává historii instance proti kódu orchestrátoru (replay); změna pořadí/jmen úloh v běžícím
procesu = nedeterministický replay → instance FAILED (nález P3-5: instance čekající dny na HITL po nasazení nového obrazu). Dapr 1.17+
umí *named versioning*: každá verze orchestrátoru je registrovaná pod stejným jménem `zakazka` s vlastní `version_name`; verze, pod kterou
instance začala, je v její historii (`OrchestratorStarted.version`) a replay vybírá vždy ji. Neregistrovaná verze = STALLED (ne FAILED),
dokud se verze nevrátí. Nové instance dostávají `is_latest`.

Pravidla tohoto modulu (wf_versions.py je vynucuje):
- Modul je **soběstačný**: aktivity volá jen **jménem** (řetězec), konstanty čte z env sám, z aplikace nic neimportuje. Jeho obsah = verze:
  `VERSION` = sha256 souboru (12 hex). Každá změna souboru → nová verze; snímek každé verze leží v `wf_versions/zakazka_<VERSION>.py`
  (`python wf_versions.py freeze`), aplikace registruje všechny snímky a aktuální soubor jako latest. Staré snímky zůstávají, dokud
  má některá instance jejich verzi (`GET /_wf/versions` → `drained`).
- Aktivity (app.py) se mění volně – replay jejich tělo neběží; mění se jen *kontrakt* (jméno, tvar vstupu/výstupu) a ten musí zůstat
  zpětně kompatibilní se všemi registrovanými verzemi (nová pole volitelná, nic nepřejmenovávat).
- Vstup `z` je veřejný kontrakt s životností dnů: jen přidávat volitelná pole.
"""
from __future__ import annotations

import hashlib
import os
from datetime import timedelta

import dapr.ext.workflow as wf

VERSION = hashlib.sha256(open(__file__, "rb").read().replace(b"\r\n", b"\n")).hexdigest()[:12]   # identita této verze orchestrátoru = obsah souboru

HITL_TIMEOUT_S = float(os.environ.get("O1_HITL_TIMEOUT_S", "3600"))
BUDGET_USD = float(os.environ.get("O1_BUDGET_USD", "400"))
BUDGET_TIMEOUT_S = float(os.environ.get("P0_BUDGET_TIMEOUT_S", str(4 * 3600)))   # roles/*.yaml on_exceeded.timeout: 4h, on_timeout: pause
SLA_DEFAULT_S = {"klasifikace": 2 * 86400, "dialog": 2 * 86400, "H1": 2 * 86400, "H1a": 5 * 86400, "H2": 3 * 86400, "H4": 1 * 86400, "H5": 2 * 86400, "rozpocet": 4 * 3600}   # procesy.md SLA (prac. dny ≈ dny – zjednodušení v0)


def h(s): return hashlib.sha256(s.encode()).hexdigest()[:16]


def wait_with_sla(ctx: wf.DaprWorkflowContext, z, event_name, bod, t_out):
    """when_any(event, timeout, SLA): SLA bodu = z['sla'][bod] nebo SLA_DEFAULT_S; překročení → sla_breach (eskalace, org.sla_events), čeká se dál;
    timeout → None (pozastavení řeší volající). Úlohy ev/tm se po SLA timeru použijí znovu (durabletask je přeparentuje do nového when_any)."""
    ev = ctx.wait_for_external_event(event_name); tm = ctx.create_timer(timedelta(seconds=t_out))
    sla_s = float((z.get("sla") or {}).get(bod, SLA_DEFAULT_S.get(bod, 0)) or 0)
    sla = ctx.create_timer(timedelta(seconds=sla_s)) if 0 < sla_s < t_out else None
    winner = yield wf.when_any([ev, tm, sla] if sla is not None else [ev, tm])
    if sla is not None and winner == sla:
        yield ctx.call_activity("sla_breach", input={"z": z, "bod": bod, "sla_s": sla_s})
        winner = yield wf.when_any([ev, tm])
    if winner == tm: return None
    return ev.get_result() or {}


def hitl(ctx: wf.DaprWorkflowContext, z, bod, artifact_hash, timeout_s=None):
    tok, _ = yield from hitl_full(ctx, z, bod, artifact_hash, timeout_s)
    return tok


def hitl_full(ctx: wf.DaprWorkflowContext, z, bod, artifact_hash, timeout_s=None):
    """HITL bod: čeká na event `hitl:<bod>` NEBO timer. Timeout nikdy neschvaluje → stav Pozastaveno. Vrací (token, data eventu) – data nesou
    u bodu `rozpocet` nový strop (P3-6 E3).
    HITL_WAIT v ledgeru = otevřený rozhodovací bod pro AG-UI (interrupt `hitl:<bod>:<hash>`); zamítnutí člověkem (event {rejected}) = HITL_REJECTED → Pozastaveno.
    P3-4: SLA bodu (procesy.md) běží uvnitř čekání – překročení eskaluje, nerozhoduje. P3-6 E6: HITL_WAIT nese verzi orchestrátoru, která bod vystavila."""
    t_out = float(timeout_s if timeout_s is not None else z.get("hitl_timeout_s", HITL_TIMEOUT_S))
    yield ctx.call_activity("notify", input={"event": "HITL_WAIT", "bod": bod, "zakazka": z["id"], "artifact_hash": artifact_hash, "timeout_s": t_out, "sla_s": float((z.get("sla") or {}).get(bod, SLA_DEFAULT_S.get(bod, 0)) or 0), "wf_version": VERSION})
    data = yield from wait_with_sla(ctx, z, f"hitl:{bod}", bod, t_out)
    if data is None:
        yield ctx.call_activity("notify", input={"event": "HITL_TIMEOUT", "bod": bod, "zakazka": z["id"], "result": "pozastaveno"})
        return None, None
    if isinstance(data, dict) and data.get("rejected"):
        yield ctx.call_activity("notify", input={"event": "HITL_REJECTED", "bod": bod, "zakazka": z["id"], "by": data.get("by"), "reason": data.get("reason"), "result": "pozastaveno"})
        return None, data
    tok = yield ctx.call_activity("verify_approval", input={"token": (data.get("token") if isinstance(data, dict) else "") or "", "zakazka": z["id"], "bod": bod})
    if not tok or tok.get("artifact_hash") != artifact_hash or tok.get("bod") != bod:
        yield ctx.call_activity("notify", input={"event": "HITL_INVALID_TOKEN", "bod": bod, "zakazka": z["id"]})
        return None, data
    if isinstance(data.get("subject"), dict) and data["subject"].get("token"): z["subject"] = data["subject"]   # P3-6 E2: další role jedná jménem tohoto schvalovatele (Q6: obnova při každém HITL)
    yield ctx.call_activity("notify", input={"event": "HITL_APPROVED", "bod": bod, "zakazka": z["id"], "by": tok.get("by"), "artifact_hash": artifact_hash, "subject_sub": (data.get("subject") or {}).get("sub")})
    return data["token"], data


def run_role(ctx: wf.DaprWorkflowContext, z, role, activity, inp):
    """Role jako aktivita (jméno `role_<role>`) + `on_exceeded` z roles/<role>.yaml: rozpočet klíče role × zakázka vyčerpán (429 z gateway) →
    BUDGET_EXCEEDED, eskalace vlastníkovi procesu jako HITL bod `rozpocet` (token vázaný na roli), timeout → pauza (fail-closed).
    Po schválení (vlastník navýšil limit / vydal nový klíč) jeden opakovaný pokus; druhé vyčerpání → pauza."""
    gate = yield ctx.call_activity("budget_gate", input={"z": z, "role": role})   # P2-6: strop zakázky (součet klíčů) před rolí
    art = {"budget_exceeded": True, "gate": gate} if gate.get("exceeded") else (yield ctx.call_activity(activity, input=inp))
    for attempt in range(2):   # P3-5: pod role ukončen stopem (SIGTERM → checkpoint) – výsledek dorazí až po resume (workflow je SUSPENDED); pak role znovu od checkpointu
        if not art.get("stopped"): break
        yield ctx.call_activity("notify", input={"event": "ROLE_STOPPED", "role": role, "zakazka": z["id"], "attempt": attempt + 1, "result": "rerun_after_resume" if attempt == 0 else "pozastaveno"})
        if attempt == 1: return None
        art = yield ctx.call_activity(activity, input=inp)   # bez prodlevy (P3-5 nález: timer/sleep po resume znovuspuštění rozbil); klíče tenanta odblokuje resume_tenant PŘED resume workflow
    if not gate.get("exceeded"):
        yield ctx.call_activity("registry_agent", input={"z": z, "role": role})   # P3-3: řádek org.agents píše workflow (T12), ne harness
        yield ctx.call_activity("registry_zakazka", input={"z": z, "status": "Running"})   # P3-5 (O3e): útrata zakázky v org.zakazky po každé roli (FinOps per tenant bez čekání na konec)
    if not art.get("budget_exceeded"): return art
    yield ctx.call_activity("notify", input={"event": "BUDGET_EXCEEDED", "role": role, "zakazka": z["id"], "escalate_to": "process_owner", "timeout_s": z.get("budget_timeout_s", BUDGET_TIMEOUT_S), "source": "zakazka-sum" if gate.get("exceeded") else "agentgateway"})
    tok, data = yield from hitl_full(ctx, z, "rozpocet", role, timeout_s=z.get("budget_timeout_s", BUDGET_TIMEOUT_S))
    if not tok: return None
    new_cap = (data or {}).get("budget_usd")
    if new_cap and float(new_cap) > float(z.get("budget_usd") or BUDGET_USD):   # P3-6 (E3): schválení s novým stropem → gateway klíče (ConfigMap + sonda), registr, workflow
        res = yield ctx.call_activity("raise_cap", input={"z": z, "budget_usd": float(new_cap), "by": data.get("by")})
        z["budget_usd"] = float(new_cap)   # tentýž objekt dostávají další role (deterministické: v replayi se provede stejně)
        if isinstance(inp, dict) and "z" in inp and inp["z"] is not z: inp["z"]["budget_usd"] = float(new_cap)
        yield ctx.call_activity("notify", input={"event": "BUDGET_RAISED", "role": role, "zakazka": z["id"], "budget_usd": float(new_cap), "by": data.get("by"), "gateway": res})
    art = yield ctx.call_activity(activity, input=inp)
    return None if art.get("budget_exceeded") else art


def zakazka(ctx: wf.DaprWorkflowContext, z):
    state = {"id": z["id"], "stav": "P1"}
    yield ctx.call_activity("notify", input={"event": "WORKFLOW_VERSION", "zakazka": z["id"], "wf_version": VERSION})   # kandidát: verze z orchestrátoru, ne z HTTP vrstvy
    # P3-4 P1a klasifikační brána (T9/T15) PŘED prvním během role (odchylka od procesy.md Upresneni → Klasifikace: odmítnutá zakázka nespustí žádný pod ani neutratí nic);
    # odpovědi K1–K6 buď v poptávce (GUI formulář / API), jinak interrupt `klasifikace` v AG-UI; timeout → Pozastaveno
    if not z.get("klasifikace"):
        t_out = float(z.get("hitl_timeout_s", HITL_TIMEOUT_S))
        yield ctx.call_activity("notify", input={"event": "KLASIFIKACE_WAIT", "bod": "klasifikace", "zakazka": z["id"], "artifact_hash": h(z["poptavka"]), "timeout_s": t_out, "sla_s": float((z.get("sla") or {}).get("klasifikace", SLA_DEFAULT_S["klasifikace"]) or 0), "wf_version": VERSION})
        data = yield from wait_with_sla(ctx, z, "klasifikace", "klasifikace", t_out)
        if data is None: yield ctx.call_activity("notify", input={"event": "KLASIFIKACE_TIMEOUT", "bod": "klasifikace", "zakazka": z["id"], "result": "pozastaveno"}); return {**state, "stav": "Pozastaveno", "bod": "klasifikace"}
        z = {**z, "klasifikace": data.get("answers") or {}, "klasifikace_by": data.get("by"), "klasifikace_sub": data.get("sub"), "klasifikace_reason": data.get("reason")}
    kl = yield ctx.call_activity("klasifikace", input={"z": z})
    yield ctx.call_activity("notify", input={"event": "KLASIFIKACE_DONE", "zakazka": z["id"], "profile": kl["profile"], "wf_version": VERSION})   # kandidát: důkaz, že po restartu podu běží instance dál na své verzi
    z = {**z, "profile": kl["profile"], "sensitivity": kl["sensitivity"]}
    if kl["profile"] == "odmitnout":                                              # čl. 5 → zakázka končí v P1 s auditním záznamem (org.approvals decision=reject)
        yield ctx.call_activity("registry_zakazka", input={"z": z, "status": "Odmitnuto"}); return {**state, "stav": "Odmitnuto", "bod": "klasifikace", "reason": "čl. 5 (K1 = ano)", "profile": kl["profile"]}
    if kl["profile"] == "nejasne":                                                # H1a stanovisko právníka; do stanoviska high-risk zacházení (autonomie zamčena)
        t1a = yield from hitl(ctx, z, "H1a", kl["hash"])
        if not t1a: return {**state, "stav": "Pozastaveno", "bod": "H1a", "profile": kl["profile"]}
    for rnd in range(int(z.get("dialog_max", 3)) + 1):                            # P1 Přijetí zadání – P3-3: ≤ 3 kola upřesňujících otázek Account ↔ zadavatel (AG-UI)
        zad = yield from run_role(ctx, z, "account", "role_account", z)
        if not zad: yield ctx.call_activity("registry_zakazka", input={"z": z, "status": "BudgetExceeded"}); return {**state, "stav": "Pozastaveno", "bod": "rozpocet", "role": "account"}
        if zad.get("type") != "otazky": break
        if rnd >= int(z.get("dialog_max", 3)): yield ctx.call_activity("notify", input={"event": "DIALOG_LIMIT", "zakazka": z["id"], "rounds": rnd}); return {**state, "stav": "Pozastaveno", "bod": "dialog"}
        yield ctx.call_activity("notify", input={"event": "DIALOG_WAIT", "bod": "dialog", "zakazka": z["id"], "artifact_hash": zad["hash"], "round": rnd + 1, "timeout_s": float(z.get("hitl_timeout_s", HITL_TIMEOUT_S))})
        data = yield from wait_with_sla(ctx, z, "dialog:account", "dialog", float(z.get("hitl_timeout_s", HITL_TIMEOUT_S)))
        if data is None:
            yield ctx.call_activity("notify", input={"event": "DIALOG_TIMEOUT", "bod": "dialog", "zakazka": z["id"], "result": "pozastaveno"}); return {**state, "stav": "Pozastaveno", "bod": "dialog"}
        yield ctx.call_activity("notify", input={"event": "DIALOG_ANSWER", "bod": "dialog", "zakazka": z["id"], "by": data.get("by"), "round": rnd + 1, "answer": str(data.get("answer", ""))[:500]})
        z = {**z, "dialog": (z.get("dialog") or []) + [str(data.get("answer", ""))[:2000]]}
    gh_hitl = os.environ.get("P0_HITL_GITHUB") == "1"
    if os.environ.get("P0_GITHUB_MODE") == "1" and gh_hitl:
        yield ctx.call_activity("publish_issue", input={"z": z, "zad": zad})     # issue = nosič H1 (dogfooding, vlastní repo; cizí zákazník → AG-UI)
    t1 = yield from hitl(ctx, z, "H1", zad["hash"])                           # vstup zakázky – člověk zákazníka (/schvaluji na issue nebo AG-UI)
    if not t1: return {**state, "stav": "Pozastaveno", "bod": "H1"}
    if os.environ.get("P0_GITHUB_MODE") == "1" and not gh_hitl:
        yield ctx.call_activity("publish_issue", input={"z": z, "zad": zad})     # bez GitHub HITL: issue až po schválení (N3)
    yield ctx.call_activity("notify_customer", input={"z": z, "channel": "email", "role": "account", "subject": f"Zakázka {z['id']}: zadání přijato (H1)",   # P3-4 N3 stavová zpráva (čl. 50 naostro)
                                                       "body": f"Zadání zakázky {z['id']} bylo schváleno člověkem (H1); profil rizika {kl['profile']}. Artefakt {zad['ref']} · hash {zad['hash']}."})
    adr = yield from run_role(ctx, z, "architekt", "role_architekt", z)        # P2 Návrh
    if not adr: yield ctx.call_activity("registry_zakazka", input={"z": z, "status": "BudgetExceeded"}); return {**state, "stav": "Pozastaveno", "bod": "rozpocet", "role": "architekt"}
    t2 = yield from hitl(ctx, z, "H2", adr["hash"])
    if not t2: return {**state, "stav": "Pozastaveno", "bod": "H2"}
    pr = yield from run_role(ctx, z, "vyvojar", "role_vyvojar", z)             # P3 Implementace (sandbox)
    if not pr: yield ctx.call_activity("registry_zakazka", input={"z": z, "status": "BudgetExceeded"}); return {**state, "stav": "Pozastaveno", "bod": "rozpocet", "role": "vyvojar"}
    pr_pub = {}
    if os.environ.get("P0_GITHUB_MODE") == "1":
        pr_pub = yield ctx.call_activity("publish_pr", input={"z": z, "pr": pr})  # větev + PR = artefakt pro review (reverzibilní)
    rev = yield from run_role(ctx, z, "reviewer", "role_reviewer", {"z": z, "pr": pr})   # P4 Review
    if not rev: yield ctx.call_activity("registry_zakazka", input={"z": z, "status": "BudgetExceeded"}); return {**state, "stav": "Pozastaveno", "bod": "rozpocet", "role": "reviewer"}
    yield ctx.call_activity("budget_check", input=z)
    t4 = yield from hitl(ctx, z, "H4", pr["hash"])                            # merge = N1 – člověk vlastník
    if not t4: return {**state, "stav": "Pozastaveno", "bod": "H4"}
    m = yield ctx.call_activity("executor", input={"z": z, "action": "merge", "artifact_hash": pr["hash"], "token": t4, "pr": pr, "pr_publish": pr_pub})
    if not m["allow"]: return {**state, "stav": "Zamitnuto", "bod": "H4", "reason": m["reason"]}
    t5 = yield from hitl(ctx, z, "H5", pr["hash"])                            # deploy = N2
    if not t5: return {**state, "stav": "Pozastaveno", "bod": "H5"}
    d = yield ctx.call_activity("executor", input={"z": z, "action": "deploy", "artifact_hash": pr["hash"], "token": t5})
    yield ctx.call_activity("notify_customer", input={"z": z, "channel": "ticket", "role": "sre", "body": f"Nasazení zakázky {z['id']} {'provedeno' if d['allow'] else 'zamítnuto'} (H5 schválil člověk; PR {pr['ref']} · hash {pr['hash']})."})   # P3-4 N3 ticket
    spent = yield ctx.call_activity("budget_check", input=z)
    yield ctx.call_activity("registry_zakazka", input={"z": z, "status": "Dokonceno" if d["allow"] else "Zamitnuto"})   # P2-6: cena zakázky v registru org.zakazky
    return {**state, "stav": "Dokonceno" if d["allow"] else "Zamitnuto", "artefakty": [zad["ref"], adr["ref"], pr["ref"], rev["ref"]], "cost_usd": spent}
