---
name: identity-research
description: Postup pro průzkum a prověrku vrstvy identity, autorizace a governance multiagentní platformy (SPIFFE/SPIRE, Keycloak, Zitadel, Ory, OPA, Cedar, OpenFGA, SpiceDB, OpenBao, Vault, Entra Agent ID, MCP authorization, OAuth token exchange, EU AI Act, ISO 42001) a pro aktualizaci knowledge/identity/. Použij vždy, když Adam řeší, kdo je agent a za koho jedná, propagaci identity uživatele mezi agenty a nástroji, on-behalf-of a delegaci, kdo smí volat který nástroj nebo agenta, policy engine, tajemství a credentials nástrojů, audit trail, lidský dohled, EU AI Act či compliance agentů – i když slovo "identita" výslovně nezazní.
---

# Průzkum identity, autorizace a governance

## 1. Vyjdi ze znalostní báze
- Přečti `knowledge/identity/overview.md` a `kriteria.md`; u dotčených kandidátů jejich soubor.
- Přečti rozhodnutí v `knowledge/platforma/cilova-architektura.md`: smyčka Claude Agent SDK, orchestrace
  Dapr Agents, gateway agentgateway, hranice MCP / A2A / AG-UI. Identita musí sedět **do** těchto
  švů – ne vedle nich.
- Přečti `knowledge/protocols/mcp.md` (sekce autorizace) a `a2a.md` (autentizační schémata).
- Zkontroluj `naposledy_overeno`. Regulace a specifikace autorizace MCP se mění v řádu měsíců.

## 2. Rozliš čtyři otázky, nesměšuj je
I1 kdo je agent · I2 za koho jedná · I3 co smí · I4 co udělal. Každý kandidát obvykle řeší
jednu až dvě. Projekt, který tvrdí, že řeší všechny čtyři, je buď platforma (lock-in), nebo marketing.

## 3. Licenci a governance ověřuj jako u frameworků
Postup v `framework-research` sekce 2 a vzorce v `knowledge/frameworks/licencni-vzorce.md`. Pro tuhle vrstvu navíc:
- **BUSL je tu častá** (HashiCorp Vault, Boundary, Consul) – zapiš doslovně Additional Use Grant a Change Date,
  nerozhoduj, a vždy uveď OSS fork pod nadací (OpenBao), pokud existuje.
- U identity providerů najdi, co je **za hranicí**: SSO federace, multi-tenancy, audit log, HA – typicky první
  placené funkce.
- U policy enginů ověř licenci **decision logu / managementu** (OPA vs. Styra DAS, Cedar vs. Verified
  Permissions, OpenFGA vs. Okta FGA).

## 4. Standardy ověřuj z primárních zdrojů
- MCP authorization: aktuální spec na modelcontextprotocol.io (ne blogy) – OAuth 2.1, RFC 9728, RFC 8707, co je
  MUST a co SHOULD, co se změnilo od minulé verze.
- OAuth Token Exchange RFC 8693, OIDC; IETF drafty k identitě agentů (ověř stav draftu a datum).
- A2A spec: autentizace v Agent Card a předání uživatelského kontextu.
- Entra Agent ID a obdoby: Microsoft Learn, ne tiskové zprávy; rozliš GA / preview.
- EU AI Act: EUR-Lex (text), Evropská komise (harmonogram, guidelines, případné odklady), AI Office.
  **Datum a stav každého termínu**; u „odkladu“ ověř, zda je přijatý, nebo jen navržený.

## 5. Analyzuj architektonicky
- Kde je Policy Enforcement Point a kde Decision Point? Co se stane při výpadku PDP (fail-closed?)
- Jak identita teče: uživatel → AG-UI → orchestrátor → agent → gateway → model, a agent → MCP server,
  agent → A2A peer. Nakresli v Mermaidu.
- Kolik z toho už řeší zvolené komponenty (Dapr sentry/SPIFFE, agentgateway CEL authz + apiKey, MCP spec)
  a co zbývá dostavět.
- Cena odchodu: politika jako kód je přenositelná; vazba na IdP je šev přes OIDC.

## 6. Výstup
- Česky, závěr první, fakta se zdrojem a datem, doporučení jako doporučení.
- Návrh úprav `knowledge/identity/` jako diff; rozhodnutí do `knowledge/platforma/cilova-architektura.md`.
- Soubory měň až po Adamově souhlasu.

## 7. Pasti z kola 1 (2026-10-22)
- „Podporuje token exchange“ má tři úrovně: bez `actor_token` (Dex), s `actor_token` jako preview (Keycloak
  26.8), downscope-only s RFC 8707 (Zitadel). Ověř **v kterém releasu** a zda exchange umí i **upscoping**
  (Keycloak bez `downscope-assertion-grant-enforcer` ano).
- Policy engine ≠ PDP: Cedar a Casbin jsou knihovny bez serveru a decision logu; pro I4 musí logovat PEP.
- Secret manager ≠ credential injection: ESO dá tajemství do K8s Secret, agent ho **vidí**. Injekce patří do gateway.
- Weby docs a registry quay/ghcr bývají nedostupné – čti zdrojové repozitáře docs a uváděj commit; OCI
  labely ověř, kde to jde.

## 8. Čemu se vyhni
- Netvrď nic o termínech AI Actu z paměti – harmonogram se v roce 2026 měnil. Vždy ověř.
- Nezaměňuj „guardrails“ (filtrování obsahu) za autorizaci.
- Nehodnoť IdP podle počtu konektorů.
