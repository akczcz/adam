# Harness G1: věrnost Anthropic Messages API přes model gateway

Ověřuje kritérium G1 z `knowledge/gateway/kriteria.md` pro kandidáty z kola 2
(`knowledge/gateway/overview.md`): **co gateway udělá s requestem Claude Agent SDK
na cestě k poskytovateli.** Referenční kontrakt je
[code.claude.com/docs/en/llm-gateway-protocol](https://code.claude.com/docs/en/llm-gateway-protocol).

Cíl není porovnat „kvalitu“ gateway, ale falsifikovat tvrzení z dokumentace:
„podporuje Anthropic“ znamená u každého kandidáta něco jiného a tichá ztráta
`cache_control` nebo beta hlavičky se pozná až na faktuře.

## Dva režimy

| Režim | Upstream | Co měří | Potřebuje |
|---|---|---|---|
| `mock` (default) | `mock_upstream.py` – záznamník, ne model | **přenos**: hlavičky, tělo, stream, chybová těla, usage, latence | nic, zdarma |
| `live` | `api.anthropic.com` (nebo `--upstream` pro Azure Foundry `/anthropic`) | prompt cache přes gateway vs. napřímo (`usage.cache_read_input_tokens`) | `ANTHROPIC_API_KEY`, řádově centy |

V obou režimech se navíc spustí **Claude Agent SDK** (bundlované Claude Code CLI) přes gateway
s jedním in-process MCP nástrojem (`A1`). V `mock` režimu mock odpovídá podle protokolu Claude Code:
nejdřív `ToolSearch` (MCP nástroje jsou deferred), pak `mcp__harness__lookup_ticket`, pak text.

## Kontroly

| # | Tvrzení | Kritérium |
|---|---|---|
| K1, K1a–f | Tělo requestu dorazí upstream beze změny | diff klíčů prázdný; `cache_control` v `system` i `messages`; pořadí `system` bloků; `tools`; neznámé pole `context_management`; `metadata.user_id`; `model` |
| K2a | `anthropic-beta` je otevřený seznam | hodnota identická včetně neznámé bety `harness-unknown-beta-2099-01-01` |
| K2b | `anthropic-version` forwardován | identický |
| K2c | Atribuční hlavičky `x-claude-code-session-id/agent-id/parent-agent-id` | všechny tři identické |
| K2d–f | `traceparent`, auth k upstreamu, hlavičky navíc | jen informativní |
| K3a–b | Odpověď vč. `usage.cache_*` doručena klientovi beze změny | pole přítomná, `id`/`stop_reason`/`content` nezměněné |
| K4a–e | Stream: pořadí eventů, `ping` propuštěny, nebufferováno, usage v `message_delta`, tělo upstream | první event dorazí dřív než 80 % celku |
| K5a–b | Chybová těla 400 a 529 **neobalena** | status, `error.type` i `error.message` identické |
| K6 | `count_tokens` passthrough | 200 a hodnota z mocku |
| K7 | Latence non-stream P50/P95 | informativní; mock bez prodlevy |
| A1–A2 | Claude Agent SDK přes gateway dokončí turn s nástrojem | nástroj proveden ≥ 1×, `is_error=false` |
| L1 (live) | Prompt cache funguje přes gateway | 2. volání má `cache_read_input_tokens > 0` přímo i přes gateway |

Kontrolní běh `--gateway direct` (klient → upstream bez gateway) musí projít na 100 %;
jinak je chyba v harnessu, ne v gateway.

## Výsledky 2026-10-22 (mock, Linux x86_64, agentgateway 1.6.0, LiteLLM 1.106.2)

| Cesta | PASS | FAIL | Co selhalo |
|---|---|---|---|
| direct | 21 | 0 | – |
| **agentgateway 1.6.0** | **21** | **0** | – ; `traceparent` propagován jako child span (stejné trace id, nový span id); latence p50 +0,7 ms proti direct |
| LiteLLM 1.106.2 (nativní `/v1/messages`) | 16 | 5 | K2a beta hlavička **přeuspořádána a doplněna** o `context-management-2025-06-27` (neznámá beta zachována); K2c atribuční hlavičky **zahozeny**; K4a vlastní `ping` před `message_start`; K5a tělo 400 obaleno textem `litellm.BadRequestError: AnthropicException - {...}`; K5b **529 → 500 `api_error`**; `traceparent` k upstreamu zahozen; hlavičky odpovědi (`request-id`) nepropagovány; latence p50 +13 ms |

Detail v `results/*.json`. Live režim (L1) v tomto běhu **neproveden** – prostředí nemělo `ANTHROPIC_API_KEY`.

## Prerekvizity

- Python 3.11–3.13, `uv`
- binárka `agentgateway` (GitHub releases, `agentgateway-linux-amd64` / `-darwin-arm64`) – cesta v `AGENTGATEWAY_BIN`
- volné porty 9777 (mock), 4100 (agentgateway), 4200 (LiteLLM), 19001–19002 (agentgateway readiness/stats)
- live: `ANTHROPIC_API_KEY`

```bash
cd tools/harness_gateway_g1
uv venv && uv pip install -p .venv/bin/python httpx fastapi uvicorn pyyaml anthropic "litellm[proxy]" claude-agent-sdk
export AGENTGATEWAY_BIN=/path/to/agentgateway

.venv/bin/python harness.py --gateway direct          # kontrola harnessu
.venv/bin/python harness.py --gateway agentgateway
.venv/bin/python harness.py --gateway litellm
ANTHROPIC_API_KEY=sk-ant-... .venv/bin/python harness.py --gateway agentgateway --mode live
```

## Pasti, které harness odhalil (a obchází)

- **agentgateway v kontejneru bez IPv6** padá na `bind [::]:port` – `config.enableIpv6: false`.
- **agentgateway `baseUrl` bez cesty** přepíše výchozí prefix `/v1` prázdným řetězcem a volá `/messages` –
  v configu musí být `baseUrl: http://host:port/v1`.
- **LiteLLM bez databáze** odmítne jakýkoliv Bearer token kromě `master_key` chybou „No connected db“ –
  Claude Code CLI posílá klíč jako `Authorization: Bearer`, takže pro A1 musí být klíč = master key.
- **Claude Code CLI v hostovaném prostředí** (claude.ai cloud, `CLAUDE_CODE_PROVIDER_MANAGED_BY_HOST`)
  ignoruje `ANTHROPIC_API_KEY` a posílá OAuth token relace; `CLAUDE_CODE_OAUTH_TOKEN` ho přebije.
  Na běžném stroji s `ANTHROPIC_API_KEY` tohle není potřeba.
- **MCP nástroje jsou v Claude Code deferred** – v `tools` requestu je jen `ToolSearch` a
  `DeferredToolPlaceholder`; mock to musí respektovat, jinak nástroj nikdy nezavolá.
- Harness ruší `HTTP(S)_PROXY` pro `mock` režim a nastavuje `NO_PROXY=127.0.0.1`, jinak jde lokální
  provoz přes firemní proxy.
- `litellm[proxy]` instaluje `litellm-enterprise` (`LicenseRef-Proprietary`) jako závislost –
  tady 0.1.76.post1 vedle litellm 1.106.2; harness to vypisuje do `meta.gateway_version`.
