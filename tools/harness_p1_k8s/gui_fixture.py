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
    import app as A

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
            st = self.inst[zid]; A.ledger("NOTIFY", event="HITL_WAIT", bod=bod, zakazka=zid, artifact_hash=hh, timeout_s=timeout); t0 = time.time()
            while time.time() - t0 < timeout:
                if st["paused"]: return "paused"
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
            fn = {"account": "zadani.md", "architekt": "adr.md", "reviewer": "review.md"}.get(role)
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
            h1 = self._role(zid, "account", f"issue://{zid}", "human:zakaznik", f"# Zadání\n\nCíl: {z['poptavka']}\n\nAkceptační kritéria: soubor existuje.")
            if h1 is None: return
            if (t := self._wait(zid, "H1", h1, z.get("hitl_timeout_s", 3600))) in (None, "paused"): return (None if t == "paused" else end({"id": zid, "stav": "Pozastaveno", "bod": "H1"}))
            A.ledger("PUBLISHED", zakazka=zid, publish_kind="issue", number=7, mode="mock")
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
            end({"id": zid, "stav": "Dokonceno", "artefakty": [f"issue://{zid}", f"adr://{zid}", f"pr://{zid}", f"review://{zid}"], "cost_usd": 0.016})
        def get_workflow_state(self, zid, fetch_payloads=False):
            st = self.inst.get(zid)
            return FakeState("SUSPENDED" if st and st["paused"] else st["status"], st.get("output")) if st else None
        def raise_workflow_event(self, zid, name, data=None): self.inst[zid]["events"][name] = data or {}
        def pause_workflow(self, zid): self.inst[zid]["paused"] = True
        def resume_workflow(self, zid): self.inst[zid]["paused"] = False

    A._client = FakeClient()
    print(f"fixture: ledger={led} gui={a.gui} port={a.port}", flush=True)
    import uvicorn
    uvicorn.run(A.app, host="127.0.0.1", port=a.port, log_level="warning")


if __name__ == "__main__":
    main()
