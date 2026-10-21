#!/usr/bin/env python3
"""
Harness: přežije běh Claude Agent SDK nad Dapr Agents restart uprostřed schvalování?

Testuje zvolenou cestu z knowledge/frameworks/overview.md (rozhodnutí 2026-10-21):
smyčka = Claude Agent SDK, trvalost = Dapr Agents ``ClaudeAgentExecutor`` +
``DaprSessionStore``. Stejný styl jako tools/smoke_mcp_2026_07_28.py – každé
tvrzení tiskne TVRZENÍ / VÝSLEDEK / VERDIKT a vše se ukládá do results/*.json.

Tvrzení, která se falsifikují:
    T1  Druhý běh se stejným session_id si pamatuje první (transcript ve state storu).
    T2  Čekající schválení přežije SIGKILL aplikace i sidecaru – po restartu ho
        GET /hitl/approvals zase vrátí (``_restore_pending_approvals``).
    T3  Po restartu lze schválit a běh dokončí; nástroj se side-effectem proběhl
        PŘESNĚ JEDNOU (ledger start=1, end=1).
    T4  Transcript po restartu drží celou historii (follow-up turn si pamatuje
        první otázku i převod).
    T5  Restart uprostřed běhu nástroje (po schválení) – kolikrát se nástroj
        spustil? Spec dapr-agents to negarantuje; harness to jen změří.
    T6  Zamítnutí: nástroj neproběhl (ledger prázdný) a Claude to neopakuje.
    T7  Dlouhá pauza mezi schvalovacím bodem a rozhodnutím (konfigurovatelná,
        výchozí 120 s, lze dny) s restartem uprostřed.

Spuštění (viz README.md):
    .venv/bin/python harness.py --scenario all
    .venv/bin/python harness.py --scenario restart-while-waiting
    .venv/bin/python harness.py --scenario long-pause --pause-seconds 3600

Limit: ``dapr run`` na lokálním stroji není Kubernetes pod. SIGKILL celé
procesní skupiny zabije aplikaci i daprd, což odpovídá restartu podu včetně
sidecaru. Redis z ``dapr init`` běží v Dockeru a restart přežije – to je
záměr (stav má přežít, proces ne).
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import signal
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx

HERE = pathlib.Path(__file__).resolve().parent
RESULTS = HERE / "results"
LOGS = HERE / "logs"

APP_ID = "claude-harness"
APP_PORT = int(os.getenv("APP_PORT", "8001"))
DAPR_HTTP = int(os.getenv("DAPR_HTTP_PORT", "3500"))
DAPR_GRPC = int(os.getenv("DAPR_GRPC_PORT", "50001"))
BASE = f"http://127.0.0.1:{APP_PORT}"
SIDECAR = f"http://127.0.0.1:{DAPR_HTTP}"

FINISHED = {"COMPLETED", "FAILED", "TERMINATED"}
READY_TIMEOUT = 120
RUN_TIMEOUT = 240
APPROVAL_WAIT = 180

TASK_WEATHER = "What's the weather in Paris?"
TASK_RESUME = "Which city did I just ask about? Answer in one sentence."
TASK_TRANSFER = "Send $25 to Alice for dinner."
TASK_RECALL = (
    "In one sentence: which city did I ask about first in this conversation, "
    "and did a money transfer to Alice happen or not?"
)

# ----------------------------------------------------------------------------
# Evidence
# ----------------------------------------------------------------------------

results: List[Dict[str, Any]] = []
evidence: Dict[str, Any] = {}


def verdict(claim: str, ok: Optional[bool], detail: str) -> None:
    mark = {True: "✅ POTVRZENO", False: "❌ VYVRÁCENO", None: "⚠️  NEJASNÉ"}[ok]
    print(f"  {mark}  {claim}: {detail}", flush=True)
    results.append({"claim": claim, "ok": ok, "detail": detail})


def section(title: str) -> None:
    print(f"\n=== {title} ===", flush=True)


def note(msg: str) -> None:
    print(f"  · {msg}", flush=True)


# ----------------------------------------------------------------------------
# Ledger (side-effect counter)
# ----------------------------------------------------------------------------


class Ledger:
    def __init__(self, path: pathlib.Path) -> None:
        self.path = path

    def reset(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text("", encoding="utf-8")

    def entries(self) -> List[Dict[str, Any]]:
        if not self.path.exists():
            return []
        out = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                out.append(json.loads(line))
        return out

    def count(self, phase: str) -> int:
        return sum(1 for e in self.entries() if e.get("phase") == phase)

    def wait_for(self, phase: str, timeout: float) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.count(phase) > 0:
                return True
            time.sleep(0.5)
        return False


# ----------------------------------------------------------------------------
# Process under test: `dapr run -- python app.py`
# ----------------------------------------------------------------------------


def _process_tree(root: int) -> List[int]:
    """root + všichni potomci (přes `ps`, bez psutil)."""
    out = subprocess.run(["ps", "-axo", "pid=,ppid="], capture_output=True, text=True).stdout
    children: Dict[int, List[int]] = {}
    for line in out.splitlines():
        try:
            pid, ppid = (int(x) for x in line.split())
        except ValueError:
            continue
        children.setdefault(ppid, []).append(pid)
    tree, stack = [], [root]
    while stack:
        pid = stack.pop()
        tree.append(pid)
        stack.extend(children.get(pid, []))
    return tree


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


class AgentProcess:
    """Spouští a zabíjí aplikaci i sidecar jako jeden strom procesů."""

    def __init__(self, env: Dict[str, str]) -> None:
        self.env = env
        self.proc: Optional[subprocess.Popen] = None
        self.generation = 0
        LOGS.mkdir(exist_ok=True)

    def start(self) -> None:
        self.generation += 1
        log = open(LOGS / f"app-gen{self.generation}.log", "w", encoding="utf-8")
        cmd = [
            "dapr", "run",
            "--app-id", APP_ID,
            "--app-port", str(APP_PORT),
            "--dapr-http-port", str(DAPR_HTTP),
            "--dapr-grpc-port", str(DAPR_GRPC),
            "--resources-path", str(HERE / "resources"),
            "--", sys.executable, "app.py",
        ]
        note(f"start gen{self.generation}: {' '.join(cmd[:4])} … (log {log.name})")
        self.proc = subprocess.Popen(
            cmd, cwd=HERE, env=self.env, stdout=log, stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        self._wait_ready()

    def _wait_ready(self) -> None:
        deadline = time.monotonic() + READY_TIMEOUT
        last = ""
        while time.monotonic() < deadline:
            if self.proc and self.proc.poll() is not None:
                raise SystemExit(
                    f"dapr run skončil s kódem {self.proc.returncode} – viz logs/"
                )
            try:
                side = httpx.get(f"{SIDECAR}/v1.0/healthz", timeout=2)
                app = httpx.get(f"{BASE}/hitl/approvals", timeout=2)
                if side.status_code in (200, 204) and app.status_code == 200:
                    note(f"ready za {READY_TIMEOUT - (deadline - time.monotonic()):.0f} s")
                    return
                last = f"sidecar={side.status_code} app={app.status_code}"
            except httpx.HTTPError as exc:
                last = str(exc)
            time.sleep(1)
        raise SystemExit(f"aplikace nenaběhla do {READY_TIMEOUT} s ({last})")

    def kill(self) -> None:
        """SIGKILL na celý strom procesů – aplikace i daprd umřou naráz (restart podu).

        `dapr run` spouští daprd i aplikaci každý ve vlastní procesní skupině,
        takže killpg na skupinu CLI je nezabije (ověřeno 2026-10-21, Dapr CLI 1.18.0).
        """
        assert self.proc is not None
        tree = _process_tree(self.proc.pid)
        note(f"SIGKILL stromu procesů {tree} (gen{self.generation})")
        for pid in tree:
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        self.proc.wait(timeout=30)
        self._wait_ports_free()
        alive = [pid for pid in tree if _pid_alive(pid)]
        if alive:
            raise SystemExit(f"po SIGKILL stále žijí procesy {alive} – restart by byl falešný")

    def stop(self) -> None:
        if self.proc is None or self.proc.poll() is not None:
            return
        try:
            os.killpg(os.getpgid(self.proc.pid), signal.SIGTERM)
            self.proc.wait(timeout=30)
        except Exception:  # noqa: BLE001
            os.killpg(os.getpgid(self.proc.pid), signal.SIGKILL)
        self._wait_ports_free()

    def _wait_ports_free(self) -> None:
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            busy = []
            for url in (f"{SIDECAR}/v1.0/healthz", f"{BASE}/hitl/approvals"):
                try:
                    httpx.get(url, timeout=1)
                    busy.append(url)
                except httpx.HTTPError:
                    pass
            if not busy:
                return
            time.sleep(0.5)
        raise SystemExit(f"porty stále obsluhuje starý proces: {busy}")

    def restart(self) -> float:
        t0 = time.monotonic()
        self.kill()
        self.start()
        return time.monotonic() - t0


# ----------------------------------------------------------------------------
# HTTP client to the served agent
# ----------------------------------------------------------------------------


class Agent:
    def __init__(self) -> None:
        self.http = httpx.Client(timeout=60)

    def start_run(self, task: str, session_id: str) -> str:
        r = self.http.post(
            f"{BASE}/agent/run", json={"task": task, "session_id": session_id}
        )
        r.raise_for_status()
        return r.json()["instance_id"]

    def status(self, instance_id: str) -> Dict[str, Any]:
        r = self.http.get(f"{BASE}/agent/instances/{instance_id}")
        r.raise_for_status()
        return r.json()

    def wait_finished(self, instance_id: str, timeout: float) -> Dict[str, Any]:
        deadline = time.monotonic() + timeout
        last: Dict[str, Any] = {}
        while time.monotonic() < deadline:
            try:
                last = self.status(instance_id)
            except httpx.HTTPError:
                time.sleep(2)
                continue
            if last.get("runtime_status") in FINISHED:
                return last
            time.sleep(2)
        last.setdefault("runtime_status", "TIMEOUT")
        return last

    @staticmethod
    def output_text(state: Dict[str, Any]) -> str:
        raw = state.get("serialized_output") or state.get("output") or ""
        if isinstance(raw, str):
            try:
                parsed = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                return raw
            raw = parsed
        if isinstance(raw, dict):
            for key in ("content", "output", "result", "text"):
                if isinstance(raw.get(key), str):
                    return raw[key]
        return json.dumps(raw, ensure_ascii=False)

    def pending(self) -> List[Dict[str, Any]]:
        r = self.http.get(f"{BASE}/hitl/approvals")
        r.raise_for_status()
        return r.json()

    def wait_pending(self, instance_id: str, timeout: float) -> Optional[Dict[str, Any]]:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            for p in self.pending():
                if p.get("instance_id") == instance_id:
                    return p
            try:
                if self.status(instance_id).get("runtime_status") in FINISHED:
                    return None
            except httpx.HTTPError:
                pass
            time.sleep(1)
        return None

    def respond(
        self, instance_id: str, approval_request_id: str, approved: bool, reason: str
    ) -> str:
        """Vrátí cestu, kterou rozhodnutí prošlo: 'http' nebo 'sidecar-raiseEvent'."""
        r = self.http.post(
            f"{BASE}/hitl/approvals/{approval_request_id}/respond",
            json={"approved": approved, "reason": reason},
        )
        if r.status_code == 200:
            return "http"
        note(f"/respond vrátil {r.status_code}: {r.text[:160]} → fallback na sidecar")
        r2 = self.http.post(
            f"{SIDECAR}/v1.0-beta1/workflows/dapr/{instance_id}"
            f"/raiseEvent/approval_response_{approval_request_id}",
            json={
                "approval_request_id": approval_request_id,
                "approved": approved,
                "reason": reason,
            },
        )
        r2.raise_for_status()
        return "sidecar-raiseEvent"


def redis_session_keys(session_hint: str) -> Dict[str, Any]:
    """Důkaz, že transcript leží v Redisu, ne v procesu. Nezávislé na SDK."""
    try:
        import redis  # type: ignore
    except ImportError:
        return {"available": False}
    try:
        r = redis.Redis(host="localhost", port=6379, decode_responses=False)
        keys = [k.decode() for k in r.scan_iter("claude-session:*")]
        sizes = {k: r.memory_usage(k) or 0 for k in keys[:50]}
        return {
            "available": True,
            "keys_total": len(keys),
            "keys_for_session": [k for k in keys if session_hint in k],
            "bytes_sampled": sum(sizes.values()),
        }
    except Exception as exc:  # noqa: BLE001
        return {"available": False, "error": str(exc)}


# ----------------------------------------------------------------------------
# Scenarios
# ----------------------------------------------------------------------------


class Ctx:
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.session_id = args.session_id or str(uuid.uuid4())
        self.ledger = Ledger(RESULTS / "ledger.jsonl")
        env = dict(os.environ)
        env["HARNESS_LEDGER"] = str(self.ledger.path)
        env.setdefault("CLAUDE_MODEL", "claude-haiku-4-5")
        env.setdefault("APPROVAL_TIMEOUT_SECONDS", str(7 * 24 * 3600))
        env["SLOW_TOOL_SECONDS"] = "0"
        self.env = env
        self.proc = AgentProcess(env)
        self.agent = Agent()
        self.asked_weather = False

    def run_turn(self, task: str, label: str) -> str:
        iid = self.agent.start_run(task, self.session_id)
        state = self.agent.wait_finished(iid, RUN_TIMEOUT)
        text = self.agent.output_text(state)
        note(f"{label}: status={state.get('runtime_status')} → {text[:140]!r}")
        evidence.setdefault("turns", []).append(
            {"label": label, "instance_id": iid, "status": state.get("runtime_status"), "text": text}
        )
        return text


def scenario_smoke(ctx: Ctx) -> None:
    section("S0 smoke: nástroj + obnovení session (T1)")
    t1 = ctx.run_turn(TASK_WEATHER, "turn1")
    ctx.asked_weather = True
    verdict("T0 nástroj", "22" in t1 or "sunny" in t1.lower(), f"odpověď zmiňuje počasí: {t1[:80]!r}")
    t2 = ctx.run_turn(TASK_RESUME, "turn2")
    verdict("T1 session resume", "paris" in t2.lower(), f"druhý běh si pamatuje Paříž: {t2[:80]!r}")
    evidence["redis_after_smoke"] = redis_session_keys(ctx.session_id)
    note(f"redis: {evidence['redis_after_smoke']}")


def scenario_restart_while_waiting(ctx: Ctx, pause_seconds: int = 0) -> None:
    title = "S4 long-pause" if pause_seconds else "S1 restart-while-waiting"
    section(f"{title}: SIGKILL při čekání na schválení (T2, T3, T4)")
    ctx.ledger.reset()
    iid = ctx.agent.start_run(TASK_TRANSFER, ctx.session_id)
    pending = ctx.agent.wait_pending(iid, APPROVAL_WAIT)
    if pending is None:
        verdict("T2 schvalovací bod", False, "Claude transfer_money nezavolal, nebo běh skončil dřív")
        return
    rid = pending["approval_request_id"]
    note(f"pending: tool={pending.get('step_name')} args={pending.get('tool_arguments')} rid={rid}")
    evidence["pending_before_restart"] = pending

    if pause_seconds:
        note(f"pauza {pause_seconds} s před restartem (polovina), druhá polovina po něm")
        time.sleep(pause_seconds / 2)

    downtime = ctx.proc.restart()
    note(f"restart trval {downtime:.1f} s")
    evidence["restart_seconds"] = downtime

    if pause_seconds:
        time.sleep(pause_seconds / 2)

    after = [p for p in ctx.agent.pending() if p.get("instance_id") == iid]
    restored = any(p.get("approval_request_id") == rid for p in after)
    verdict(
        "T2 pending přežije restart",
        restored,
        f"GET /hitl/approvals po restartu: {len(after)} záznam(ů) pro instanci, "
        f"stejné request_id={restored}",
    )
    status_after = ctx.agent.status(iid).get("runtime_status")
    note(f"stav workflow po restartu: {status_after}")
    evidence["status_after_restart"] = status_after

    path = ctx.agent.respond(iid, rid, True, "harness approve after restart")
    note(f"rozhodnutí doručeno cestou: {path}")
    evidence["respond_path"] = path
    state = ctx.agent.wait_finished(iid, RUN_TIMEOUT)
    text = ctx.agent.output_text(state)
    starts, ends = ctx.ledger.count("start"), ctx.ledger.count("end")
    verdict(
        "T3 dokončení po restartu",
        state.get("runtime_status") == "COMPLETED",
        f"status={state.get('runtime_status')} výstup={text[:100]!r}",
    )
    verdict(
        "T3 nástroj přesně jednou",
        starts == 1 and ends == 1,
        f"ledger start={starts} end={ends} (pid: {[e.get('pid') for e in ctx.ledger.entries()]})",
    )
    evidence["ledger_s1"] = ctx.ledger.entries()

    recall = ctx.run_turn(TASK_RECALL, "recall-after-restart")
    low = recall.lower()
    remembers_transfer = "alice" in low or "25" in low
    remembers_paris = "paris" in low
    verdict(
        "T4 transcript drží historii",
        remembers_transfer and (remembers_paris or not ctx.asked_weather),
        f"follow-up (Paříž v této session: {ctx.asked_weather}): {recall[:120]!r}",
    )
    evidence["redis_after_restart"] = redis_session_keys(ctx.session_id)


def scenario_restart_during_tool(ctx: Ctx) -> None:
    section("S2 restart-during-tool: SIGKILL uprostřed běhu schváleného nástroje (T5)")
    ctx.ledger.reset()
    slow = ctx.args.slow_tool_seconds
    ctx.env["SLOW_TOOL_SECONDS"] = str(slow)
    ctx.proc.restart()  # aby app načetla SLOW_TOOL_SECONDS
    iid = ctx.agent.start_run(TASK_TRANSFER + " (second transfer)", ctx.session_id)
    pending = ctx.agent.wait_pending(iid, APPROVAL_WAIT)
    if pending is None:
        verdict("T5 schvalovací bod", False, "bez schvalovacího bodu nelze měřit")
        ctx.env["SLOW_TOOL_SECONDS"] = "0"
        return
    rid = pending["approval_request_id"]
    ctx.agent.respond(iid, rid, True, "harness approve before kill")
    if not ctx.ledger.wait_for("start", 90):
        verdict("T5 nástroj začal", False, "ledger 'start' se neobjevil do 90 s po schválení")
        ctx.env["SLOW_TOOL_SECONDS"] = "0"
        return
    note("nástroj běží (start zapsán) → SIGKILL za 2 s")
    time.sleep(2)
    ctx.env["SLOW_TOOL_SECONDS"] = "0"
    ctx.proc.restart()

    # Po restartu buď workflow doběhne, nebo si Claude vyžádá nové schválení.
    deadline = time.monotonic() + RUN_TIMEOUT
    second_pending = None
    state: Dict[str, Any] = {}
    while time.monotonic() < deadline:
        state = ctx.agent.status(iid)
        if state.get("runtime_status") in FINISHED:
            break
        for p in ctx.agent.pending():
            if p.get("instance_id") == iid and p.get("approval_request_id") != rid:
                second_pending = p
                break
        if second_pending:
            note(f"po restartu NOVÁ žádost o schválení rid={second_pending['approval_request_id']}")
            ctx.agent.respond(iid, second_pending["approval_request_id"], True, "harness re-approve")
            state = ctx.agent.wait_finished(iid, RUN_TIMEOUT)
            break
        time.sleep(2)

    starts, ends = ctx.ledger.count("start"), ctx.ledger.count("end")
    evidence["ledger_s2"] = ctx.ledger.entries()
    evidence["s2_second_approval"] = second_pending
    verdict(
        "T5 dokončení po restartu během nástroje",
        state.get("runtime_status") == "COMPLETED",
        f"status={state.get('runtime_status')} nové schválení={'ano' if second_pending else 'ne'}",
    )
    if starts == 1 and ends == 1:
        verdict("T5 sémantika", True, "exactly-once: nástroj dokončen jednou (nečekané – ověř log)")
    elif starts >= 2:
        verdict(
            "T5 sémantika", None,
            f"AT-LEAST-ONCE: nástroj spuštěn {starts}×, dokončen {ends}× → idempotency key na naší straně",
        )
    else:
        verdict("T5 sémantika", False, f"nástroj nedoběhl: start={starts} end={ends}")


def scenario_deny(ctx: Ctx) -> None:
    section("S3 deny: zamítnutí → nástroj neproběhne (T6)")
    ctx.ledger.reset()
    iid = ctx.agent.start_run("Send $40 to Bob for the concert.", ctx.session_id)
    pending = ctx.agent.wait_pending(iid, APPROVAL_WAIT)
    if pending is None:
        verdict("T6 schvalovací bod", False, "bez schvalovacího bodu")
        return
    ctx.agent.respond(iid, pending["approval_request_id"], False, "harness deny")
    state = ctx.agent.wait_finished(iid, RUN_TIMEOUT)
    text = ctx.agent.output_text(state)
    starts = ctx.ledger.count("start")
    verdict("T6 nástroj neproběhl", starts == 0, f"ledger start={starts}")
    verdict(
        "T6 Claude zamítnutí respektuje",
        state.get("runtime_status") == "COMPLETED" and ctx.ledger.count("start") == 0,
        f"status={state.get('runtime_status')} výstup={text[:100]!r}",
    )
    evidence["ledger_s3"] = ctx.ledger.entries()


SCENARIOS = {
    "smoke": scenario_smoke,
    "restart-while-waiting": scenario_restart_while_waiting,
    "restart-during-tool": scenario_restart_during_tool,
    "deny": scenario_deny,
    "long-pause": lambda ctx: scenario_restart_while_waiting(ctx, ctx.args.pause_seconds),
}
ORDER_ALL = ["smoke", "restart-while-waiting", "deny", "restart-during-tool"]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--scenario", default="all", choices=["all", *SCENARIOS])
    ap.add_argument("--session-id", help="pokračovat v existující Claude session")
    ap.add_argument("--pause-seconds", type=int, default=120, help="pro long-pause")
    ap.add_argument("--slow-tool-seconds", type=int, default=20, help="pro restart-during-tool")
    ap.add_argument("--keep-running", action="store_true", help="nezastavovat app na konci")
    args = ap.parse_args()

    RESULTS.mkdir(exist_ok=True)
    ctx = Ctx(args)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    evidence.update(
        {
            "started": stamp,
            "session_id": ctx.session_id,
            "model": ctx.env.get("CLAUDE_MODEL"),
            "dapr_agents": _pkg_version("dapr-agents"),
            "claude_agent_sdk": _pkg_version("claude-agent-sdk"),
            "dapr_cli": _cmd(["dapr", "--version"]),
        }
    )
    print(f"session_id={ctx.session_id}  model={evidence['model']}  "
          f"dapr-agents={evidence['dapr_agents']}  claude-agent-sdk={evidence['claude_agent_sdk']}")

    ctx.proc.start()
    try:
        for name in (ORDER_ALL if args.scenario == "all" else [args.scenario]):
            try:
                SCENARIOS[name](ctx)
            except Exception as exc:  # noqa: BLE001
                verdict(f"{name} – běh harnessu", False, f"výjimka: {exc!r}")
    finally:
        if not args.keep_running:
            ctx.proc.stop()

    out = RESULTS / f"{args.scenario}-{stamp}.json"
    out.write_text(
        json.dumps({"results": results, "evidence": evidence}, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    section("Souhrn")
    ok = sum(1 for r in results if r["ok"] is True)
    bad = sum(1 for r in results if r["ok"] is False)
    unclear = sum(1 for r in results if r["ok"] is None)
    print(f"  potvrzeno {ok}, vyvráceno {bad}, nejasné {unclear} → {out}")
    return 1 if bad else 0


def _pkg_version(name: str) -> str:
    try:
        from importlib.metadata import version
        return version(name)
    except Exception:  # noqa: BLE001
        return "?"


def _cmd(cmd: List[str]) -> str:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=10).stdout.strip().replace("\n", " ")[:80]
    except Exception:  # noqa: BLE001
        return "?"


if __name__ == "__main__":
    sys.exit(main())
