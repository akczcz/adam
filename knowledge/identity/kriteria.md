---
tema: Hodnoticí kritéria pro vrstvu identity, autorizace a governance agentů
naposledy_overeno: 2026-10-22
zralost: n/a (metodika)
primarni_zdroje:
  - https://modelcontextprotocol.io/specification/2026-07-28/basic/authorization
  - https://datatracker.ietf.org/doc/html/rfc8693
  - https://spiffe.io/docs/latest/spiffe-about/overview/
  - https://eur-lex.europa.eu/eli/reg/2024/1689/oj
---

# Kritéria pro identitu, autorizaci a governance

Rubrika pro **průřezovou vrstvu** platformy (viz [`../platforma/overview.md`](../platforma/overview.md)):
nemá jedno místo, protíná orchestraci, gateway, nástroje (MCP) i agenty (A2A). Je nejdražší na
dodatečné vložení, proto se otevírá hned po gateway.

## Čtyři otázky, které vrstva musí zodpovědět

| # | Otázka | Co to znamená v autonomní firmě |
|---|---|---|
| I1 | **Kdo je agent?** | Každá instance agenta má ověřitelnou workload identitu (ne sdílený API klíč), vázanou na roli a tenanta |
| I2 | **Za koho jedná?** | Identita koncového uživatele / zadavatele se propaguje celým řetězcem agent → agent → nástroj (on-behalf-of), s možností zúžení, nikdy rozšíření oprávnění |
| I3 | **Co smí?** | Autorizace je politika mimo prompt: kdo smí volat který nástroj, kterého agenta, s jakým rozsahem; limity hloubky delegace |
| I4 | **Co udělal a proč?** | Auditní stopa vzniká automaticky, je neměnná, spojuje identitu, rozhodnutí, nástroj, náklad a trace |

## A. Vyřazovací kritéria

Společná A1–A5 z [`../frameworks/kriteria.md`](../frameworks/kriteria.md), pro tuhle vrstvu konkrétně:

| # | Kritérium | Co to znamená tady |
|---|---|---|
| A1 | OSI licence produkčního runtimu | Pozor na **BUSL** (HashiCorp Vault, Boundary) a na „open core“ identity providery, kde je SSO/multi-tenancy placené |
| A2 | Kontejnery na Kubernetes | Identity provider, policy engine i secret store běží jako běžné workloady; žádná vazba na jeden IdP cloudu |
| A3 | Air-gapped | Žádná kontrola licence přes síť; OIDC discovery a JWKS funguje interně |
| A4 | Bez řízené služby jednoho cloudu | **Entra ID je výchozí IdP zákazníka, ne jádro platformy** – platforma musí federovat s Entra ID, Keycloakem i čímkoliv OIDC; stejně Entra Agent ID je integrace, ne závislost |
| A5 | Stav mimo framework | Uživatelé, role, politiky a audit log v naší DB v dokumentovaném schématu |

## B. Bodovaná kritéria

### N1. Identita agentů (I1)

| Co | Jak se to zjistí |
|---|---|
| Workload identita per agent instance (SPIFFE ID / SVID, K8s service account token, mTLS) | Umí Dapr sentry / SPIRE vydat identitu per aplikace a lze ji svázat s rolí agenta? |
| Identita přežije restart a škálování, nevyžaduje distribuci dlouhodobých tajemství | Rotace certifikátů/tokenů automaticky |
| Agent se identifikuje stejně vůči MCP serveru, A2A peerovi i gateway | Jedna identita, tři protokoly – nebo tři identity? |
| **Entra Agent ID a obdobné** (identity agentů v IdP zákazníka) | Jde o mapování naší identity na účet v Entra, ne o nahrazení |

### N2. Propagace identity a delegace (I2)

| Co | Jak se to zjistí |
|---|---|
| **OAuth 2.0 Token Exchange (RFC 8693)** nebo ekvivalent pro on-behalf-of mezi agenty | Podporuje IdP kandidát `urn:ietf:params:oauth:grant-type:token-exchange` s `actor_token`? |
| **MCP authorization** (OAuth 2.1, RFC 9728 protected resource metadata, resource indicators RFC 8707) | Umí IdP vydat token pro konkrétní MCP server jako resource? Umí MCP server kandidáta ověřit? |
| A2A: autentizační schémata v Agent Card, předání kontextu uživatele | Co A2A spec říká o identitě uživatele v úkolu |
| **Zúžení, nikdy rozšíření**: delegovaný token má podmnožinu oprávnění | Scope down při exchange; limit hloubky delegace (`act` chain) |
| Identita uživatele dorazí až k poskytovateli modelu (`metadata.user_id`) a do audit logu | Viz gateway G5 |

### N3. Autorizace (I3)

| Co | Jak se to zjistí |
|---|---|
| Model politiky: RBAC / ABAC / ReBAC – a který sedí na „agent X smí nástroj Y pro tenanta Z do limitu W“ | OPA/Rego (ABAC), Cedar (ABAC+RBAC s formální verifikací), OpenFGA/SpiceDB (ReBAC, Zanzibar) |
| Politika jako kód v Gitu, testovatelná, s dry-run | Policy testy, decision logy |
| Vynucení na hranici: gateway (MCP tool call, model), orchestrátor (kdo koho volá), sandbox (co smí proces) | Kde je **Policy Enforcement Point** a kde **Decision Point**; latence rozhodnutí |
| Hloubka delegace a obrana proti kaskádě | Vynutitelné pravidlo, ne doporučení v promptu |
| Schvalovací body (HITL) jako součást politiky | Které akce vždy vyžadují člověka – deklarativně, mimo prompt |

### N4. Tajemství a credentials nástrojů

| Co | Jak se to zjistí |
|---|---|
| Agent nikdy nevidí credential k nástroji – injektuje ho gateway/sidecar | Credential injection pattern (kagent, agentgateway, Dapr secret store) |
| Secret store: OpenBao / Vault (licence!) / External Secrets Operator / cloud KMS za abstrakcí | Dapr secret store komponenty jako šev |
| Rotace bez restartu agentů | – |

### N5. Audit a governance (I4)

| Co | Jak se to zjistí |
|---|---|
| Auditní záznam **automaticky** z gateway, orchestrátoru a policy engine, ne dopisovaný agentem | Decision log OPA/Cedar, request log gateway, Dapr workflow history |
| Neměnnost a retence (append-only, podepsané, WORM úložiště) | Kam a jak dlouho |
| Spojení přes `trace_id`: identita → rozhodnutí → nástroj → model → náklad | Jeden klíč napříč vrstvami (viz observabilita) |
| **EU AI Act**: klasifikace rizika use casu, logging (čl. 12), lidský dohled (čl. 14), transparentnost (čl. 50), povinnosti pro GPAI; **aktuální harmonogram** (odklady 2026?) | Primární zdroj: EUR-Lex a Evropská komise, ne články |
| ISO/IEC 42001, NIST AI RMF jako rámec governance | Co z nich plyne pro platformu, ne pro organizaci |

### N6. Provozní zralost a ekosystém

| Co |
|---|
| Helm chart, HA, upgrade bez výpadku autorizace (fail-closed vs. fail-open při výpadku PDP) |
| Governance projektu: nadace, CLA/DCO, bus factor, support policy – jako u frameworků B1 |
| SDK pro Python a TypeScript; integrace s Dapr, agentgateway, Claude Agent SDK |

## C. Čím se záměrně neřídit

| Anti-kritérium | Proč |
|---|---|
| „Guardrails v promptu“ jako autorizace | Prompt není politika. Model lze přesvědčit, policy engine ne |
| Počet integrací IdP | OIDC je jeden standard; stačí ho umět správně |
| Certifikace vendora (SOC 2 atd.) | Říká něco o vendorovi, ne o komponentě, kterou provozujeme my |

## Changelog
- 2026-10-22: první verze; čtyři otázky I1–I4, kritéria N1–N6.
