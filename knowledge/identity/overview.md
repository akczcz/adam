---
tema: Mapa vrstvy identity, autorizace a governance agentů
naposledy_overeno: 2026-10-22
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

*(doplní se z rešerše 2026-10-22)*

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

- [ ] Síto kolo 1 – OSS kandidáti pro I1–I4 a N4.
- [x] ~~Stav MCP authorization, A2A auth, IETF drafty, Entra Agent ID~~ → [standardy.md](standardy.md), 2026-10-22.
- [x] ~~Aktuální harmonogram EU AI Act a technické požadavky na audit a lidský dohled~~ → [regulace.md](regulace.md), 2026-10-22; text OJ zbývá ověřit.

## Changelog
- 2026-10-22: standardy – MCP auth, A2A, ID-JAG, Entra Agent ID, co řeší Dapr/agentgateway/Agent SDK (standardy.md).
- 2026-10-22: regulace – harmonogram po Omnibusu, požadavky T1–T15 (regulace.md).
- 2026-10-22: první verze – kostra, diagram toku identity, otevřeno síto.
