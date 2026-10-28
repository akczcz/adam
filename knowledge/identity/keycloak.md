---
tema: Keycloak 26.8 jako platformní authorization server – standard token exchange V2, downscope enforcer, delegace
naposledy_overeno: 2026-10-22
zralost: stable (V2 exchange supported, default on) / preview (delegace, `act`)
primarni_zdroje:
  - https://github.com/keycloak/keycloak/blob/main/docs/guides/securing-apps/token-exchange.adoc
  - https://github.com/keycloak/keycloak/releases/tag/26.8.1
  - https://github.com/keycloak/keycloak/blob/main/LICENSE.txt
---

# Keycloak

## Účel
Platformní authorization server pro I2: vydává tokeny uživatelům (federace na IdP zákazníka přes OIDC brokering),
provádí **token exchange** pro gateway (user token → token pro konkrétní MCP server) a nese audit událostí exchange.

## Aktuální stav
- 26.8.1 (2026-10-13), Apache-2.0, CNCF incubating, DCO; 8/11 maintainerů IBM (viz [overview.md](overview.md)).
- Standard token exchange **V2** (`token-exchange-standard:v2`) je **DEFAULT** feature; legacy V1 PREVIEW + deprecated;
  **delegace** (`token-exchange-delegation`) PREVIEW se závislostí `parameterized-scopes` (`Profile.java`, main @f7532e1).
- Vše níže **změřeno harnessem** `tools/harness_identity_i2/` proti 26.8.1 (2026-10-22), nejen přečteno.

## Klíčové koncepty (změřeno)

| Vlastnost | Chování 26.8.1 | Důsledek |
|---|---|---|
| Zapnutí exchange | per klient atribut `standard.token.exchange.enabled=true`; klient musí být confidential | gateway = confidential klient s tajemstvím nebo `private_key_jwt` |
| Subject token | **musí mít requester (gateway) v `aud`**, jinak „Client is not within the token audience“ | frontend klient potřebuje audience mapper na gateway |
| `audience` parametr | **jen filtruje**, audience nepřidá; audience vzniká z mapperů (client scope nebo client-level mapper) | mapper `mcp-tickets` patří na gateway klienta, ne na scope, jinak ho nese i uživatelův token (passthrough by prošel) |
| `scope` parametr | bez enforceru vydá **i scope, který subject token neměl** (alice bez `tickets:write` ho dostala) | **upscoping je default** – past |
| `downscope-assertion-grant-enforcer` | client policy executor; odmítne scope **i audience**, které subject token nemá (`invalid_scope` / „Requested audience not available“) | buď uživatelův token nese aud všech MCP serverů (koliduje s RFC 8707 passthrough obranou), nebo enforcer vypnout a upscope hlídat konfigurací gateway |
| `actor_token` bez feature | tiše ignorován, `act` nevzniká | žádná delegace |
| `actor_token` s `token-exchange-delegation` | validován („Client is not within the token audience“); scope `delegation:client:<id>` vyžaduje **consent required** na klientovi, **souhlas uživatele při každém přihlášení** a **FGAP V2** permission `delegate`; direct grant ho odmítne | pro autonomní agenty s dlouhodobým mandátem **nepoužitelné**; `act` řetěz zbývá řešit jinak |
| `resource` (RFC 8707) | nepodporován v exchange | audience jen přes `audience` |
| Revokace řetězu | exchangovaný token přežije revokaci subject tokenu | krátké TTL |
| `sub` claim | od KC 25 ho nese client scope `basic` | realm import s `clientScopes` vestavěné scopes **nevytvoří** – `basic` musí být v JSON |
| Audit | `TOKEN_EXCHANGE_ERROR` události s `client_policy_error_detail`; úspěšné exchange jen s zapnutým event logem | zapnout `eventsEnabled` pro realm |
| Latence | exchange p50 58 ms (dev mode, H2) | cache v gateway nutná |

## Federated client authentication a exchange v podu role (P3-6 E2, změřeno na AKS 2026-10-28)

Ověřeno z tagu `keycloak/keycloak@26.8.1` (docs + zdroje; identity-scout 2026-10-28) a měřením `tools/harness_p1_k8s` E2a–c (run 40667386140):

| Fakt | Stav 26.8.1 | Zdroj |
|---|---|---|
| `client-auth-federated`, `kubernetes-service-accounts` | **DEFAULT** (GA od 26.5): client authenticator `federated-jwt` („Signed JWT - Federated“), atributy `jwt.credential.issuer` (alias IdP) a `jwt.credential.sub`; klient se hledá podle `sub` assertion + alias IdP (`DefaultClientAssertionStrategy`), **ne podle `client_id`** → jeden SA = jeden klient | `Profile.java`, `authenticators/client/*.java`, `identity-broker/kubernetes.adoc` |
| IdP `kubernetes` | config `issuerDiscoveryUrl` (discovery při uložení → `issuer`, `jwksUrl`); assertion = projektovaný SA token s `aud` = issuer realmu, max 3600 s; `iss` nepovinné u SPIFFE varianty | `KubernetesIdentityProviderConfig.java`, `kubernetes.adoc` |
| `spiffe` (JWT-SVID jako client assertion, `jwt-spiffe`) | **PREVIEW** – „specification is still a draft“; bundle endpoint může být JWKS spire-oidc | `spiffe.adoc`, `SpiffeIdentityProvider.java` |
| Standard exchange V2 + federated klient | funguje: žadatel = klient role autentizovaný SA tokenem → `azp` = role, `sub` = člověk; subject token musí nést klienta role v `aud` (audience mapper na `platform-gui`) | měřeno E2a: exchange 94 ms, lifespan 1800 s |
| Delegace (`act`) | PREVIEW `token-exchange-delegation` + `parameterized-scopes`; souhlas při každé login session; 27.0 notes beze změny | `26_8_0.adoc`, `27_0_0.adoc` |
| Legacy exchange (external-to-internal) | PREVIEW + deprecated, vyžaduje FGAP V1 (DEPRECATED); náhrada = JWT Authorization Grant (DEFAULT, ale mapuje na **uživatele**) | `token-exchange.adoc`, `jwt-authorization-grant.adoc` |
| Admin API past | `PUT /clients/{id}` s `protocolMappers` v reprezentaci mappery přepíše | měřeno E2 (2. běh) |

Důsledek: mandát „jménem“ = `sub + azp` podepsané Keycloakem + vazba na SVID v PEP (paměť ověří `azp == agent-<role>-<tenant>` ze SPIFFE ID);
`act` přijde jako nadmnožina po GA. Omezení: subject token (člověk) žije 30 min – role bez HITL před sebou exchange nestihne (degradace).

## Místo v architektuře
AS pro platformu, federovaný na Entra ID / IdP zákazníka. Exchange volá **agentgateway** (`backendAuth.oauthTokenExchange`),
ne agentní kód. Viz [agentgateway-identity.md](agentgateway-identity.md) a diagram v [standardy.md](standardy.md).

## Zralost a rizika
- V2 exchange stabilní a podporovaný; delegace preview s UX, které autonomní agent nesplní.
- Bez enforceru je gateway jediná obrana proti upscopingu – gateway klient je tedy plně důvěryhodný PEP.
- De facto IBM projekt pod CNCF (směrové riziko, ne licenční).

## Architektonické důsledky
1. Identita agenta (I1) **nejde dnes vložit do tokenu uživatele** přes Keycloak `act`. Alternativy: (a) agent posílá JWT-SVID
   jako druhý credential a MCP server/gateway ho loguje (I4) a vyhodnocuje (I3) zvlášť; (b) Zitadel (downscope-only,
   RFC 8707, `actor_token`) po právním posudku AGPL; (c) čekat na Keycloak delegation GA s client-credentials cestou.
2. Enforcer **nepoužívat** v kombinaci s per-MCP audience; upscope hlídá konfigurace gateway (`scopes: [...]` per route) + OPA.
3. Realm jako kód: `configs/realm-platform.json` v harnessu je referenční import (scopes `basic`, `profile`, audience mappery, client policy).

## Otevřené otázky
- [ ] V kterém releasu je `actor_token` delegace a zda vznikne cesta bez interaktivního souhlasu (client credentials actor) – 27.0 notes beze změny (2026-10-28).
- [x] ~~Chování `actor_token` s JWT-SVID cizího issueru~~ – SVID se v Keycloaku nepoužívá jako actor, ale jako **client assertion** (`jwt-spiffe`, preview); K8s SA token totéž GA (E2, 2026-10-28).
- [ ] Support policy 26.x / LTS – neověřeno.
- [ ] Cache exchange v agentgateway: změřeno p50 71–81 ms přes gateway vs. 58 ms exchange → cache pravděpodobně neúčinná; ověřit.

## Changelog
- 2026-10-28: P3-6 E2 – federated client authentication (K8s SA token podu role) + standard exchange V2 změřeno na AKS; SPIFFE client auth a delegace `act` preview; past PUT klienta.
- 2026-10-22: první verze; vše z harnessu I2 proti 26.8.1.
