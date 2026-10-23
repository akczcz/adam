---
tema: Produkt – fáze P0–P3 nad rozhodnutou architekturou; stav, co je změřené, co zbývá
naposledy_overeno: 2026-10-23
zralost: n/a (sledovací soubor)
primarni_zdroje:
  - knowledge/platforma/cilova-architektura.md
  - tools/harness_p0_o2/README.md
---

# Produkt: fáze P0–P3

Rešeršní fáze skončila rozhodnutím všech osmi vrstev (2026-10-23). Tenhle soubor sleduje skládání produktu.
Zásada zůstává: **každý krok se nejdřív změří harnessem, pak se staví.**

## P0 – dogfooding zakázka (běží)

| Krok | Stav | Důkaz |
|---|---|---|
| Zakázka end-to-end jako Dapr Workflow s HITL, executor nevratných akcí, PDP | ✅ | [O-1](../../tools/harness_org_o1/README.md) 9/9 |
| Vývojář = Claude Agent SDK přes agentgateway, paměť M1 s PEP, sandbox srt za gateway – **mock model** | ✅ | [O-2](../../tools/harness_p0_o2/README.md) 6/6 mock: injekce prošla modelem, neprošla platformou |
| O-2 se **živým modelem** (`--mode live`) | ⬜ spouští Adam lokálně s API klíčem | – |
| Artefakty naostro: zadání = issue, ADR v `knowledge/`, PR v tomto repu; HITL přes PR review místo HTTP volání | ⬜ | – |
| Role Account, Architekt, Reviewer, SRE přes Agent SDK podle `organization/roles/*.yaml` | ⬜ | – |
| Identita: Keycloak JWKS místo HMAC JWT; SVID role místo `spiffe://` řetězce | ⬜ (mechanismus změřen v I2) | – |
| Rozpočet per role × zakázka v agentgateway (`apiKey.keys[].budgets`) místo součtu usage | ⬜ (mechanismus změřen v G1) | – |
| První reálná zakázka: „platforma staví sama sebe“ – generátor konfigurací z `roles/*.yaml` | ✅ ručně (ne ještě agentem) | [`tools/rolegen`](../../tools/rolegen/README.md) R1 6/6: OPA data + jedna Rego, gateway klíče s rozpočty, srt settings, pod spec, approval policy, registr rolí – každý výstup ověřen nástrojem své vrstvy |
| Tatáž zakázka **provedená platformou** (Vývojář přes O-2 dostane zadání „rozšiř rolegen o roli SRE“, PR přes HITL) | ⬜ | – |

## P1 – platforma na AKS

| Krok | Stav |
|---|---|
| Cluster: agentgateway, Keycloak, SPIRE, OPA-Envoy, OpenBao, OTEL Collector, ClickHouse, Postgres (state + paměť + `org.*`), Kata node pool | ⬜ |
| Harness S1 na AKS (`tools/harness_sandbox_s1/aks/`): Kata, srt v guestu non-root, start a hustota | ⬜ |
| O1 observabilita end-to-end (Agent SDK → Collector → ClickHouse) v clusteru | ⬜ |
| Helm/manifesty z harnessů jako výchozí konfigurace | ⬜ |

## P2 – role naostro

| Krok | Stav |
|---|---|
| Generátor: `roles/*.yaml` → OPA data bundle, gateway klíče a rozpočty, srt settings, Inspect eval sady | ✅ v0 (`tools/rolegen`); zbývá CI job, OPA bundle balení, hash klíčů z OpenBao |
| Obrazy rolí (devcontainer build v CI) v interním registru | ⬜ |
| Evaly L0–L3 per role s gate; registr agentů plněný z workflow | ⬜ |

## P3 – první externí zákazník

| Krok | Stav |
|---|---|
| Tenant model (Keycloak realm/atributy, RLS, gateway klíče, CNP per tenant) | ⬜ |
| Klasifikační brána naostro, čl. 50 disclosure v reálných kanálech, SLA | ⬜ |
| O-3 multi-tenant harness (M-E3 přes dva tenanty, stop per tenant) | ⬜ |

## Changelog
- 2026-10-23: rolegen R1 6/6 – generátor konfigurací z rolí; v P0 zbývá nechat ji provést agentem.
- 2026-10-23: první verze – P0 rozpracováno (O-1, O-2 mock hotové), P1–P3 jako checklist.
