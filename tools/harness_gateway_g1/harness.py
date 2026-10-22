"""
Harness G1 – věrnost Anthropic Messages API přes model gateway.

Měří, co gateway udělá s requestem Claude Agent SDK na cestě k poskytovateli,
podle kontraktu https://code.claude.com/docs/en/llm-gateway-protocol:
beta hlavičky jako otevřený seznam, cache_control, pořadí `system`, `ping`
eventy nebufferované, chybová těla neobalená, atribuční hlavičky.

Dva režimy:
  mock  (default) – upstream je mock_upstream.py; nic nestojí, nepotřebuje klíč.
                    Kontroluje *přenos*, ne chování modelu.
  live            – upstream je api.anthropic.com; potřebuje ANTHROPIC_API_KEY.
                    Porovná `usage` (cache) přímo vs. přes gateway.

Gateway: agentgateway | litellm | direct (klient mluví s upstreamem napřímo –
kontrolní běh, který musí projít na 100 %, jinak je chyba v harnessu).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import signal
import socket
import statistics
import subprocess
import sys
import time
from pathlib import Path

import httpx

HERE = Path(__file__).resolve().parent
RESULTS = HERE / "results"
LOGS = HERE / "logs"
MOCK_PORT = 9777
GW_PORTS = {"agentgateway": 4100, "litellm": 4200}

BETA_HEADER = "prompt-caching-2024-07-31,harness-unknown-beta-2099-01-01"
ATTRIB = {
    "x-claude-code-session-id": "sess-harness-001",
    "x-claude-code-agent-id": "agent-harness-001",
    "x-claude-code-parent-agent-id": "agent-harness-000",
}
TRACEPARENT = "00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01"

TOOL = {
    "name": "lookup_ticket",
    "description": "Najde ticket podle id.",
    "input_schema": {"type": "object", "properties": {"ticket_id": {"type": "string"}}, "required": ["ticket_id"]},
}


def canonical_request(model: str, stream: bool = False) -> dict:
    """Request ve tvaru, jaký posílá Claude Code: system jako pole bloků s cache_control,
    nástroje, metadata.user_id a jedno pole, které gateway nemusí znát."""
    return {
        "model": model,
        "max_tokens": 64,
        "system": [
            {"type": "text", "text": "Jsi harness. Odpovídej stručně."},
            {"type": "text", "text": "Druhý blok – dlouhý kontext, který se cachuje. " * 8, "cache_control": {"type": "ephemeral"}},
        ],
        "messages": [
            {"role": "user", "content": [{"type": "text", "text": "Najdi ticket T-1.", "cache_control": {"type": "ephemeral", "ttl": "1h"}}]},
        ],
        "tools": [TOOL],
        "tool_choice": {"type": "auto"},
        "metadata": {"user_id": "harness-user-42"},
        "temperature": 0,
        "context_management": {"edits": [{"type": "clear_tool_uses_20250919"}]},
        "stream": stream,
    }


# ---------- infrastruktura ----------

def port_free(port: int) -> bool:
    with socket.socket() as s:
        return s.connect_ex(("127.0.0.1", port)) != 0


def wait_http(url: str, timeout: float = 60, ok=(200,)) -> bool:
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            r = httpx.get(url, timeout=2)
            if r.status_code in ok:
                return True
        except Exception:
            pass
        time.sleep(0.5)
    return False


class Proc:
    def __init__(self, name: str, cmd: list[str], env: dict, log: Path):
        self.name = name
        self.log = open(log, "wb")
        self.p = subprocess.Popen(cmd, env=env, stdout=self.log, stderr=subprocess.STDOUT, start_new_session=True)

    def stop(self):
        try:
            os.killpg(self.p.pid, signal.SIGTERM)
            self.p.wait(timeout=10)
        except Exception:
            try:
                os.killpg(self.p.pid, signal.SIGKILL)
            except Exception:
                pass
        self.log.close()


def start_mock(env: dict) -> Proc:
    assert port_free(MOCK_PORT), f"port {MOCK_PORT} obsazen"
    p = Proc("mock", [sys.executable, str(HERE / "mock_upstream.py")], env | {"MOCK_PORT": str(MOCK_PORT)}, LOGS / "mock.log")
    assert wait_http(f"http://127.0.0.1:{MOCK_PORT}/health", 30), "mock nenaběhl"
    return p


def render(template: Path, out: Path, **kw) -> Path:
    txt = template.read_text()
    for k, v in kw.items():
        txt = txt.replace("{{" + k + "}}", str(v))
    out.write_text(txt)
    return out


def start_gateway(name: str, upstream: str, env: dict, agentgateway_bin: str) -> tuple[Proc, str]:
    port = GW_PORTS[name]
    assert port_free(port), f"port {port} obsazen"
    cfg_dir = LOGS / "cfg"
    cfg_dir.mkdir(exist_ok=True)
    if name == "agentgateway":
        cfg = render(HERE / "configs/agentgateway.yaml", cfg_dir / "agentgateway.yaml", UPSTREAM=upstream, PORT=port)
        p = Proc(name, [agentgateway_bin, "-f", str(cfg)], env, LOGS / "agentgateway.log")
        assert wait_http("http://127.0.0.1:19001/healthz/ready", 60), "agentgateway není ready (viz logs/agentgateway.log)"
        base = f"http://127.0.0.1:{port}"
    elif name == "litellm":
        cfg = render(HERE / "configs/litellm.yaml", cfg_dir / "litellm.yaml", UPSTREAM=upstream)
        lenv = env | {
            "ANTHROPIC_API_BASE": upstream,            # pro passthrough /anthropic/*
            "LITELLM_LOCAL_MODEL_COST_MAP": "True",    # žádný fetch ceníku z GitHubu
            "LITELLM_TELEMETRY_DISABLED": "true",
            "NO_DOCS": "True",
        }
        p = Proc(name, [str(HERE / ".venv/bin/litellm"), "--config", str(cfg), "--port", str(port), "--host", "127.0.0.1"], lenv, LOGS / "litellm.log")
        assert wait_http(f"http://127.0.0.1:{port}/health/liveliness", 120), "litellm není ready (viz logs/litellm.log)"
        base = f"http://127.0.0.1:{port}"
    else:
        raise ValueError(name)
    return p, base


# ---------- kontroly ----------

class Report:
    def __init__(self):
        self.checks: list[dict] = []

    def add(self, cid: str, name: str, status: str, detail):
        self.checks.append({"id": cid, "name": name, "status": status, "detail": detail})
        mark = {"PASS": "✅", "FAIL": "❌", "INFO": "ℹ️", "SKIP": "⏭️"}[status]
        print(f"  {mark} {cid} {name}: {json.dumps(detail, ensure_ascii=False)[:300]}")


def mock_requests() -> list[dict]:
    return httpx.get(f"http://127.0.0.1:{MOCK_PORT}/_debug/requests").json()


def mock_clear():
    httpx.delete(f"http://127.0.0.1:{MOCK_PORT}/_debug/requests")


def client_headers(api_key: str) -> dict:
    return {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "anthropic-beta": BETA_HEADER,
        "content-type": "application/json",
        "traceparent": TRACEPARENT,
        **ATTRIB,
    }


def diff_keys(sent: dict, got: dict, prefix="") -> list[str]:
    out = []
    for k in sent:
        if k not in got:
            out.append(f"missing {prefix}{k}")
        elif isinstance(sent[k], dict) and isinstance(got[k], dict):
            out.extend(diff_keys(sent[k], got[k], f"{prefix}{k}."))
        elif sent[k] != got[k]:
            out.append(f"changed {prefix}{k}")
    for k in got:
        if k not in sent:
            out.append(f"added {prefix}{k}")
    return out


def check_mock(base: str, api_key: str, model: str, rep: Report, n_latency: int):
    url = f"{base}/v1/messages"
    hdr = client_headers(api_key)

    # K1 + K2: tělo a hlavičky, non-stream
    mock_clear()
    req = canonical_request(model)
    r = httpx.post(url, headers=hdr, json=req, timeout=30)
    rec = mock_requests()
    if r.status_code != 200 or not rec or rec[-1]["path"] != "/v1/messages":
        rep.add("K0", "Request přes gateway doručen upstream", "FAIL", {"status": r.status_code, "body": r.text[:300], "upstream_requests": [(x["path"], x["method"]) for x in rec]})
        return
    got = rec[-1]
    body = got["body"] or {}
    diffs = diff_keys({k: v for k, v in req.items() if k != "stream"}, {k: v for k, v in body.items() if k != "stream"})
    rep.add("K1", "Tělo requestu doručeno beze změny", "PASS" if not diffs else "FAIL", {"diff": diffs})
    rep.add("K1a", "cache_control zachován (system i messages)", "PASS" if body.get("system", [{}, {}])[1].get("cache_control") == req["system"][1]["cache_control"] and body["messages"][0]["content"][0].get("cache_control") == req["messages"][0]["content"][0]["cache_control"] else "FAIL", {})
    rep.add("K1b", "system: pořadí a počet bloků zachován", "PASS" if body.get("system") == req["system"] else "FAIL", {"got": body.get("system")})
    rep.add("K1c", "tools + input_schema beze změny", "PASS" if body.get("tools") == req["tools"] else "FAIL", {})
    rep.add("K1d", "Neznámé pole (context_management) forwardováno", "PASS" if body.get("context_management") == req["context_management"] else "FAIL", {"got": body.get("context_management")})
    rep.add("K1e", "metadata.user_id forwardován", "PASS" if (body.get("metadata") or {}).get("user_id") == "harness-user-42" else "FAIL", {"got": body.get("metadata")})
    rep.add("K1f", "model beze změny", "PASS" if body.get("model") == model else "FAIL", {"got": body.get("model")})

    h = got["headers"]
    rep.add("K2a", "anthropic-beta forwardován jako otevřený seznam", "PASS" if h.get("anthropic-beta") == BETA_HEADER else "FAIL", {"got": h.get("anthropic-beta")})
    rep.add("K2b", "anthropic-version forwardován", "PASS" if h.get("anthropic-version") == "2023-06-01" else "FAIL", {"got": h.get("anthropic-version")})
    rep.add("K2c", "Atribuční hlavičky x-claude-code-* forwardovány", "PASS" if all(h.get(k) == v for k, v in ATTRIB.items()) else "FAIL", {"got": {k: h.get(k) for k in ATTRIB}})
    tp = h.get("traceparent")
    rep.add("K2d", "traceparent k upstreamu", "INFO", {"got": tp, "same_trace_id": bool(tp) and tp.split("-")[1] == TRACEPARENT.split("-")[1], "unchanged": tp == TRACEPARENT})
    rep.add("K2e", "Autentizace k upstreamu", "INFO", {"x-api-key": "present" if h.get("x-api-key") else "absent", "authorization": "present" if h.get("authorization") else "absent"})
    rep.add("K2f", "Hlavičky navíc od gateway", "INFO", {"extra": sorted(k for k in h if k not in hdr and k not in ("host", "content-length", "accept", "accept-encoding", "user-agent", "connection"))})

    # K3: odpověď non-stream
    resp = r.json()
    u = resp.get("usage", {})
    rep.add("K3a", "usage vč. cache polí doručeno klientovi", "PASS" if u.get("cache_read_input_tokens") == 4096 and u.get("cache_creation_input_tokens") == 2048 and u.get("cache_creation") else "FAIL", {"usage": u})
    rep.add("K3b", "Odpověď: id, stop_reason, content beze změny", "PASS" if resp.get("stop_reason") == "tool_use" and resp.get("content", [{}])[-1].get("type") == "tool_use" and str(resp.get("id", "")).startswith("msg_mock_") else "FAIL", {"id": resp.get("id"), "stop_reason": resp.get("stop_reason")})
    rep.add("K3c", "Hlavičky odpovědi upstreamu (request-id, x-mock-upstream)", "INFO", {"request-id": r.headers.get("request-id"), "x-mock-upstream": r.headers.get("x-mock-upstream")})

    # K4: streaming
    mock_clear()
    events, t_first, t0 = [], None, time.perf_counter()
    with httpx.stream("POST", url, headers=hdr, json=canonical_request(model, stream=True), timeout=60) as s:
        status = s.status_code
        for line in s.iter_lines():
            if line.startswith("event:"):
                if t_first is None:
                    t_first = time.perf_counter() - t0
                events.append(line.split(":", 1)[1].strip())
            elif line.startswith("data:") and '"message_delta"' in line:
                md_usage = json.loads(line[5:]).get("usage")
    total = time.perf_counter() - t0
    pings = events.count("ping")
    expected_min_total = float(os.getenv("MOCK_EVENT_DELAY", "0.25")) * 6
    buffered = t_first is not None and t_first > total * 0.8 and total > expected_min_total * 0.8
    rep.add("K4a", "Stream: status 200 a pořadí eventů", "PASS" if status == 200 and events[:1] == ["message_start"] and events[-1:] == ["message_stop"] else "FAIL", {"status": status, "events": events})
    rep.add("K4b", "Stream: ping eventy propuštěny", "PASS" if pings >= 2 else ("INFO" if pings == 1 else "FAIL"), {"pings": pings})
    rep.add("K4c", "Stream: nebufferováno (první event dorazí dřív než celek)", "FAIL" if buffered else "PASS", {"t_first_s": round(t_first or -1, 3), "t_total_s": round(total, 3)})
    rep.add("K4d", "Stream: usage v message_delta vč. cache polí", "PASS" if md_usage and md_usage.get("cache_read_input_tokens") == 4096 else "FAIL", {"usage": md_usage})
    rec = mock_requests()
    rep.add("K4e", "Stream: tělo doručeno upstream beze změny", "PASS" if rec and not diff_keys(canonical_request(model, True), rec[-1]["body"] or {}) else "FAIL", {"diff": diff_keys(canonical_request(model, True), (rec or [{}])[-1].get("body") or {}) if rec else "no upstream request"})

    # K5: chybová těla
    for cid, mdl, code, etype in (("K5a", "mock-error", 400, "invalid_request_error"), ("K5b", "mock-overloaded", 529, "overloaded_error")):
        r = httpx.post(url, headers=hdr, json=canonical_request(mdl), timeout=30)
        try:
            j = r.json()
        except Exception:
            j = {"_raw": r.text[:200]}
        e = j.get("error") or {}
        exact_msg = {"mock-error": "mock: deliberately invalid request", "mock-overloaded": "Overloaded"}[mdl]
        ok = r.status_code == code and j.get("type") == "error" and e.get("type") == etype and e.get("message") == exact_msg
        partial = r.status_code == code and e.get("type") == etype
        rep.add(cid, f"Chybové tělo {code} {etype} neobaleno", "PASS" if ok else "FAIL", {"status": r.status_code, "status_and_type_preserved": partial, "message_unchanged": e.get("message") == exact_msg, "body": j})

    # K6: count_tokens
    r = httpx.post(f"{base}/v1/messages/count_tokens", headers=hdr, json={"model": model, "messages": [{"role": "user", "content": "x"}]}, timeout=30)
    rep.add("K6", "count_tokens passthrough", "PASS" if r.status_code == 200 and r.json().get("input_tokens") == 4242 else "FAIL", {"status": r.status_code, "body": r.text[:200]})

    # K7: režie (mock bez prodlevy, non-stream)
    lat = []
    small = {"model": model, "max_tokens": 8, "messages": [{"role": "user", "content": "hi"}]}
    with httpx.Client(timeout=30) as c:
        for _ in range(n_latency):
            t = time.perf_counter()
            c.post(url, headers=hdr, json=small)
            lat.append((time.perf_counter() - t) * 1000)
    rep.add("K7", "Latence non-stream přes tuto cestu (ms)", "INFO", {"n": n_latency, "p50": round(statistics.median(lat), 2), "p95": round(sorted(lat)[int(len(lat) * 0.95) - 1], 2)})


async def check_agent_sdk(base: str, api_key: str, model: str, rep: Report, live: bool):
    """A1: Claude Agent SDK (bundlované Claude Code CLI) přes gateway dokončí jeden turn s nástrojem."""
    try:
        from claude_agent_sdk import ClaudeAgentOptions, ResultMessage, AssistantMessage, ToolUseBlock, create_sdk_mcp_server, query, tool
    except Exception as e:
        rep.add("A1", "Claude Agent SDK přes gateway", "SKIP", {"reason": f"claude-agent-sdk nelze importovat: {e}"})
        return

    calls = []

    @tool("lookup_ticket", "Najde ticket podle id.", {"ticket_id": str})
    async def lookup_ticket(args):
        calls.append(args)
        return {"content": [{"type": "text", "text": f"Ticket {args.get('ticket_id')}: OPEN"}]}

    server = create_sdk_mcp_server("harness", "1.0.0", [lookup_ticket])
    env = {
        "ANTHROPIC_BASE_URL": base,
        "ANTHROPIC_API_KEY": api_key,
        "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
        "DISABLE_TELEMETRY": "1",
    }
    if os.environ.get("ANTHROPIC_WORKSPACE_ID"):
        # Uživatelský klíč (sk-ant-usr-…) bez vazby na workspace: API vyžaduje anthropic-workspace-id.
        env["ANTHROPIC_CUSTOM_HEADERS"] = f"anthropic-workspace-id: {os.environ['ANTHROPIC_WORKSPACE_ID']}"
    if os.environ.get("CLAUDE_CODE_PROVIDER_MANAGED_BY_HOST"):
        # Claude Code v hostovaném prostředí (claude.ai cloud) ignoruje ANTHROPIC_API_KEY a posílá
        # OAuth token relace jako Bearer. CLAUDE_CODE_OAUTH_TOKEN ho přebije – ověřeno 2026-10-22.
        env["CLAUDE_CODE_OAUTH_TOKEN"] = api_key
    opts = ClaudeAgentOptions(
        model=model,
        env=env,
        mcp_servers={"harness": server},
        allowed_tools=["mcp__harness__lookup_ticket"],
        permission_mode="bypassPermissions",
        max_turns=6,
        system_prompt="Jsi harness. Na dotaz o ticketu vždy použij nástroj lookup_ticket a pak odpověz jednou větou.",
    )
    mock_clear() if not live else None
    tool_uses, result, err = [], None, None
    t0 = time.perf_counter()
    try:
        async for m in query(prompt="Jaký je stav ticketu T-1?", options=opts):
            if isinstance(m, AssistantMessage):
                tool_uses += [b.name for b in m.content if isinstance(b, ToolUseBlock)]
            if isinstance(m, ResultMessage):
                result = m
    except Exception as e:
        err = f"{type(e).__name__}: {e}"
    dt = time.perf_counter() - t0
    detail = {
        "seconds": round(dt, 1),
        "error": err,
        "tool_uses": tool_uses,
        "tool_calls_executed": len(calls),
        "num_turns": getattr(result, "num_turns", None),
        "is_error": getattr(result, "is_error", None),
        "usage": getattr(result, "usage", None),
        "total_cost_usd": getattr(result, "total_cost_usd", None),
    }
    ok = err is None and result is not None and not result.is_error and len(calls) >= 1
    rep.add("A1", "Claude Agent SDK přes gateway: turn s nástrojem doběhl", "PASS" if ok else "FAIL", detail)
    if not live:
        rec = mock_requests()
        betas = sorted({r["headers"].get("anthropic-beta", "") for r in rec if r["path"] == "/v1/messages"})
        rep.add("A2", "Agent SDK: requesty doručené upstream (mock)", "INFO", {"count": len(rec), "paths": sorted({r["path"] for r in rec}), "anthropic-beta_seen_upstream": betas, "user_agent": sorted({r["headers"].get("user-agent", "") for r in rec})[:2]})


def check_live(base: str, api_key: str, model: str, rep: Report, direct_base: str):
    """L1: usage s prompt cache přímo vs. přes gateway (stejný request 2×, druhý má mít cache_read)."""
    from anthropic import Anthropic

    big = ("Interní směrnice č. 42 o zpracování ticketů. " * 400)  # ~4–5k tokenů, nad minimem pro cache
    def run(b):
        hdrs = dict(ATTRIB)
        if os.environ.get("ANTHROPIC_WORKSPACE_ID"):
            hdrs["anthropic-workspace-id"] = os.environ["ANTHROPIC_WORKSPACE_ID"]
        c = Anthropic(base_url=b, api_key=api_key, default_headers=hdrs)
        out = []
        for _ in range(2):
            m = c.messages.create(model=model, max_tokens=16, system=[{"type": "text", "text": big, "cache_control": {"type": "ephemeral"}}], messages=[{"role": "user", "content": "Odpověz jedním slovem: OK"}])
            out.append(m.usage.model_dump())
        return out
    try:
        d = run(direct_base)
        g = run(base)
    except Exception as e:
        rep.add("L1", "Live: usage přímo vs. přes gateway", "FAIL", {"error": f"{type(e).__name__}: {e}"})
        return
    ok = (g[1].get("cache_read_input_tokens") or 0) > 0 and (d[1].get("cache_read_input_tokens") or 0) > 0
    rep.add("L1", "Live: prompt cache funguje přes gateway (2. volání má cache_read > 0)", "PASS" if ok else "FAIL", {"direct": d, "gateway": g})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gateway", choices=["direct", "agentgateway", "litellm"], required=True)
    ap.add_argument("--mode", choices=["mock", "live"], default="mock")
    ap.add_argument("--model", default="claude-haiku-4-5")
    ap.add_argument("--agentgateway-bin", default=os.getenv("AGENTGATEWAY_BIN", shutil.which("agentgateway") or ""))
    ap.add_argument("--skip-agent-sdk", action="store_true")
    ap.add_argument("--latency-n", type=int, default=20)
    ap.add_argument("--upstream", default="https://api.anthropic.com", help="live: upstream (např. Azure Foundry /anthropic)")
    a = ap.parse_args()

    RESULTS.mkdir(exist_ok=True)
    LOGS.mkdir(exist_ok=True)
    env = {k: v for k, v in os.environ.items() if k not in ("ANTHROPIC_BASE_URL",)}
    for k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
        env.pop(k, None) if a.mode == "mock" else None
    env["NO_PROXY"] = env["no_proxy"] = "127.0.0.1,localhost," + env.get("NO_PROXY", "")

    if a.mode == "mock":
        api_key = "sk-ant-harness-mock"
        upstream = f"http://127.0.0.1:{MOCK_PORT}"
    else:
        api_key = os.environ.get("ANTHROPIC_API_KEY") or ""
        if not api_key:
            print("live režim potřebuje ANTHROPIC_API_KEY"); sys.exit(2)
        upstream = a.upstream
    env["ANTHROPIC_API_KEY"] = api_key
    os.environ["NO_PROXY"] = os.environ["no_proxy"] = env["NO_PROXY"]

    rep = Report()
    procs: list[Proc] = []
    meta = {"gateway": a.gateway, "mode": a.mode, "model": a.model, "upstream": upstream, "started": time.strftime("%Y-%m-%dT%H:%M:%S")}
    try:
        if a.mode == "mock":
            procs.append(start_mock(env))
        if a.gateway == "direct":
            base = upstream
            client_key = api_key
        else:
            if a.gateway == "agentgateway" and not a.agentgateway_bin:
                print("chybí binárka agentgateway (--agentgateway-bin nebo AGENTGATEWAY_BIN)"); sys.exit(2)
            p, base = start_gateway(a.gateway, upstream, env, a.agentgateway_bin)
            procs.append(p)
            client_key = "sk-harness-master" if a.gateway == "litellm" else api_key
            meta["gateway_version"] = gateway_version(a.gateway, a.agentgateway_bin)
        print(f"== {a.gateway} / {a.mode} / {a.model} / base={base}")
        if a.mode == "mock":
            check_mock(base, client_key, a.model, rep, a.latency_n)
        else:
            check_live(base, client_key, a.model, rep, upstream)
        if not a.skip_agent_sdk:
            asyncio.run(check_agent_sdk(base, client_key, a.model, rep, a.mode == "live"))
    finally:
        for p in reversed(procs):
            p.stop()
    out = RESULTS / f"{a.gateway}-{a.mode}-{time.strftime('%Y%m%d-%H%M%S')}.json"
    out.write_text(json.dumps({"meta": meta, "checks": rep.checks}, ensure_ascii=False, indent=1))
    n = {s: sum(1 for c in rep.checks if c["status"] == s) for s in ("PASS", "FAIL", "INFO", "SKIP")}
    print(f"== výsledek: {n}  -> {out.relative_to(HERE)}")


def gateway_version(name: str, agw_bin: str) -> str:
    try:
        if name == "agentgateway":
            return json.loads(subprocess.check_output([agw_bin, "--version"], text=True)).get("version", "?")
        from importlib.metadata import version
        return f"litellm {version('litellm')} (+ litellm-enterprise {version('litellm-enterprise')})"
    except Exception as e:
        return f"? ({e})"


if __name__ == "__main__":
    main()
