---
tema: agentgateway jako PEP identity – jwtAuth, extAuthz (OPA), authorization CEL, oauthTokenExchange (RFC 8693) ve standalone configu
naposledy_overeno: 2026-10-22
zralost: stable (1.6.0; schéma z main @bf1032b9 ověřeno na tagu v1.6.0; změřeno harnessem)
primarni_zdroje:
  - https://github.com/agentgateway/agentgateway/blob/main/schema/config.md
  - https://github.com/agentgateway/agentgateway/blob/main/schema/cel.md
  - https://github.com/agentgateway/agentgateway/tree/main/examples/traffic-token-exchange
  - https://github.com/agentgateway/agentgateway/blob/main/examples/mcp-authzen/config.yaml
  - https://github.com/envoyproxy/envoy/blob/main/api/envoy/service/auth/v3/external_auth.proto
  - https://github.com/open-policy-agent/opa-envoy-plugin
---

# agentgateway jako místo identity

## Účel
Jeden Policy Enforcement Point pro I2 (token exchange), I3 (rozhodnutí PDP) a I4 (JSON log) – agentní kód
identitu nenese, jen posílá uživatelův token a volitelně vlastní SVID.

## Aktuální stav
1.6.0 stable (2026-10-02), 1.7.0-alpha.1 (2026-10-21). Vše níže **změřeno** harnessem `tools/harness_identity_i2/`
(`configs/agentgateway-cel.yaml`, `configs/agentgateway-opa.yaml`).

## Klíčové koncepty

Pořadí filtrů na routě: `jwtAuth → extAuthz → authorization (CEL) → … → backendAuth` (backend fáze).

| Pole | Co dělá | Pasti |
|---|---|---|
| `policies.jwtAuth` | validace JWT (issuer, audiences, JWKS url/file, `requiredClaims`) | **standalone název je `jwtAuth`**, CRD má `jwtAuthentication`; default `mode: optional` **pustí request bez tokenu** → `strict`; po validaci je token **z hlavičky odstraněn** (`preserveToken: false` default) |
| `backends[].policies.backendAuth.oauthTokenExchange` | RFC 8693 (`grantType: tokenExchange`) nebo RFC 7523; `clientAuth` (secret basic/post, `privateKeyJwt`); `subjectToken.source`, `actorToken.source` (jen z requestu: header/query/cookie/CEL – **žádný soubor ani Workload API**), `audiences`, `scopes`, `resources`, `requestedTokenType` (bez něj se neposílá), `cache` | subject token po `jwtAuth` není v hlavičce → `subjectToken.source.expression: jwt.rawToken.unredacted()` |
| `policies.authorization.rules[]` | CEL `allow/require/deny` nad `jwt.*`, `request.*`, `extauthz.*`, `source.spiffeId` | `json(request.body).params.name` **funguje** na HTTP routě (změřeno); u MCP backendu navíc `mcp.tool.name` **i `mcp.tool.arguments`** |
| `policies.extAuthz` | Envoy ext_authz gRPC/HTTP; posílá hlavičky, `includeRequestBody`, JWT claims ve `filter_metadata["envoy.filters.http.jwt_authn"].jwt_payload`; `failureMode.denyWithStatus` | default fail-closed 403, timeout 2 s; OPA `dynamic_metadata` → CEL `extauthz.*` i do logu |
| `config.logging.fields.add` | CEL mapa do JSON logu (`user.sub: jwt.sub`, `authz.decision: extauthz.decision`) | I4 zadarmo |

## Místo v architektuře
```mermaid
sequenceDiagram
    participant A as Agent (Claude Agent SDK)
    participant GW as agentgateway 1.6
    participant OPA as OPA-Envoy (ext_authz gRPC)
    participant KC as Keycloak
    participant MCP as MCP server (aud=mcp-tickets)
    A->>GW: POST /mcp, Bearer userAT (+ x-agent-token)
    GW->>GW: jwtAuth strict (JWKS Keycloak); token odstraněn z hlavičky
    GW->>OPA: Check{parsed_body JSON-RPC, jwt_payload, headers}
    OPA-->>GW: allowed + dynamic_metadata{decision,tool,reason}; decision log
    GW->>GW: authorization: require extauthz.decision == true
    GW->>KC: token-exchange subject=jwt.rawToken, audience=mcp-tickets, scope=tickets:read
    KC-->>GW: AT aud=mcp-tickets, sub=uživatel, azp=gateway
    GW->>MCP: POST /mcp, Bearer AT
    MCP->>MCP: validuje iss, aud; MUST NOT passthrough
```

## Zralost a rizika (změřeno 2026-10-22)
- CEL i OPA varianta: `delete_ticket` zamítnut před MCP (403), `lookup_ticket` projde, MCP vidí `aud=mcp-tickets`,
  `sub` uživatele, `azp=gateway`, scope ⊆ scope uživatele; neplatný token 401 před exchange; výpadek OPA → 503.
- **OPA-Envoy 1.21.2 posílá input v camelCase** (`metadataContext.filterMetadata`), docs uvádějí snake_case; politika
  musí číst obojí, jinak „undefined decision“ = výpadek PDP.
- `act` claim nevzniká – limit Keycloaku ([keycloak.md](keycloak.md)), ne gateway; `actorToken` z hlavičky gateway posílá.
- Latence `tools/call` přes gateway p50 71–81 ms (z toho exchange ~58 ms) – cache exchange zřejmě neúčinná, ověřit.
- `extAuthz` nemá vlastní `timeout` pole (přes backend `http.requestTimeout`); `failureMode` YAML pro `allow` neověřen.

## Architektonické důsledky
1. Rego politika je **jedna** pro oba PEP: OPA za `extAuthz` v gateway a REST `POST /v1/data/envoy/authz/result`
   z `PreToolUse` hooku Agent SDK (stejný input: `parsed_body`, `jwt_payload`).
2. Identita agenta (SVID) putuje jako druhý credential v hlavičce; gateway ji loguje a OPA vyhodnocuje; do tokenu
   ji Keycloak dnes nevloží.
3. Cena odchodu: Rego přenositelné (AuthZEN HTTP varianta existuje), RFC 8693 parametry standardní (Keycloak ↔
   Zitadel ↔ Entra mění jen `path`, `clientAuth`); YAML schéma gateway není standard.

## Otevřené otázky
- [ ] Cache exchange: proč p50 přes gateway ≈ exchange + 15 ms; `cache.defaultTtl` vs. `expires_in`.
- [ ] `privateKeyJwt` / `backendTLS.spiffe` vůči Keycloak token endpointu (gateway s vlastním SVID místo secretu).
- [ ] MCP backend (`backends[].mcp`) místo HTTP: `mcpAuthorization` s `mcp.tool.arguments`.

## Changelog
- 2026-10-22: první verze (kolo 2 + harness I2).
