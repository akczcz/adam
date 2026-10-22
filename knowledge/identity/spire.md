---
tema: SPIRE jako workload identita agentů – JWT-SVID, OIDC discovery, vztah k Dapr sentry
naposledy_overeno: 2026-10-22
zralost: stable (SPIRE v1.15.5; helm-charts-hardened 0.30.3; Dapr sentry JWT od 1.16) – rešerše, neměřeno
primarni_zdroje:
  - https://github.com/spiffe/spire/blob/main/doc/spire_server.md
  - https://github.com/spiffe/spire/blob/main/doc/spire_agent.md
  - https://github.com/spiffe/spire/blob/main/support/oidc-discovery-provider/README.md
  - https://github.com/spiffe/spire/blob/main/doc/plugin_server_upstreamauthority_disk.md
  - https://github.com/spiffe/helm-charts-hardened/blob/main/charts/spire/README.md
  - https://github.com/dapr/dapr/blob/master/cmd/sentry/options/options.go
  - https://github.com/dapr/dapr/blob/master/dapr/proto/sentry/v1/sentry.proto
  - https://github.com/dapr/dapr/blob/master/docs/release_notes/v1.16.0.md
---

# SPIRE

## Účel
Odpověď na I1 „kdo je agent“: identita per workload (instance) místo sdíleného klíče. X509-SVID pro mTLS
k gateway, **JWT-SVID** jako `actor_token` nebo `client_assertion` (Keycloak, Entra FIC).

## Aktuální stav
SPIRE v1.15.5 (2026-10-20), CNCF graduated, Apache-2.0, DCO. Helm `helm-charts-hardened` 0.30.3 s OIDC discovery
providerem **zapnutým defaultně**. Rešerše ze zdrojových repozitářů (2026-10-22), v harnessu I2 **neběžel**.

## Klíčové koncepty
- Attestace node (K8s PSAT, `join_token` lokálně) a workload (`unix`, `k8s` selectory); entry = SPIFFE ID + selektory.
- `default_jwt_svid_ttl` 5 min, `jwt_issuer` nutné pro `iss`; `spire-agent api fetch jwt -audience <aud>`.
- OIDC discovery provider: `/.well-known/openid-configuration`, `/keys` (`set_key_use = true` → `use: sig`, Entra to vyžaduje).
- `UpstreamAuthority "disk"`: SPIRE jako intermediate pod společným offline rootem.

## Vztah k Dapr sentry (oprava kola 1)

| | Dapr sentry 1.18 | SPIRE |
|---|---|---|
| X.509 | ano, `spiffe://<td>/ns/<ns>/<appid>` – **per App ID**, ne per instance | ano, per workload |
| JWT-SVID | **ano od 1.16** (`--jwt-enabled`, `--jwt-issuer`, OIDC server `--oidc-enabled` :9080; 1.18 per-audience) | ano |
| API pro aplikaci | **žádné** – `FetchJWT` je interní Go API daprd; použije ho jen daprd (Azure FIC, `MCPServer` CRD `auth.spiffe.jwt`) | Workload API (unix socket), py-spiffe |
| BYO CA | `--issuer-credentials` (klíč issueru na disku) | `UpstreamAuthority disk` |
| SPIRE jako upstream sentry | **ne** – SPIRE CA klíč neexportuje | – |

Společný root je možný jen jako **offline root + dva intermediates** (jeden SPIRE, jeden sentry).

## Zralost a rizika
- Dvě trust domény (Dapr-interní vs. aplikační) jsou realistický stav; spojovat je má smysl jen kvůli jednomu rootu v HSM.
- Dapr 1.18 default Ed25519 – sentry < 1.17.7 bundle neparsuje.
- Keycloak SPIFFE identity provider je tech preview; Entra FIC vyžaduje RS256 a veřejný OIDC endpoint.

## Architektonické důsledky
**Pozn. Adam (návrh):** SPIRE pro agenty a gateway (X509 pro mTLS, JWT-SVID jako actor/client assertion),
Dapr sentry výhradně pro Dapr-interní mTLS a ACL. Agent si SVID bere z Workload API sám – alternativa „Dapr sidecar
je MCP klient s SPIFFE injekcí“ (`MCPServer` CRD) by obešla Claude Agent SDK jako MCP klienta a změnila rozhodnutí
o MCP hranici.

## Otevřené otázky
- [ ] Harness: SPIRE standalone (join_token) + JWT-SVID jako `actor_token` v Keycloaku (vyžaduje SPIFFE IdP federaci realm).
- [ ] py-spiffe v agentním runtime; rotace 5min JWT-SVID v dlouhých bězích.
- [ ] Společný root: ano/ne (rozhodnutí Adam).

## Changelog
- 2026-10-22: první verze (kolo 2, rešerše).
