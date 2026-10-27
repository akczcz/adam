"""
gui_fixture.py – lokální AG-UI server bez Dapru a Keycloaku pro vývoj GUI a U-1 scénáře (P3-1): app.py s falešným workflow klientem,
který zakázku „přehrává“ zápisem do ledgeru (ROLE_GATE → HANDOFF → HITL_WAIT → …), reaguje na raise_event (hitl:*), pause (stop).
Spuštění: python tools/harness_p1_k8s/gui_fixture.py --port 8010 --gui gui/dist   (dev tokeny: adam/adam tenant acme, bea/bea tenant beta)
Nic z toho není součást obrazu – měří se tím GUI a mapování ledger → AG-UI, ne platforma.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import threading
import time
from pathlib import Path

from fastapi import APIRouter, Request   # na úrovni modulu: anotace jsou řetězce (from __future__ import annotations) a FastAPI je hledá v globals
from fastapi.responses import PlainTextResponse

HERE = Path(__file__).resolve().parent
O2 = HERE.parent / "harness_p0_o2"
sys.path.insert(0, str(O2))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8010)
    ap.add_argument("--gui", default=str(HERE.parent.parent / "gui/dist"))
    ap.add_argument("--ledger", default="")
    ap.add_argument("--role-s", type=float, default=1.5, help="trvání role v simulaci")
    a = ap.parse_args()
    led = a.ledger or os.path.join(tempfile.mkdtemp(prefix="agui-fx-"), "ledger.jsonl")
    os.environ.update({"O1_LEDGER": led, "P0_GUI_DIR": a.gui, "P0_TENANT": "acme", "P0_AGUI_RUN_MAX_S": "600",
                       "P0_AGUI_DEV_USERS": json.dumps({"adam": {"password": "adam", "tenant_id": "acme", "roles": ["human", "reviewer"]}, "bea": {"password": "bea", "tenant_id": "beta", "roles": ["human"]}, "bot": {"password": "bot", "tenant_id": "acme", "roles": ["agent"]}, "platform-admin": {"password": "platform-admin", "tenant_id": "platform", "roles": ["human", "platform_admin"]}})})
    os.environ.pop("P0_KC_TOKEN_URL", None); os.environ.pop("P0_KC_JWKS_URL", None); os.environ.pop("P0_BAO_ADDR", None)
    os.environ["P0_CHANNELS_URL"] = f"http://127.0.0.1:{a.port}/channels"   # P3-4: mock kanálů (e-mail, ticket) namountovaný do téhož serveru
    import app as A
    import mock_channels

    class FakeState:
        def __init__(self, status, output=None):
            self.runtime_status = type("S", (), {"name": status})(); self.serialized_output = json.dumps(output) if output else None

    class FakeClient:
        """Simulace workflow zakázky: vlákno per instance; HITL = čekání na event; pause = zastavení vlákna."""
        def __init__(self): self.inst = {}
        def schedule_new_workflow(self, wf, input, instance_id):
            z = input; st = {"status": "RUNNING", "output": None, "events": {}, "paused": False, "z": z}
            self.inst[instance_id] = st
            threading.Thread(target=self._run, args=(instance_id,), daemon=True).start()
        def _wait(self, zid, bod, hh, timeout):
            st = self.inst[zid]; sla = float((st["z"].get("sla") or {}).get(bod, 0) or 0); A.ledger("NOTIFY", event="HITL_WAIT", bod=bod, zakazka=zid, artifact_hash=hh, timeout_s=timeout, sla_s=sla); t0 = time.time(); breached = False
            while time.time() - t0 < timeout:
                if st["paused"]: return "paused"
                if sla and not breached and time.time() - t0 > sla: breached = True; A.sla_breach_run(st["z"], bod, sla)   # P3-4: SLA eskaluje, nerozhoduje
                ev = st["events"].pop(f"hitl:{bod}", None)
                if ev is not None:
                    if ev.get("rejected"): A.ledger("NOTIFY", event="HITL_REJECTED", bod=bod, zakazka=zid, by=ev.get("by"), reason=ev.get("reason"), result="pozastaveno"); return None
                    tok = A.verify(ev.get("token", "")); A.ledger("VERIFY", backend="hmac", zakazka=zid, bod=bod, valid=bool(tok), by=(tok or {}).get("by"))
                    if not tok or tok.get("artifact_hash") != hh or tok.get("bod") != bod: A.ledger("NOTIFY", event="HITL_INVALID_TOKEN", bod=bod, zakazka=zid); return None
                    A.ledger("NOTIFY", event="HITL_APPROVED", bod=bod, zakazka=zid, by=tok.get("by"), artifact_hash=hh); return ev["token"]
                time.sleep(0.2)
            A.ledger("NOTIFY", event="HITL_TIMEOUT", bod=bod, zakazka=zid, result="pozastaveno"); return None
        def _role(self, zid, role, art, to, text):
            st = self.inst[zid]; root = f"/tmp/p0-o2/{zid}/artifacts"; os.makedirs(root, exist_ok=True)
            A.ledger("ROLE_GATE", zakazka=zid, role=role, passed=True, gate="passed", version="0.1.0")
            A.ledger("BUDGET_GATE", zakazka=zid, role=role, spent_usd=0.01, limit_usd=st["z"]["budget_usd"], exceeded=False, source="budget_usage")
            A.ledger("ROLE_POD_CREATE", zakazka=zid, role=role, pod=f"role-{role}-fx", namespace="platform-roles", runtime_class="kata-vm-isolation", image=f"roles/{role}:0.1.0")
            t0 = time.time()
            while time.time() - t0 < a.role_s:
                if st["paused"]: A.ledger("ROLE_POD_ERROR", zakazka=zid, role=role, pod=f"role-{role}-fx", error="pod killed (stop)"); return None
                time.sleep(0.1)
            fn = "otazky.md" if art.startswith("otazky://") else {"account": "zadani.md", "architekt": "adr.md", "reviewer": "review.md"}.get(role)
            if fn: open(f"{root}/{fn}", "w").write(text)
            hh = A.h(text)
            A.ledger("TOOL", zakazka=zid, role=role, tool="search_memory", http=200)
            A.ledger("AGENT_RUN", zakazka=zid, role=role, tool_uses=3, cost_usd=0.004, via="pod", num_turns=4, files=[{"path": "zakazky/x/NOTES.md", "sha256": "abc"}] if role == "vyvojar" else None, result_text=text[:200])
            A.ledger("ROLE_POD", zakazka=zid, role=role, pod=f"role-{role}-fx", namespace="platform-roles", phase="Succeeded", node="aks-kata-1", t_start_s=12.0, t_run_s=round(a.role_s, 1), identity={"spiffe_id": f"spiffe://platform/role/{role}/acme"})
            A.ledger("HANDOFF", frm=role, to=to, zakazka=zid, artifact=art, hash=hh, cost_usd=0.004)
            return hh
        def _run(self, zid):
            st = self.inst[zid]; z = st["z"]
            def end(out): st["status"] = "COMPLETED"; st["output"] = out; A.ledger("REGISTRY_ZAKAZKA", zakazka=zid, status=out.get("stav"), written=False)
            if not z.get("klasifikace"):   # P3-4: dotazník K1–K6 jako interrupt, když nepřišel s poptávkou
                A.ledger("NOTIFY", event="KLASIFIKACE_WAIT", bod="klasifikace", zakazka=zid, artifact_hash=A.h(z["poptavka"]), timeout_s=3600.0, sla_s=0); t0 = time.time(); ans = None
                while time.time() - t0 < 3600:
                    if st["paused"]: return
                    ev = st["events"].pop("klasifikace", None)
                    if ev is not None: ans = ev; break
                    time.sleep(0.2)
                z = st["z"] = {**z, "klasifikace": ans.get("answers") or {}, "klasifikace_by": ans.get("by"), "klasifikace_reason": ans.get("reason")}
            kl = A.klasifikace_run(z); z = st["z"] = {**z, "profile": kl["profile"]}
            if kl["profile"] == "odmitnout": return end({"id": zid, "stav": "Odmitnuto", "bod": "klasifikace", "profile": kl["profile"]})
            if kl["profile"] == "nejasne" and (t := self._wait(zid, "H1a", kl["hash"], z.get("hitl_timeout_s", 3600))) in (None, "paused"): return (None if t == "paused" else end({"id": zid, "stav": "Pozastaveno", "bod": "H1a"}))
            if os.environ.get("FX_DIALOG", "1") == "1":   # P3-3: Account se nejdřív ptá (1 kolo)
                hq = self._role(zid, "account", f"otazky://{zid}/1", "human:zadavatel", "# Upřesňující otázky\n\n1. Kam má soubor přijít?\n2. Je rozpočet výchozí?")
                if hq is None: return
                A.ledger("NOTIFY", event="DIALOG_WAIT", bod="dialog", zakazka=zid, artifact_hash=hq, round=1, timeout_s=3600.0); t0 = time.time(); ans = None
                while time.time() - t0 < 3600:
                    if st["paused"]: return
                    ev = st["events"].pop("dialog:account", None)
                    if ev is not None: ans = ev; break
                    time.sleep(0.2)
                if ans is None: A.ledger("NOTIFY", event="DIALOG_TIMEOUT", bod="dialog", zakazka=zid, result="pozastaveno"); return end({"id": zid, "stav": "Pozastaveno", "bod": "dialog"})
                A.ledger("NOTIFY", event="DIALOG_ANSWER", bod="dialog", zakazka=zid, by=ans.get("by"), round=1, answer=str(ans.get("answer"))[:500])
            h1 = self._role(zid, "account", f"issue://{zid}", "human:zakaznik", f"# Zadání\n\nCíl: {z['poptavka']}\n\nAkceptační kritéria: soubor existuje.")
            if h1 is None: return
            if (t := self._wait(zid, "H1", h1, z.get("hitl_timeout_s", 3600))) in (None, "paused"): return (None if t == "paused" else end({"id": zid, "stav": "Pozastaveno", "bod": "H1"}))
            A.ledger("PUBLISHED", zakazka=zid, publish_kind="issue", number=7, mode="mock")
            A.notify_customer_run({"z": z, "channel": "email", "role": "account", "subject": f"Zakázka {zid}: zadání přijato (H1)", "body": f"Zadání zakázky {zid} bylo schváleno člověkem (H1); profil rizika {kl['profile']}."})
            h2 = self._role(zid, "architekt", f"adr://{zid}", "human:vlastnik", "# ADR\n\n| varianta | + | - |\n|---|---|---|\n| A | jednoduchá | – |\n\nRozhodnutí: A.")
            if h2 is None: return
            if (t := self._wait(zid, "H2", h2, z.get("hitl_timeout_s", 3600))) in (None, "paused"): return (None if t == "paused" else end({"id": zid, "stav": "Pozastaveno", "bod": "H2"}))
            hp = self._role(zid, "vyvojar", f"pr://{zid}", "reviewer", "implementace hotová")
            if hp is None: return
            A.ledger("PUBLISHED", zakazka=zid, publish_kind="pull_request", number=8, mode="mock")
            hr = self._role(zid, "reviewer", f"review://{zid}", "human:vlastnik", "verdict: ok\n\nŽádné vady.")
            if hr is None: return
            A.ledger("BUDGET", zakazka=zid, spent_usd=0.016, limit_usd=z["budget_usd"], source="budget_usage", window="30d", by_role={"account": 0.004})
            if (t := self._wait(zid, "H4", hp, z.get("hitl_timeout_s", 3600))) in (None, "paused"): return (None if t == "paused" else end({"id": zid, "stav": "Pozastaveno", "bod": "H4"}))
            A.ledger("PDP", action="merge", actor="merge-executor", zakazka=zid, decision={"allow": True}, approval_by="adam"); A.ledger("EXECUTED", action="merge", by="merge-executor", zakazka=zid, artifact_hash=hp, applied=[])
            if (t := self._wait(zid, "H5", hp, z.get("hitl_timeout_s", 3600))) in (None, "paused"): return (None if t == "paused" else end({"id": zid, "stav": "Pozastaveno", "bod": "H5"}))
            A.ledger("PDP", action="deploy", actor="deploy-executor", zakazka=zid, decision={"allow": True}, approval_by="adam"); A.ledger("EXECUTED", action="deploy", by="deploy-executor", zakazka=zid, artifact_hash=hp, applied=[])
            A.notify_customer_run({"z": z, "channel": "ticket", "role": "sre", "body": f"Nasazení zakázky {zid} provedeno (H5 schválil člověk)."})
            end({"id": zid, "stav": "Dokonceno", "artefakty": [f"issue://{zid}", f"adr://{zid}", f"pr://{zid}", f"review://{zid}"], "cost_usd": 0.016})
        def get_workflow_state(self, zid, fetch_payloads=False):
            st = self.inst.get(zid)
            return FakeState("SUSPENDED" if st and st["paused"] else st["status"], st.get("output")) if st else None
        def raise_workflow_event(self, zid, name, data=None): self.inst[zid]["events"][name] = data or {}
        def pause_workflow(self, zid): self.inst[zid]["paused"] = True
        def resume_workflow(self, zid): self.inst[zid]["paused"] = False

    A._client = FakeClient()
    # falešný Governance MCP (bez DB): canned data – jen pro vývoj stránek GUI a lokální U-2 smoke
    fx = APIRouter(prefix="/govfake")
    def _u(req): return A.agui.user_from_request(req)
    @fx.get("/resources")
    async def _res(req: Request): _u(req); return {"tools": [{"name": n, "description": n} for n in ("tenants", "zakazky", "roles", "agents", "approvals", "agent_events", "risk_register", "finops", "governance_report", "export")], "read_only": True, "db_role": "org_reader"}
    @fx.post("/tools/{name}")
    async def _tool(name: str, req: Request):
        u = _u(req); ten = ["acme", "beta", "platform"] if u["tenant"] == "platform" else [u["tenant"]]
        L = A._ledger(); zs = [e for e in L if e.get("kind") == "ZAKAZKA_START" and (e.get("tenant") or "acme") in ten]
        data = {"tenants": [{"tenant_id": t, "name": t, "profile": "standard", "budget_usd": 20.0, "spent_usd": 0.016 * len(zs), "role_pods": t != "platform", "namespace": f"tenant-{t}", "status": "active"} for t in ten],
                "zakazky": [{"zakazka_id": e["zakazka"], "tenant_id": e.get("tenant") or "acme", "budget_usd": e.get("budget_usd"), "spent_usd": 0.016, "spent_by_role": {"account": 0.004}, "status": "Running"} for e in zs],
                "roles": [{"role_id": r, "version": "0.1.0", "status": "active", "eval_gates": [{"layer": "L0", "value": 1, "threshold": 1, "passed": True}], "autonomy": {}, "autonomy_max": "A2"} for r in ("account", "architekt", "vyvojar", "reviewer", "sre")],
                "agents": [{"agent_id": f"spiffe://platform/role/account/{e.get('tenant') or 'acme'}/{e['zakazka']}/fx", "tenant_id": e.get("tenant") or "acme", "role_id": "account", "role_version": "0.1.0", "zakazka_id": e["zakazka"], "model": "mock", "gateway_key_id": "k-x", "sandbox_profile": "kata", "cost_usd": 0.004} for e in zs],
                "approvals": [{"decided_at": "", "tenant_id": e.get("tenant") or "acme", "workflow_instance": e["zakazka"], "process_id": e.get("bod"), "action": e.get("bod"), "decision": "approve", "approver": e.get("by"), "reason": e.get("reason"), "channel": e.get("channel")} for e in L if e.get("kind") == "APPROVAL_RAISED"],
                "agent_events": [], "risk_register": [],
                "finops": {"tenants": [{"tenant_id": t, "budget_usd": 20.0, "spent_usd": 17.0 if t == "beta" else 1.0, "pct": 85.0 if t == "beta" else 5.0, "alert": t == "beta", "status": "active"} for t in ten], "zakazky": [], "by_role": {"account": 0.1}, "window": "30d"},
                "governance_report": {"generated_at": "now", "tenant_view": u["tenant"], "zakazky": [{"zakazka_id": e["zakazka"], "tenant_id": e.get("tenant") or "acme", "status": "Running", "missing": (["T15:klasifikace"] if not any(k.get("kind") == "KLASIFIKACE" and k.get("zakazka") == e["zakazka"] for k in L) else []) + ["T11:risk_register"], "spent_usd": 0.0, "budget_usd": 20.0} for e in zs], "roles": [], "summary": {"zakazky": len(zs), "with_gaps": len(zs), "complete": 0, "t_items": {"T15": "klasifikace"}}},
                "export": [{"table": "zakazky", "tenant_id": e.get("tenant") or "acme", "zakazka_id": e["zakazka"]} for e in zs]}
        return {"tenant": u["tenant"], "result": data.get(name, [])}
    @fx.get("/export.jsonl", response_class=PlainTextResponse)
    async def _exp(req: Request):
        u = _u(req); ten = ["acme", "beta", "platform"] if u["tenant"] == "platform" else [u["tenant"]]
        return "\n".join(json.dumps({"table": "zakazky", "tenant_id": e.get("tenant") or "acme", "zakazka_id": e["zakazka"]}) for e in A._ledger() if e.get("kind") == "ZAKAZKA_START" and (e.get("tenant") or "acme") in ten) + "\n"
    A.app.include_router(fx); A.agui.GOV_URL = f"http://127.0.0.1:{a.port}/govfake"
    A.app.mount("/channels", mock_channels.app)
    A.agui.CTX["autonomy"] = lambda role, tenant, level, u, reason: ({"ok": True, "current": "A0", "target": level, "written": True, "metrics": {"tasks": 12}} if tenant == "acme" else {"ok": False, "current": "A0", "target": level, "reasons": ["úkolů 0 < 10"], "metrics": {"tasks": 0}})
    A.agui.CTX["stop_tenant"] = lambda tenant, u, reason: {"ok": True, "tenant": tenant, "paused": [z for z, st_ in A._client.inst.items() if st_["z"].get("tenant") == tenant and not st_["paused"] and not [st_.__setitem__("paused", True)]], "pods_killed": [], "keys_blocked": 0, "registry": False}
    A.agui.CTX["resume_tenant"] = lambda tenant, u, reason: {"ok": True, "tenant": tenant, "resumed": [z for z, st_ in A._client.inst.items() if st_["z"].get("tenant") == tenant and st_["paused"] and not [st_.__setitem__("paused", False)]], "keys_unblocked": 0, "registry": False}
    print(f"fixture: ledger={led} gui={a.gui} port={a.port}", flush=True)
    import uvicorn
    uvicorn.run(A.app, host="127.0.0.1", port=a.port, log_level="warning")


if __name__ == "__main__":
    main()
