"""
Harness O1 – souvislý trace přes celý řetěz do ClickHouse.

Řetěz: orchestrátor (OTEL SDK, span `invoke_agent`) → Claude Agent SDK (injekce TRACEPARENT do CLI)
→ Claude Code CLI (traces beta, CLAUDE_CODE_PROPAGATE_TRACEPARENT) → agentgateway (SERVER span, gen_ai.*)
→ mock model. Všechny spany jdou do OTEL Collectoru (gen_ai_normalizer → redaction → clickhouse + file)
a harness je dotazem do ClickHouse ověří.

Tvrzení:
  O1a  Spany z orchestrátoru i agentgateway sdílejí jeden trace_id
  O1b  Claude Code CLI emituje vlastní spany do stejného trace (beta)
  O1c  Gateway span nese gen_ai.usage.* vč. cache tokenů a cost
  O1d  Rodičovský řetěz: gateway span → CLI span (nebo root), ne osiřelý
  O1e  Redaction v Collectoru zamaskuje tajemství v atributu (sk-…)
  O1f  gen_ai_normalizer přepíše OpenInference atributy na gen_ai.*
  O1g  Mock model dostal traceparent se stejným trace_id (propagace CLI → gateway → model)
  O1h  CLI metriky/eventy (cost, tokeny) dorazily přes OTLP (informativní)
  O1i  Dapr Workflow v řetězu – NEMĚŘENO (bez Dapr lokálně), viz standardy.md

Komponenty spouští harness: ClickHouse (CLICKHOUSE_BIN), otelcol-contrib (OTELCOL_BIN),
agentgateway (AGENTGATEWAY_BIN), mock_upstream.py z harness_gateway_g1.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx

HERE = Path(__file__).resolve().parent
G1 = HERE.parent / "harness_gateway_g1"
RESULTS, LOGS, DATA, CFG = HERE / "results", HERE / "logs", HERE / "data", HERE / "logs" / "cfg"
MOCK_PORT, GW_PORT, CH_HTTP, OTLP_HTTP = 9777, 4100, 8123, 4318


def port_free(port: int) -> bool:
    with socket.socket() as s:
        return s.connect_ex(("127.0.0.1", port)) != 0


def wait_http(url: str, timeout: float, ok=(200,)) -> bool:
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            if httpx.get(url, timeout=2).status_code in ok:
                return True
        except Exception:
            pass
        time.sleep(0.5)
    return False


class Proc:
    def __init__(self, name, cmd, env, log, cwd=None):
        self.name, self.log = name, open(log, "wb")
        self.p = subprocess.Popen(cmd, env=env, cwd=cwd, stdout=self.log, stderr=subprocess.STDOUT, start_new_session=True)

    def stop(self):
        try:
            os.killpg(self.p.pid, signal.SIGTERM); self.p.wait(timeout=20)
        except Exception:
            try: os.killpg(self.p.pid, signal.SIGKILL)
            except Exception: pass
        self.log.close()


def render(src: Path, dst: Path, **kw) -> Path:
    txt = src.read_text()
    for k, v in kw.items():
        txt = txt.replace("{{" + k + "}}", str(v))
    dst.write_text(txt)
    return dst


class Report:
    def __init__(self): self.checks = []
    def add(self, cid, name, status, detail):
        self.checks.append({"id": cid, "name": name, "status": status, "detail": detail})
        print(f"  {dict(PASS='✅', FAIL='❌', INFO='ℹ️', SKIP='⏭️')[status]} {cid} {name}: {json.dumps(detail, ensure_ascii=False)[:340]}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--clickhouse-bin", default=os.getenv("CLICKHOUSE_BIN", shutil.which("clickhouse") or ""))
    ap.add_argument("--otelcol-bin", default=os.getenv("OTELCOL_BIN", shutil.which("otelcol-contrib") or ""))
    ap.add_argument("--agentgateway-bin", default=os.getenv("AGENTGATEWAY_BIN", shutil.which("agentgateway") or ""))
    ap.add_argument("--model", default="claude-haiku-4-5")
    a = ap.parse_args()
    for n, v in (("CLICKHOUSE_BIN", a.clickhouse_bin), ("OTELCOL_BIN", a.otelcol_bin), ("AGENTGATEWAY_BIN", a.agentgateway_bin)):
        if not v: print(f"chybí {n}"); sys.exit(2)
    for d in (RESULTS, LOGS, CFG): d.mkdir(parents=True, exist_ok=True)
    shutil.rmtree(DATA, ignore_errors=True); DATA.mkdir()
    for f in ("spans.jsonl", "metrics.jsonl", "logs.jsonl"):
        (LOGS / f).unlink(missing_ok=True)

    env = {k: v for k, v in os.environ.items() if k not in ("ANTHROPIC_BASE_URL", "HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "JAVA_TOOL_OPTIONS")}
    env["NO_PROXY"] = env["no_proxy"] = "127.0.0.1,localhost"
    os.environ["NO_PROXY"] = os.environ["no_proxy"] = env["NO_PROXY"]
    api_key = "sk-ant-harness-mock"
    env["ANTHROPIC_API_KEY"] = api_key
    rep, procs = Report(), []
    try:
        for port in (MOCK_PORT, GW_PORT, CH_HTTP, OTLP_HTTP, 9000, 4317):
            assert port_free(port), f"port {port} obsazen"
        ch_cfg = render(HERE / "configs/clickhouse-config.xml", CFG / "clickhouse-config.xml", DATA=str(DATA))
        procs.append(Proc("clickhouse", [a.clickhouse_bin, "server", f"--config-file={ch_cfg}"], env, LOGS / "clickhouse.log", cwd=str(DATA)))
        assert wait_http(f"http://127.0.0.1:{CH_HTTP}/ping", 60), "ClickHouse nenaběhl (logs/clickhouse.log)"
        httpx.post(f"http://127.0.0.1:{CH_HTTP}/", content="CREATE DATABASE IF NOT EXISTS otel", timeout=10).raise_for_status()
        col_cfg = render(HERE / "configs/otelcol.yaml", CFG / "otelcol.yaml", LOGS=str(LOGS))
        procs.append(Proc("otelcol", [a.otelcol_bin, "--config", str(col_cfg)], env, LOGS / "otelcol.log"))
        assert wait_http(f"http://127.0.0.1:{OTLP_HTTP}/v1/traces", 30, ok=(405, 415, 400, 200)), "otelcol nenaběhl (logs/otelcol.log)"
        procs.append(Proc("mock", [sys.executable, str(G1 / "mock_upstream.py")], env | {"MOCK_PORT": str(MOCK_PORT), "MOCK_EVENT_DELAY": "0.05"}, LOGS / "mock.log"))
        assert wait_http(f"http://127.0.0.1:{MOCK_PORT}/health", 30), "mock nenaběhl"
        gw_cfg = render(HERE / "configs/agentgateway.yaml", CFG / "agentgateway.yaml", PORT=GW_PORT, UPSTREAM=f"http://127.0.0.1:{MOCK_PORT}")
        procs.append(Proc("agentgateway", [a.agentgateway_bin, "-f", str(gw_cfg)], env, LOGS / "agentgateway.log"))
        assert wait_http("http://127.0.0.1:19001/healthz/ready", 60), "agentgateway není ready"
        print("== komponenty běží: clickhouse, otelcol, mock, agentgateway")

        trace_id, root_span_id, sdk = run_agent(a.model, api_key, env, rep)
        time.sleep(8)  # flush exportérů (CLI exportuje při ukončení, Collector batch 1 s)
        check_clickhouse(trace_id, root_span_id, rep, sdk)
    finally:
        for p in reversed(procs):
            p.stop()
    out = RESULTS / f"o1-{time.strftime('%Y%m%d-%H%M%S')}.json"
    out.write_text(json.dumps({"meta": {"started": time.strftime("%Y-%m-%dT%H:%M:%S"), "otelcol": "0.163.2", "clickhouse": "26.8.34.13-lts", "agentgateway": "1.6.0"}, "checks": rep.checks}, ensure_ascii=False, indent=1))
    n = {s: sum(1 for c in rep.checks if c["status"] == s) for s in ("PASS", "FAIL", "INFO", "SKIP")}
    print(f"== výsledek: {n} -> {out.relative_to(HERE)}")


def run_agent(model: str, api_key: str, env: dict, rep: Report):
    from opentelemetry import trace
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from claude_agent_sdk import ClaudeAgentOptions, ResultMessage, AssistantMessage, ToolUseBlock, create_sdk_mcp_server, query, tool

    provider = TracerProvider(resource=Resource.create({"service.name": "harness-orchestrator", "tenant.id": "t1"}))
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=f"http://127.0.0.1:{OTLP_HTTP}/v1/traces")))
    trace.set_tracer_provider(provider)
    tracer = trace.get_tracer("harness")

    # O1f: span s OpenInference atributy – Collector ho má normalizovat na gen_ai.*
    with tracer.start_as_current_span("openinference-probe") as sp:
        sp.set_attribute("openinference.span.kind", "LLM")
        sp.set_attribute("llm.model_name", "probe-model")
        sp.set_attribute("llm.token_count.prompt", 123)
        sp.set_attribute("llm.token_count.completion", 45)
        probe_trace = format(sp.get_span_context().trace_id, "032x")

    calls = []

    @tool("lookup_ticket", "Najde ticket podle id.", {"ticket_id": str})
    async def lookup_ticket(args):
        calls.append(args); return {"content": [{"type": "text", "text": f"Ticket {args.get('ticket_id')}: OPEN"}]}

    server = create_sdk_mcp_server("harness", "1.0.0", [lookup_ticket])
    cli_env = {
        "ANTHROPIC_BASE_URL": f"http://127.0.0.1:{GW_PORT}",
        "ANTHROPIC_API_KEY": api_key,
        "CLAUDE_CODE_ENABLE_TELEMETRY": "1",
        "CLAUDE_CODE_ENHANCED_TELEMETRY_BETA": "1",
        "OTEL_TRACES_EXPORTER": "otlp", "OTEL_METRICS_EXPORTER": "otlp", "OTEL_LOGS_EXPORTER": "otlp",
        "OTEL_EXPORTER_OTLP_PROTOCOL": "http/protobuf",
        "OTEL_EXPORTER_OTLP_ENDPOINT": f"http://127.0.0.1:{OTLP_HTTP}",
        "OTEL_METRIC_EXPORT_INTERVAL": "1000", "OTEL_LOGS_EXPORT_INTERVAL": "1000",
        "CLAUDE_CODE_PROPAGATE_TRACEPARENT": "1",
        "OTEL_RESOURCE_ATTRIBUTES": "enduser.id=alice,tenant.id=t1",
        "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
    }
    if os.environ.get("CLAUDE_CODE_PROVIDER_MANAGED_BY_HOST"):
        cli_env["CLAUDE_CODE_OAUTH_TOKEN"] = api_key  # hostované prostředí – viz harness G1 README
    opts = ClaudeAgentOptions(model=model, env=cli_env, mcp_servers={"harness": server}, allowed_tools=["mcp__harness__lookup_ticket"],
                              permission_mode="bypassPermissions", max_turns=6, system_prompt="Jsi harness. Na dotaz o ticketu použij lookup_ticket a odpověz jednou větou.")
    httpx.delete(f"http://127.0.0.1:{MOCK_PORT}/_debug/requests")

    async def go():
        tool_uses, result = [], None
        async for m in query(prompt="Jaký je stav ticketu T-1?", options=opts):
            if isinstance(m, AssistantMessage):
                tool_uses += [b.name for b in m.content if isinstance(b, ToolUseBlock)]
            if isinstance(m, ResultMessage):
                result = m
        return tool_uses, result

    with tracer.start_as_current_span("invoke_agent harness-ticket-agent") as root:
        root.set_attribute("gen_ai.operation.name", "invoke_agent")
        root.set_attribute("gen_ai.agent.name", "harness-ticket-agent")
        root.set_attribute("enduser.id", "alice")
        trace_id = format(root.get_span_context().trace_id, "032x")
        root_span_id = format(root.get_span_context().span_id, "016x")
        t0 = time.perf_counter()
        tool_uses, result = asyncio.run(go())
        dt = time.perf_counter() - t0
    provider.force_flush()
    sdk = {"seconds": round(dt, 1), "tool_uses": tool_uses, "tool_calls_executed": len(calls), "is_error": getattr(result, "is_error", None), "usage": getattr(result, "usage", None), "cost": getattr(result, "total_cost_usd", None)}
    rep.add("A1", "Claude Agent SDK přes agentgateway: turn s nástrojem doběhl", "PASS" if result and not result.is_error and calls else "FAIL", sdk)
    rec = httpx.get(f"http://127.0.0.1:{MOCK_PORT}/_debug/requests").json()
    tps = [r["headers"].get("traceparent") for r in rec if r["path"] == "/v1/messages"]
    same = [tp for tp in tps if tp and tp.split("-")[1] == trace_id]
    rep.add("O1g", "Mock model dostal traceparent se stejným trace_id (CLI → gateway → model)", "PASS" if tps and len(same) == len(tps) else "FAIL", {"traceparents": tps[:3], "same_trace": len(same), "of": len(tps), "root_trace_id": trace_id})
    sdk["probe_trace"] = probe_trace
    return trace_id, root_span_id, sdk


def check_clickhouse(trace_id: str, root_span_id: str, rep: Report, sdk: dict):
    import clickhouse_connect
    c = clickhouse_connect.get_client(host="127.0.0.1", port=CH_HTTP, username="default", database="otel")
    rows = None
    for _ in range(20):
        try:
            rows = c.query("SELECT ServiceName, SpanName, SpanId, ParentSpanId, SpanAttributes, ResourceAttributes FROM otel.otel_traces WHERE TraceId = {t:String}", parameters={"t": trace_id}).result_rows
            if rows and len({r[0] for r in rows}) >= 2:
                break
        except Exception:
            pass
        time.sleep(2)
    rows = rows or []
    by_service = {}
    for r in rows:
        by_service.setdefault(r[0], []).append(r)
    rep.add("O1a", "Jeden trace_id: spany orchestrátoru i agentgateway v ClickHouse", "PASS" if "harness-orchestrator" in by_service and "agentgateway" in by_service else "FAIL", {"services": {k: len(v) for k, v in by_service.items()}, "span_names": sorted({r[1] for r in rows})[:12]})
    cli = [r for r in rows if r[0] not in ("harness-orchestrator", "agentgateway")]
    rep.add("O1b", "Claude Code CLI spany ve stejném trace (beta)", "PASS" if cli else "FAIL", {"cli_services": sorted({r[0] for r in cli}), "cli_span_names": sorted({r[1] for r in cli})[:10], "count": len(cli)})
    gw = by_service.get("agentgateway", [])
    gw_attrs = [r[4] for r in gw]
    has_usage = [a for a in gw_attrs if any(k.startswith("gen_ai.usage.") for k in a)]
    sample = next(( {k: v for k, v in a.items() if k.startswith(("gen_ai.", "session.", "agent.", "llm.cost", "harness."))} for a in has_usage), {})
    rep.add("O1c", "Gateway span nese gen_ai.usage.* vč. cache tokenů, session.id a cost", "PASS" if has_usage and any("cache" in k for k in sample) else ("INFO" if has_usage else "FAIL"), {"sample": sample})
    span_ids = {r[2] for r in rows}
    orphans = [r[1] for r in gw if r[3] not in span_ids and r[3] != ""]
    parents = sorted({next((x[0] + ":" + x[1] for x in rows if x[2] == r[3]), "?" + r[3][:6]) for r in gw})
    rep.add("O1d", "Gateway spany mají rodiče uvnitř trace (CLI span nebo root), nejsou osiřelé", "PASS" if gw and not orphans else "FAIL", {"gateway_parents": parents[:6], "orphans": orphans[:5]})
    leaked = [r[1] for r in rows if any("sk-SECRET" in str(v) for v in r[4].values())]
    masked = [r[4].get("harness.redaction_probe") for r in gw if "harness.redaction_probe" in r[4]]
    rep.add("O1e", "Redaction v Collectoru zamaskovala sk-… v atributu gateway spanu", "PASS" if gw and not leaked and masked and all("sk-SECRET" not in str(m) for m in masked) else "FAIL", {"masked_values": masked[:3], "leaked_spans": leaked[:3]})
    probe = c.query("SELECT SpanAttributes FROM otel.otel_traces WHERE TraceId = {t:String} AND SpanName = 'openinference-probe'", parameters={"t": sdk.get("probe_trace", "")}).result_rows
    pa = probe[0][0] if probe else {}
    rep.add("O1f", "gen_ai_normalizer: OpenInference llm.token_count.* → gen_ai.usage.*", "PASS" if pa.get("gen_ai.usage.input_tokens") == "123" else ("FAIL" if pa else "FAIL"), {"attrs": {k: v for k, v in pa.items() if k.startswith(("gen_ai", "llm.", "openinference"))}})
    mfile = LOGS / "metrics.jsonl"
    mtxt = mfile.read_text(errors="replace") if mfile.exists() else ""
    names = sorted({n for n in ("claude_code.cost.usage", "claude_code.token.usage", "claude_code.session.count") if n in mtxt})
    lfile = LOGS / "logs.jsonl"
    ltxt = lfile.read_text(errors="replace") if lfile.exists() else ""
    events = sorted({e for e in ("claude_code.api_request", "claude_code.tool_decision", "claude_code.tool_result", "claude_code.user_prompt") if e in ltxt})
    rep.add("O1h", "CLI metriky a eventy přes OTLP (cost, tokeny, tool_decision)", "PASS" if names and events else ("INFO" if names or events else "FAIL"), {"metrics": names, "events": events, "enduser_in_logs": "enduser.id" in ltxt or "alice" in ltxt})
    rep.add("O1i", "Dapr Workflow v řetězu", "SKIP", {"note": "bez Dapr lokálně; Dapr Agents serializují traceparent do vstupu workflow (standardy.md) – neměřeno"})


if __name__ == "__main__":
    main()
