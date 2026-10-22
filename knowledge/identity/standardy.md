---
tema: Standardy identity a autorizace pro AI agenty – MCP auth, A2A, OAuth token exchange, ID-JAG, SPIFFE, Entra Agent ID, co řeší zvolené komponenty
naposledy_overeno: 2026-10-22
zralost: mixed (MCP core auth stable; EMA/ID-JAG stable ext + IETF draft; A2A OBO nedefinováno; Entra Agent ID GA)
primarni_zdroje:
  - https://modelcontextprotocol.io/specification/2026-07-28/basic/authorization
  - https://github.com/modelcontextprotocol/ext-auth
  - https://a2a-protocol.org/latest/specification/
  - https://datatracker.ietf.org/doc/draft-ietf-oauth-identity-assertion-authz-grant/
  - https://datatracker.ietf.org/doc/draft-ietf-oauth-identity-chaining/
  - https://datatracker.ietf.org/doc/draft-ietf-wimse-aims/
  - https://github.com/openid/authzen
  - https://learn.microsoft.com/en-us/entra/agent-id/
  - https://docs.dapr.io/operations/security/
  - https://agentgateway.dev/docs/
  - https://code.claude.com/docs/en/agent-sdk/permissions
  - https://github.com/spiffe/spire/tree/main/support/oidc-discovery-provider
---

# Standardy identity a autorizace pro agenty

**Metodická poznámka (2026-10-22):** weby specifikací nebyly z rešeršního prostředí dostupné; vše ověřeno
ze **zdrojových repozitářů týchž dokumentů na GitHubu** (MCP spec @80041ab0, ext-auth @fb374c7d, A2A @98279d62,
IETF drafty z repozitářů autorů, MicrosoftDocs/entra-docs @e30bb475, dapr/docs @c725c76b, agentgateway/website
@3e6517fe, spiffe/spire @027ce1ed, keycloak @f7532e18) a z code.claude.com. Text RFC 8693 nečten přímo
(parametry z odkazů v draftech). Stavy IETF draftů na datatrackeru jsou ze search snippetů – označeno *neověřeno*.

## Závěr: standardizovaný je jen jeden hop

**Uživatel → MCP klient (agent) → MCP server** má úplnou normu. Vše ostatní – jak MCP server volá downstream API,
jak agent předá identitu uživatele jinému agentovi přes A2A, jak se identita dostane k modelu – spec **záměrně
neřeší**, nebo zakazuje zkratky (token passthrough je MUST NOT).

| Hop | Standard | Stav |
|---|---|---|
| Uživatel → agent → MCP server | MCP core auth: OAuth 2.1, RFC 9728 (MUST), RFC 8707 (MUST), PKCE S256 (MUST), CIMD (SHOULD), DCR deprecated | stable 2026-07-28 |
| Podnikový IdP → MCP server bez per-server consentu | MCP ext **Enterprise-Managed Authorization** = ID-JAG (draft-ietf-oauth-identity-assertion-authz-grant-04) | ext **Stable**; IETF adopted WG draft |
| Agent bez uživatele → MCP server | MCP ext **OAuth Client Credentials** (private_key_jwt RECOMMENDED) | ext **Draft** |
| Agent → agent (A2A v1.0.1) | §7: schémata v Agent Card; **identita uživatele v Task/Message není definovaná** | stable, OBO neřeší |
| Delegace napříč doménami | RFC 8693 (`actor_token`, `act`, `may_act`) + draft-ietf-oauth-identity-chaining-17 | RFC / RFC Ed Queue (*neověřeno*) |
| Identita workloadu | SPIFFE X.509/JWT-SVID; Dapr sentry `spiffe://<td>/ns/<ns>/<appid>` | stable |
| Agent v IdP zákazníka | **Entra Agent ID GA** (what's new 2026-05-01); OBO přes `jwt-bearer` + FIC | GA s limity |

**Co si platforma musí dostavět:**

1. **Vazba uživatel ↔ agent ↔ nástroj v jednom tokenu.** RFC 8693 `act` řetěz je definovaný, ale ID-JAG říká,
   že `actor_token` *povoluje, ale nenormuje*. Entra má vlastní claimy (`xms_act_fct`, `xms_par_app_azp`),
   Keycloak má delegaci jen jako preview (26.8). → Platforma zvolí profil (RFC 8693 s `act`) a vynutí ho v gateway.
2. **Identita uživatele v A2A.** Spec dává jen `TASK_STATE_AUTH_REQUIRED`, credentials chodí out-of-band.
   → Token exchange per hop v gateway, nebo vlastní A2A extension.
3. **MCP server jako OAuth klient k downstream API.** „MUST NOT pass through the token“; jak získat separátní
   token spec neříká. → agentgateway `oauthTokenExchange` / `crossAppAccess`, nebo Entra sidecar.
4. **Identita uživatele k modelu.** Žádný standard; jen `metadata.user_id` (Anthropic) a CEL atributy v gateway.
5. **Autorizace per nástroj / argument.** MCP core nemá; AuthZEN COAZ-MCP je Draft 1 (2026-02-13);
   agentgateway `backend.mcp.authorization` zná `mcp.tool.name`, ale **ne argumenty**; Dapr ACL jen App-ID → App-ID.
6. **Hloubka delegace, scope-down, revokace řetězu** – nikde normativně.

**Architektonicky:** identita uživatele = OAuth token z IdP zákazníka; identita agenta = SPIFFE SVID (Dapr sentry
nebo SPIRE); spojení obou = **token exchange v gateway**, ne v agentním kódu. Claude Agent SDK k identitě nenabízí
nic kromě hooks a statických hlaviček – je to PEP pro lokální rozhodnutí, ne nosič identity.

## A. MCP authorization 2026-07-28 (doslovně MUST/SHOULD)

- Autorizace **OPTIONAL**; HTTP transporty SHOULD, STDIO SHOULD NOT (credentials z prostředí).
- AS **MUST** OAuth 2.1 (`draft-ietf-oauth-v2-1-13`). AS a klienti **SHOULD** CIMD; DCR **MAY**, **deprecated**.
- MCP server **MUST** RFC 9728 (PRM s `authorization_servers`), 401 s `WWW-Authenticate: Bearer resource_metadata=…`
  nebo well-known; klient MUST obojí. AS MUST RFC 8414 nebo OIDC Discovery; `issuer` MUST identický.
- **RFC 8707:** klient MUST `resource` = kanonické URI MCP serveru v obou requestech, „regardless of whether
  authorization servers support it“.
- **PKCE:** MUST, MUST S256, MUST ověřit z metadat (chybí-li → refuse).
- **RFC 9207 (nové, SEP-2468):** klient MUST validovat `iss` při přítomnosti; upgrade na MUST pro AS avizován.
- Tokeny: Bearer v hlavičce MUST, v query MUST NOT; server MUST validovat audience; „MCP servers MUST NOT accept
  or transit any other tokens“; k upstream API **separátní token**, **MUST NOT pass through**. RFC 8693 v jádru **není** (jen roadmapa).
- Scope step-up: 403 + `insufficient_scope` (SHOULD). Client registration binding per issuer (SEP-2352).
- **Changelog:** 2025-06-18 DCR SHOULD, PRM a 8707 MUST → 2025-11-25 + OIDC Discovery, CIMD, step-up, extensions
  → 2026-07-28 + RFC 9207, DCR deprecated, AS binding. Draft je k auth textově identický.
- **Extensions (ext-auth):** Enterprise-Managed Authorization (ID-JAG) **Stable**: `audience` MUST = issuer Resource AS,
  vydaný token audience-restricted na MCP server; discovery `authorization_grant_profiles_supported: ["urn:ietf:params:oauth:grant-profile:id-jag"]`.
  OAuth Client Credentials **Draft**. Roadmapa: Agent Identity WG (forming) – DPoP, WIF (SEP-1933, otevřený PR), RFC 8693.

## B. A2A v1.0.1

- **SecurityScheme**: apiKey, http (bearer), oauth2 (`flows` REQUIRED, `oauth2_metadata_url`; authorization_code
  s `pkce_required`, client_credentials, device_code; implicit a password deprecated), openIdConnect, mutualTLS.
- §7: „Identity information is handled at the protocol layer, not within A2A semantics.“ TLS MUST, autentizace
  každého requestu MUST, autorizace „implementation-specific“.
- **Kontext uživatele v Task/Message: žádné pole**, jen generické `metadata`; `AgentInterface.tenant` je opaque
  routing hodnota. §7.6 `TASK_STATE_AUTH_REQUIRED`: credentials **out-of-band**, in-band jen přes extension;
  stav sám není autorizace.
- Push notifications: `AuthenticationInfo` (scheme, credentials), agent MUST posílat credentials v hlavičkách.

## C. IETF a OpenID

| Dokument | Stav | Co řeší |
|---|---|---|
| **RFC 8693** Token Exchange | RFC 2020 | `subject_token`, `actor_token`, `resource`, `audience`; claim `act` (řetězitelná delegace), `may_act` |
| **draft-ietf-oauth-identity-chaining-17** | adopted WG, RFC Ed Queue (*neověřeno*) | RFC 8693 v doméně A → JWT grant → RFC 7523 v doméně B |
| **draft-ietf-oauth-identity-assertion-authz-grant-04** (ID-JAG, XAA) | adopted WG | ID token → ID-JAG (`typ oauth-id-jag+jwt`, claims vč. OPTIONAL `act`, `tenant`, `sub_id`) → access token; use case „AI Agent using External Tools“; `actor_token` bez normativního zpracování |
| **draft-ietf-wimse-aims-00** | adopted WIMSE, Informational | agenti jsou workloads; mTLS/SPIFFE + aplikační vrstva; OAuth pro delegaci; HITL |
| draft-oauth-ai-agents-on-behalf-of-user (WSO2) | individual, expirovaný 2026-02 (*neověřeno*) | `requested_actor`, `act.sub` |
| draft-liu-ai-agent-authorization-integration-00, draft-ni-wimse-ai-agent-identity-03 | individual (*neověřeno*) | integrační profily |
| **OpenID AuthZEN**: Authorization API 1.0 (Final 1/2026 *neověřeno*); **COAZ-MCP Binding Draft 1** (2026-02-13); Token Exchange binding Draft 1 | – | PDP API; mapování MCP JSON-RPC na AuthZEN requesty, CEL mapování argumentů v tool schema – **přímo relevantní pro N3** |

## D. Microsoft Entra Agent ID

- **GA** („now generally available“, what's new 2026-05-01); wizard v admin centru Preview; dostupné všem Entra
  zákazníkům, rozšířené security features (CA, ID Protection) vyžadují **Microsoft Agent 365**.
- Model: **agent identity blueprint** (drží credentials: FIC, cert, secret) → **agent identity** per agent (bez
  vlastních credentials, single-tenant) → volitelně agent user account. Service principal pro agenty „not recommended“.
- **OBO:** blueprint ani agent identity nesmí iniciovat `/authorize`; granty `client_credentials`, `jwt-bearer`,
  `refresh_token`. Flow: user token (aud = blueprint) → blueprint `client_credentials` + `fmi_path` → agent identity
  `jwt-bearer` s `requested_token_use=on_behalf_of`. Claims `azp` = agent, `oid` = uživatel, `xms_act_fct=11`,
  `xms_par_app_azp` = blueprint. → **Microsoft varianta jwt-bearer OBO, ne RFC 8693**; `act` se nepoužívá.
- **Mimo Azure:** Auth SDK sidecar (K8s, on-prem) nebo **Workload Identity Federation** – FIC na blueprintu důvěřuje
  externímu OIDC issueru vč. **SPIFFE/SPIRE** (tutorial 2026-08-12; RS256, `use: sig`, veřejný endpoint).
- Limity: 250 agent identities per blueprint (non-Microsoft platformy, app-only); nelze do administrative units;
  agent identity nepřistupuje do jiného tenantu.
- MCP server s Entra jako AS: `resource` musí odpovídat `identifierUris`, **v2 tokeny**, PRM ručně. agentgateway docs
  tvrdí, že Entra `resource` odmítá – **rozpor, vyřeší test**.

## E. Co už řeší zvolené komponenty

| Komponenta | Identita (I1) | Delegace (I2) | Autorizace (I3) | Audit (I4) |
|---|---|---|---|---|
| **Dapr 1.18.9** | sentry CA, mTLS default v K8s, `spiffe://<td>/ns/<ns>/<appid>`, Ed25519; **identita per App ID, ne per instance**; jen X.509, ne JWT-SVID | – | `accessControl` App-ID → App-ID + operace; per-tool jen **OPA middleware**; `WorkflowAccessPolicy`; secret scopes (OpenBao, Vault, Key Vault) | workflow history |
| **agentgateway 1.6** | `apiKeyAuthentication`, `jwtAuthentication` (multi-provider), MCP auth s PRM/AS metadata za gateway (Keycloak, Entra, Okta…) | **`oauthTokenExchange`** (RFC 8693 i RFC 7523, `actorToken`), **`crossAppAccess`** (ID-JAG; demo jen s patchovaným Keycloakem); past: client-auth stripuje token → `preserveToken` | CEL `traffic/backend/backend.mcp.authorization` (`mcp.tool.name`, **argumenty ne**); `extAuthz` gRPC (BYO PDP) | request log, cost, CEL labely |
| **Claude Agent SDK** | nic | nic (statické `headers` pro MCP, při 401 stav `needs-auth`) | hooks → deny → ask → mode → allow → `canUseTool`; `PreToolUse` i v `bypassPermissions`, `updatedInput`; matcher `^mcp__` | hook input `session_id`, `agent_id`, `tool_use_id` |

## F. SPIFFE/SPIRE pro agenty

- JWT-SVID stable (`sub` = SPIFFE ID, `aud` MUST); SPIRE `default_jwt_svid_ttl` 5 min.
- **SPIRE OIDC Discovery Provider** servíruje `/.well-known/openid-configuration` a `/keys` – federace SPIRE → OIDC
  **existuje a je dokumentovaná**.
- SVID jako OAuth client credential: **Entra** ano (FIC, JWT-SVID jako `client_assertion`, RS256); **Keycloak** ano
  („Signed JWT issued by an Identity Provider“ s use case SPIFFE JWT SVIDs; SPIFFE identity provider tech preview;
  Standard Token Exchange od 26.2; ID-JAG jen přijímající strana experimental 26.7; delegace `actor_token`/`may_act`
  **preview 26.8**).
- Dapr sentry vydává jen X.509 per App ID → pro OAuth client credentials agenta buď **SPIRE vedle Dapru**, nebo
  Entra sidecar/FIC. SPIRE jako upstream CA pro sentry v Dapr docs nenalezeno.

## Tok identity podle toho, co standardy umožňují

```mermaid
sequenceDiagram
    autonumber
    participant U as Uživatel
    participant UI as AG-UI frontend
    participant IdP as IdP zákazníka (Entra / Keycloak)
    participant O as Orchestrátor (Dapr Workflow)
    participant A as Agent (Claude Agent SDK + sidecar)
    participant GW as agentgateway
    participant MCP as MCP server
    participant P as A2A peer
    participant M as Model

    U->>IdP: OIDC Authorization Code + PKCE
    IdP-->>UI: ID token + access token (aud = platforma)
    UI->>O: AG-UI request, Bearer user AT
    Note over O,A: Dapr mTLS, SPIFFE App ID, ACL. User AT v hlavičce = platformní konvence, ne standard
    O->>A: invoke + user AT + traceparent
    Note over A: PreToolUse hook = lokální PEP (dotaz na PDP)
    A->>GW: tools/call, Bearer user AT
    GW->>GW: jwtAuthentication + CEL authz (jwt.sub, mcp.tool.name)
    alt RFC 8693 (jedna doména)
        GW->>IdP: token-exchange: subject=user AT, actor=agent SVID, resource=MCP URI
        IdP-->>GW: AT aud=MCP, act={sub: agent}
    else ID-JAG / EMA (dvě domény)
        GW->>IdP: token-exchange → ID-JAG
        GW->>MCP: jwt-bearer u AS MCP serveru → AT aud=MCP
    end
    GW->>MCP: tools/call, Bearer AT aud=MCP
    MCP->>MCP: MUST validovat aud; MUST NOT passthrough
    MCP-->>A: result
    opt A2A delegace
        A->>P: SendMessage, auth dle Agent Card
        Note over A,P: identita uživatele v Task nestandardizována → exchange per hop nebo extension
    end
    A->>GW: /v1/messages, virtuální klíč
    GW->>M: provider credential injektuje gateway; metadata.user_id = jwt.sub
    M-->>A: odpověď
    A-->>O: výsledek (audit: session_id, agent_id, tool_use_id, trace_id)
```

PEP: agentgateway (MCP i model), Dapr sidecar (App-ID ACL), Agent SDK hook (lokálně). PDP: IdP (vydání
tokenu = „kdo smí který server“), OPA/AuthZEN (per tool/argument), Dapr Configuration. Standard končí na kroku
„tools/call s AT aud=MCP“ – vše před ním a A2A delegace jsou platformní konvence.

## Co ověřit dál

- [ ] Text RFC 8693 a stav draftů na datatrackeru (identity-chaining RFC Ed Queue?).
- [ ] MCP SEP-1933 Workload Identity Federation – obsah PR.
- [ ] Entra: chování `resource` (MS docs vs. agentgateway docs) – test s v2 tokeny.
- [ ] Dapr sentry se SPIRE jako upstream CA; JWT-SVID.
- [ ] agentgateway `crossAppAccess` s produkčním IdP (ne patchovaný Keycloak).
- [ ] AuthZEN Authorization API 1.0 Final – potvrdit; COAZ-MCP implementace.

## Changelog
- 2026-10-22: první verze z rešerše.
