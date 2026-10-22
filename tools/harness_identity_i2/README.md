# Harness I2: propagace identity uživatele agent → gateway → MCP server

Ověřuje návrh vrstvy identity z `knowledge/identity/overview.md`: identita uživatele je OAuth token
z IdP (Keycloak), **token exchange (RFC 8693) dělá agentgateway**, MCP server přijme jen token
s vlastní audience (RFC 8707), autorizace per nástroj je politika mimo prompt (CEL v gateway
nebo OPA jako PDP) a audit vzniká automaticky v gateway a v OPA decision logu.

Celý řetěz běží lokálně bez Dockeru: Keycloak 26.8.1 (`start-dev --import-realm`), mock MCP
resource server (`mock_mcp.py`), agentgateway 1.6.0, OPA-Envoy 1.21.2.

## Tvrzení, která harness falsifikuje

| # | Tvrzení | Kritérium |
|---|---|---|
| I0 | Subject token uživatele nemá audience MCP serveru | `aud` bez `mcp-tickets` |
| I2a | Passthrough uživatelského tokenu MCP server odmítne | 401, `aud_mismatch` |
| I2b | Po exchange dorazí k MCP token `aud=mcp-tickets`, `sub`=uživatel, `azp=gateway`; MCP přijme | 200 + claimy v záznamu mocku |
| I2b' | Scope doručený MCP ⊆ scope uživatele | množinové porovnání |
| I2c | Keycloak V2 exchange bez enforceru umí **upscope** | informativní (past) |
| I2d | S `downscope-assertion-grant-enforcer` je upscope odmítnut | 400 `invalid_scope` |
| I2d' | Enforcer vyžaduje i audience v subject tokenu | informativní (konflikt s I2a) |
| I2e | `act` claim nese agenta (RFC 8693 delegace) | claim přítomen |
| I2f / I2f' | `delete_ticket` zamítnut na gateway (MCP ho nevidí), `lookup_ticket` projde | 403 / 200 |
| I2g / I2g' | Audit: gateway log nese `sub` a rozhodnutí; OPA decision log nese `decision_id` | grep logů |
| I2i | Neplatný token gateway odmítne před exchange | 401 |
| I2j | Výpadek PDP: gateway fail-closed s odlišitelným stavem | 503 (`failureMode.denyWithStatus`) |
| I2h | Latence `tools/call` přes gateway vč. exchange | informativní |

## Výsledky 2026-10-22

| Cesta | PASS/FAIL | Co selhalo / nálezy |
|---|---|---|
| `--path direct` (harness = gateway) | 4/1 | **I2e** – `act` nevzniká: Keycloak 26.8 delegaci má jen jako preview (`token-exchange-delegation`), vyžaduje souhlas uživatele v prohlížeči a FGAP V2 permission; `actor_token` bez feature se tiše ignoruje, s feature je odmítnut („Client is not within the token audience“). **I2c** upscope potvrzen (alice dostala `tickets:write`). **I2d'** enforcer odmítne i audience, kterou subject token nemá → s enforcerem musí uživatelův token nést audience každého MCP serveru. Latence exchange p50 58 ms. |
| `--path agentgateway --authz cel` | 6/1 | jen I2e. CEL nad JSON-RPC tělem (`json(request.body).params.name`) **funguje** na HTTP routě. Latence p50 81 ms. |
| `--path agentgateway --authz opa` | 8/1 | jen I2e. OPA dostane JWT claimy i parsované tělo; `dynamic_metadata` z Rego se objeví v gateway logu jako `authz.decision/tool/reason`; výpadek OPA → 503. Latence p50 71 ms. |

Detail v `results/*.json`.

## Pasti, které harness odhalil

- **Keycloak realm import s `clientScopes` nevytvoří vestavěné scopes** (`basic`, `profile`, `email`) – tiše je ignoruje
  („Referenced client scope 'basic' doesn't exist. Ignoring“) a token nemá `sub`. Scope `basic` s `oidc-sub-mapper` musí být v JSON.
- **Keycloak V2 exchange:** subject token musí mít requester (gateway) v `aud`; parametr `audience` jen filtruje, audience
  přidává mapper; bez enforceru lze **upscopovat**; enforcer kontroluje scope **i audience** vůči subject tokenu.
- **Keycloak delegace** (`act`): preview, souhlas uživatele při každém přihlášení, FGAP V2 – pro autonomní agenty dnes nepoužitelná.
- **agentgateway:** politika se ve standalone configu jmenuje `jwtAuth` (ne `jwtAuthentication` jako v CRD); default `mode: optional`
  pustí request bez tokenu; po validaci je token z hlavičky odstraněn → `subjectToken.source.expression: jwt.rawToken.unredacted()`.
- **OPA-Envoy 1.21.2 posílá input v camelCase** (`metadataContext.filterMetadata`), dokumentace uvádí snake_case;
  politika musí číst obojí, jinak je rozhodnutí „undefined“ a gateway vrátí 503.
- Rego výsledek musí být definovaný i pro requesty bez nástroje – `object.get` s defaulty, jinak undefined = výpadek PDP.

## Prerekvizity a spuštění

- Java 21, Python 3.11–3.13, `uv`
- Keycloak 26.8.1 rozbalený (`KC_HOME`), binárky `agentgateway` 1.6.0 (`AGENTGATEWAY_BIN`) a `opa-envoy` (`OPA_BIN`,
  release `v1.21.2-envoy-3`, asset `opa_envoy_linux_amd64`)
- volné porty 8080 (Keycloak), 9800 (mock MCP), 4300 (gateway), 8181/9191 (OPA), 19001–19002

```bash
cd tools/harness_identity_i2
uv venv && uv pip install -p .venv/bin/python httpx fastapi uvicorn pyyaml "PyJWT[crypto]"
export KC_HOME=/path/keycloak-26.8.1 AGENTGATEWAY_BIN=/path/agentgateway OPA_BIN=/path/opa-envoy
.venv/bin/python harness.py --path direct
.venv/bin/python harness.py --path agentgateway --authz cel
.venv/bin/python harness.py --path agentgateway --authz opa
.venv/bin/python harness.py --path direct --kc-features token-exchange-delegation,parameterized-scopes   # delegace preview
```

Harness každý běh smaže dev DB Keycloaku (`data/h2`) a importuje `configs/realm-platform.json` znovu.
