---
tema: Mapa vrstvy identity, autorizace a governance agentů
naposledy_overeno: 2026-10-23
zralost: n/a (přehled)
primarni_zdroje:
  - https://modelcontextprotocol.io/specification/2026-07-28/basic/authorization
  - https://a2a-protocol.org/latest/
  - https://spiffe.io/
  - https://eur-lex.europa.eu/eli/reg/2024/1689/oj
---

# Mapa identity, autorizace a governance

Kontext: **průřezová vrstva** – každá akce agenta v autonomní firmě má mít identitu (kdo),
mandát (za koho), oprávnění (co smí) a stopu (co udělal). Kritéria v [kriteria.md](kriteria.md).
Zvolené komponenty, do kterých se identita musí vejít: Claude Agent SDK, Dapr Agents,
agentgateway, hranice MCP / A2A / AG-UI (viz [`../platforma/cilova-architektura.md`](../platforma/cilova-architektura.md)).

## Čtyři otázky a kde se v platformě rozhodují

```mermaid
flowchart LR
    U["Uživatel / zadavatel<br/><i>Entra ID · Keycloak (OIDC)</i>"]
    UI["AG-UI frontend"]
    ORCH["Orchestrátor<br/><i>Dapr Agents</i>"]
    AG["Agent<br/><i>Claude Agent SDK</i><br/>I1: workload identita"]
    GW["agentgateway<br/>I3: kdo smí který model / nástroj<br/>I4: request log"]
    MCP["MCP server<br/>I2: token za uživatele"]
    PEER["A2A peer<br/>I2: delegace"]
    PDP["Policy engine<br/>I3: politika jako kód"]
    AUD[("Audit log<br/>I4")]

    U -->|"OIDC token"| UI --> ORCH --> AG
    AG -->|"model"| GW
    AG -->|"nástroj"| GW --> MCP
    AG -->|"úkol"| PEER
    GW -.->|"rozhodnutí"| PDP
    ORCH -.->|"rozhodnutí"| PDP
    GW -.-> AUD
    ORCH -.-> AUD
    PDP -.-> AUD
```

## Široké síto – kolo 1

Ověřeno 2026-10-22 z `LICENSE`, package registry a zdrojových repozitářů docs (weby a registry quay/ghcr
byly nedostupné; OCI labely ověřeny jen u OpenBao). Bus factor = podíl commitů za 3 měsíce podle domén.
Sloupec „Řeší“: I1 kdo je agent · I2 za koho jedná · I3 co smí · I4 audit · N4 tajemství.

| Kandidát | Řeší | Licence runtimu | Enterprise hranice | Governance | Phone-home | Stav | Release | Výsledek |
|---|---|---|---|---|---|---|---|---|
| **SPIRE** | I1 | Apache-2.0; Helm `helm-charts-hardened` Apache-2.0 | žádná | **CNCF graduated** 2022; DCO; 5 maintainerů, max. doména 26 % | ne | SQL datastore (SQLite/Postgres/MySQL), HA | v1.15.5 (2026-10-20) | **postupuje** |
| **Keycloak** | I1, I2, I4 (events) | Apache-2.0 | žádná v OSS (Red Hat build = support) | **CNCF incubating** 2023; DCO; 8/11 maintainerů IBM, redhat+ibm 52 % commitů | ne | Postgres/MySQL/MariaDB/MSSQL/Oracle, Liquibase (schéma není smluvní) | 26.8.1 (2026-10-13) | **postupuje** |
| **Zitadel** | I1, I2, I4 (event store) | **AGPL-3.0-only** (proto, docs, klienti Apache/MIT) | žádná funkční; Enterprise = support | bez nadace; **bez CLA, ale příspěvky povinně Apache-2.0** (vendor smí relicencovat) | `Telemetry.Enabled: false` | Postgres only, event-sourced | v4.20.0 (2026-10-22) | **s výhradou** – AGPL u dodávky zákazníkovi → právník |
| **Ory** Kratos / Hydra / Keto | I1 / I2 bez exchange / I3 | Apache-2.0 | **OEL**: ROPC, multi-tenancy v Kratosu, zero-downtime migrace, **včasné CVE opravy** | bez nadace; **CLA**; 100 % Ory, 2 tagy za 12 měsíců | **ano, opt-out** (Segment `sqa`) | SQL | v26.2.0 (2026-03-20) | Hydra **vyřazen** (bez RFC 8693 → neřeší I2); Keto s výhradou |
| **Dex** | I2 (federace, exchange bez actora) | Apache-2.0 | žádná | CNCF sandbox 2020; DCO; **2 maintaineři**, 1 autor 45 % | ne | etcd / CRD / SQL | v2.46.1 (2026-10-21) | s výhradou – federační shim, ne IdP |
| **OPA** | I3, I4 (decision log) | Apache-2.0 | Styra DAS / Enterprise OPA mimo repo; **bundle, decision log, testy v OSS** | **CNCF graduated** 2021; DCO; 7/10 maintainerů Apple (ex-Styra), 78 % commitů apple+gmail | **version check** na api.github.com při `opa run` (`--skip-version-check`) | bez DB, bundles | v1.21.3 (2026-10-19) | **postupuje** |
| **Cedar** | I3 | Apache-2.0; PyPI `cedarpy` bez licenčních metadat (3. strana) | Verified Permissions = AWS managed PDP (A4) | CNCF sandbox **2025-10-08**; ≈99 % Amazon; DCO text nenalezen | ne (knihovna) | žádný (embedded) | v4.14.0 (2026-10-16) | s výhradou – **knihovna bez PDP a decision logu** |
| **OpenFGA** | I3 | Apache-2.0; SDK se SPDX | Okta FGA managed; v OSS nic placeného; **audit/decision log v OSS nenalezen** | **CNCF incubating** 2025-10-28; **LF EasyCLA** (držitel nadace); 20/22 maintainerů Okta | ne | Postgres/MySQL/SQLite, migrace SQL v repu | v1.22.0 (2026-10-06) | **postupuje** |
| **SpiceDB** | I3 (+I4 placené) | Apache-2.0 | **Audit Logging, Rate Limiting, Security Embargo = jen Enterprise/Cloud** | bez nadace; **CLA** AuthZed; 80–90 % AuthZed | **ano, opt-out** – hodinově na `telemetry.authzed.com` | Postgres/CockroachDB/MySQL/Spanner | v1.57.0 (2026-10-20) | s výhradou |
| **Topaz** (Aserto) | I3, I4 (file decision log) | Apache-2.0 | control plane mimo repo | bez nadace; **1 autor 95 % commitů** | nenalezeno | BoltDB | v0.33.22 (2026-09-28) | s výhradou – bus factor 1 |
| **Casbin** | I3 | Apache-2.0; PyPI bez SPDX | žádná | **ASF Incubator** (2026); ICLA; 1 autor 73 % | ne | knihovna, adaptéry | v3.11.0 (2026-08-04) | s výhradou – knihovna |
| **OpenBao** | N4, I4 (audit devices) | **MPL-2.0** (LICENSE, OCI label, Helm, Go) | žádná – **namespaces v OSS** | **OpenSSF sandbox** (od 2025-06-05, ne LF Edge); DCO; SAP 22 %, control-plane.io 22 %, bez dominantního vendora | ne | Raft a další | v2.7.1 (2026-10-01) | **postupuje** |
| **HashiCorp Vault** | N4 | **BUSL-1.1** (Licensor IBM); `api/`, `sdk/` MPL-2.0 | replikace, HSM, namespaces, audit filtering, MFA, Sentinel, FIPS, LTS… | bez nadace; CLA; 98 % HashiCorp | Enterprise: license utilization reporting (air-gap = manuální) | Raft | v2.2.0 (2026-10-15) | **vyřazen A1** – text pro právníka níže |
| **External Secrets Operator** | N4 (distribuce) | Apache-2.0 | žádná | CNCF sandbox 2022; DCO; 5 maintainerů z 5 firem | ne | K8s CRD + Secrets | v2.13.0 (2026-10-16) | **postupuje** – ale agent tajemství **vidí**; injekce patří do gateway |
| **Infisical** | N4 (+I4 placené) | MIT mimo `ee/` (proprietární) | `onPremFeatures` bez klíče: `auditLogs:false, samlSSO:false, oidcSSO:false, rbac:false, scim:false, ldap:false, secretApproval:false, secretRotation:false, externalKms:false, hsm:false…` | bez nadace; bez CLA/DCO; 63 % gmail (afiliace neověřitelná) | **PostHog default on**; **licence validována online** (offline klíč existuje) | Postgres + Redis | v0.167.0 (2026-10-22) | **vyřazen** – SSO, RBAC i audit log za klíčem |

**Vault BUSL doslovně (LICENSE, 2026-10-22):** Additional Use Grant: „You may make production use of the Licensed
Work, provided Your use does not include offering the Licensed Work to third parties on a hosted or embedded basis
in order to compete with IBM Corp's paid version(s)… ‚competitive offering' is a Product that is offered to third
parties on a paid basis, **including through paid support arrangements**… ‚Embedded' means including the source
code or executable code from the Licensed Work in a competitive offering… Hosting or using the Licensed Work(s)
for internal purposes within an organization is not considered a competitive offering.“ Change Date: 4 roky od
publikace verze; Change License: MPL 2.0. **Otázka na právníka:** „dodáváme produkt zákazníkovi s podporou“ vs.
„paid support arrangements“. Do té doby OpenBao.

### Rozhodnutí (Adam, 2026-10-23) – co ze síta a kola 2 plyne

| Otázka | Komponenta | Proč | Riziko / co zbývá |
|---|---|---|---|
| I1 workload identita | **SPIRE** vedle Dapr sentry (dvě trust domény) | SVID per instance, JWT-SVID + OIDC discovery; Dapr sentry JWT umí, ale aplikace k němu nemá API | **změřeno 2026-10-24 (P1-3 kind, SPIRE 1.14.2):** agent atestován `k8s_psat`, X.509-SVID `spiffe://platform/role/vyvojar` z pod-labelu `role=vyvojar`, pod bez labelu „no identity issued“ (`tools/harness_p1_k8s`) |
| I2 uživatelé + delegace | **Keycloak** jako platformní AS, federovaný na Entra ID; **exchange v agentgateway** | V2 exchange změřen: aud, sub, azp, downscope fungují | upscope je default → enforcer **nepoužívat** s per-MCP audience, scope hlídá konfigurace gateway; `act` delegace preview → identita agenta jako druhý credential |
| I3 + I4 | **OPA-Envoy** za `extAuthz` v gateway + stejná Rego politika z `PreToolUse` hooku; decision log | změřeno: per-tool deny před MCP, 503 při výpadku, decision log | input camelCase; CEL v gateway stačí pro jednoduchá pravidla |
| N4 tajemství | **OpenBao**; credential k nástrojům injektuje gateway | MPL-2.0, OpenSSF | neměřeno |

Čtyři komponenty, čtyři nadace (CNCF ×3, OpenSSF), žádný vendor s právem relicencovat.

## Kolo 2 a harness I2 (změřeno 2026-10-22)

Hloubkové kolo pro Keycloak ([keycloak.md](keycloak.md)), agentgateway jako PEP ([agentgateway-identity.md](agentgateway-identity.md))
a SPIRE vs. Dapr sentry ([spire.md](spire.md)). Harness `tools/harness_identity_i2/`: Keycloak 26.8.1 + mock MCP resource
server + agentgateway 1.6.0 + OPA-Envoy 1.21.2, lokálně bez Dockeru.

| Cesta | PASS/FAIL | Nálezy |
|---|---|---|
| direct (harness = gateway) | 4/1 | passthrough uživatelského tokenu MCP odmítne (aud); exchange dá `aud=mcp-tickets`, `sub`, `azp=gateway`; **upscope bez enforceru potvrzen**; enforcer odmítá i audience mimo subject token; **`act` nevzniká** |
| **agentgateway + CEL** | 6/1 | exchange v gateway funguje; CEL nad JSON-RPC tělem blokuje `delete_ticket` před MCP; audit log nese `sub` a 403; p50 81 ms |
| **agentgateway + OPA** | 8/1 | totéž + OPA decision log s `dynamic_metadata` v gateway logu; **výpadek OPA → 503** (fail-closed, odlišitelný); p50 71 ms |

Jediné selhání všude: **`act` claim** – Keycloak 26.8 má delegaci jako preview s interaktivním souhlasem a FGAP V2,
pro autonomní agenty nepoužitelnou. Identita agenta tedy dnes putuje jako **druhý credential** (SVID v hlavičce),
který gateway loguje a OPA vyhodnocuje – ne uvnitř uživatelova tokenu.

Pasti z harnessu: Keycloak realm import s `clientScopes` nevytvoří `basic` (token bez `sub`); OPA-Envoy input je camelCase;
agentgateway `jwtAuth` default `optional` a odstraní token z hlavičky. Vše v README harnessu.

## Standardy a co z nich plyne

Detail v [standardy.md](standardy.md). Jedna věta: **standardizovaný je jen hop uživatel → agent → MCP server**
(OAuth 2.1, RFC 9728, RFC 8707 – vše MUST). Delegace mezi agenty (A2A), token k downstream API a identita
k modelu jsou platformní konvence. Z toho plyne:

- Identita uživatele = OAuth token z IdP zákazníka (Entra / Keycloak); identita agenta = SPIFFE SVID
  (Dapr sentry intra, SPIRE JWT-SVID extra); **spojení obou se dělá token exchange v agentgateway**
  (`oauthTokenExchange` s `actorToken`, RFC 8693), ne v agentním kódu.
- Claude Agent SDK je jen lokální PEP (`PreToolUse` hook), nosičem identity není.
- Per-tool autorizaci umí agentgateway (`mcp.tool.name`, ne argumenty); per-argument až AuthZEN COAZ-MCP (Draft 1).
- Entra Agent ID je GA a funguje i pro workloady mimo Azure (sidecar nebo WIF přes SPIFFE) – jako **integrace**
  s IdP zákazníka, ne jádro platformy.

## Regulace a governance

Detail v [regulace.md](regulace.md). Tři věci, které mění návrh (ověřeno 2026-10-22, text OJ nečten):

- **Příloha III odložena na 2.12.2027** (nařízení 2026/1744), ale **čl. 50 platí od 2.8.2026**: agent
  jednající s lidmi musí architektonicky oznámit „jsem AI, jednám za X“. To je první požadavek k implementaci.
- Platforma pro ADLC není vysoce riziková sama o sobě, ale **přidělování práce lidem** (příloha III/4) a
  **provoz systémů u CER entit** (III/2) use case zákazníka překlopí. Multiagentní systém se počítá jako
  **jeden systém** – nejde ho rozdělit na malé bezpečné agenty. → Klasifikační brána při onboardingu (T9).
- Audit trail má minimální schéma (T3), retenci ≥ 6 měsíců (čl. 19/26) a musí být **vlastností platformy**,
  ne dopisovaný agentem (T2). AISI: per-instance monitoring agentů nestačí – útok lze rozložit mezi agenty (T12).

## Co ověřit dál
- [x] ~~SPIRE naostro: node + workload attestace v Kubernetes~~ – **2026-10-24 P1-3 kind**: `k8s_psat` + `k8s` attestor (pod-label), SVID TTL 1 h, entries zatím ručně (→ rolegen v P1-6); JWT-SVID a exchange SVID→Keycloak v gateway zbývá.

- [x] ~~Síto kolo 1 – OSS kandidáti pro I1–I4 a N4~~ – 2026-10-22, 15 kandidátů.
- [x] ~~Kolo 2: Keycloak – `actor_token`, enforcer~~ → [keycloak.md](keycloak.md) (změřeno); federace na Entra ID zbývá.
- [x] ~~Kolo 2: agentgateway `extAuthz` → OPA, nebo CEL~~ → obojí změřeno, [agentgateway-identity.md](agentgateway-identity.md).
- [x] ~~Kolo 2: SPIRE vedle Dapr sentry~~ → [spire.md](spire.md): dvě trust domény, upstream nejde.
- [ ] Právní posudek: Zitadel AGPL + inbound Apache; Vault BUSL „paid support arrangements“.
- [ ] OpenFGA: existuje decision/audit log v OSS? (nenalezen, docs neprohledány celé)
- [ ] OCI labely obrazů Keycloak (quay.io), SPIRE, Zitadel (ghcr) – registry byly nedostupné.
- [x] ~~Harness I2~~ → změřeno 2026-10-22: scope se zužuje, aud ověřeno, **`act` nevzniká**.
- [ ] Harness I2 rozšířit: SPIRE JWT-SVID jako actor/druhý credential; cache exchange v gateway; Keycloak delegace přes browser flow (pro úplnost).
- [ ] Jak nést identitu agenta, když `act` není: hlavička + OPA, nebo Zitadel – rozhodnutí Adam.
- [x] ~~Stav MCP authorization, A2A auth, IETF drafty, Entra Agent ID~~ → [standardy.md](standardy.md), 2026-10-22.
- [x] ~~Aktuální harmonogram EU AI Act a technické požadavky na audit a lidský dohled~~ → [regulace.md](regulace.md), 2026-10-22; text OJ zbývá ověřit.

## Changelog
- 2026-10-25: P2-3 (implementace, měření na AKS probíhá) – SVID v Kata podu přes SPIRE agenta jako sidecar (k8s_psat per pod, alias uzlu per role, unix uid), JWT-SVID přijímá server paměti jako druhý vydavatel (spire-oidc), OpenBao auto-unseal Key Vault + auth kubernetes; token exchange SVID→Keycloak v gateway zůstává otevřený (P3).
- 2026-10-24: P1-3 kind – Keycloak, OpenBao (raft) a SPIRE 1.14.2 v clusteru; SVID z pod-labelu změřen (I1); O-2 identity 5/5 proti clusteru.
- 2026-10-23: rozhodnuto (Adam): SPIRE + Keycloak + exchange v agentgateway + OPA-Envoy + OpenBao; agent jako druhý credential.
- 2026-10-22: kolo 2 + harness I2 – Keycloak, agentgateway PEP, SPIRE; `act` nevzniká, upscope potvrzen, OPA 503 při výpadku.
- 2026-10-22: síto kolo 1 – 15 kandidátů; Vault (BUSL), Infisical, Ory Hydra vyřazeni; návrh SPIRE + Keycloak + OPA + OpenBao.
- 2026-10-22: standardy – MCP auth, A2A, ID-JAG, Entra Agent ID, co řeší Dapr/agentgateway/Agent SDK (standardy.md).
- 2026-10-22: regulace – harmonogram po Omnibusu, požadavky T1–T15 (regulace.md).
- 2026-10-22: první verze – kostra, diagram toku identity, otevřeno síto.
