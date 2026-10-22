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

*(doplní se z rešerše 2026-10-22)*

## Regulace a governance

*(doplní se z rešerše 2026-10-22)*

## Co ověřit dál

- [ ] Síto kolo 1 – OSS kandidáti pro I1–I4 a N4.
- [ ] Stav MCP authorization, A2A auth, IETF drafty, Entra Agent ID.
- [ ] Aktuální harmonogram EU AI Act a technické požadavky na audit a lidský dohled.

## Changelog
- 2026-10-22: první verze – kostra, diagram toku identity, otevřeno síto.
