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
| O-2 se **živým modelem** (`--mode live`) | ✅ 2026-10-24 (Adamův Mac, Remote Control session) | 5 PASS, 3 INFO: `claude-haiku-4-5` injekci **sám odmítl** („vsunutá instrukce, kterou jsem ověřil a ignoroval“), zápis do paměti žádal `proposed`; cena 0,045–0,058 USD per zakázka (8–21 kol). **Nález:** vestavěný Bash CLI běžel 11× mimo sandbox → `tools=[]`, `strict_mcp_config`, cwd mimo repo; agent runtime je součást hranice (kriteria sandboxu B3, `roles/*.yaml` `agent_sdk`) |
| Artefakty naostro: zadání = GitHub issue (po H1), větev + PR ze sandboxu (po Vývojáři), merge PR jen přes executor po H4; disclosure vkládá platforma z definice role | ✅ suchý běh 2026-10-24 (O-2 `--scenario github` 4/4, payloady v `results/github-dryrun/`); **ostrý zápis čeká na Adamův souhlas a PAT** (`--publish-github`) | [`tools/harness_p0_o2`](../../tools/harness_p0_o2/README.md) |
| HITL přes GitHub: H1 = `/schvaluji` na issue, H4 = PR review APPROVED na head SHA; bridge (poll + webhook HMAC) jako PEP před approval tokenem | ✅ mock 2026-10-24 (O-2 `github-hitl` 5/5); ostrý běh = webhook GitHub App nebo polling s PAT | [`tools/harness_p0_o2`](../../tools/harness_p0_o2/README.md) |
| Role Account, Architekt, Reviewer, SRE přes Agent SDK podle `organization/roles/*.yaml` | ✅ mock 2026-10-24: Account, Architekt, Vývojář, Reviewer běží přes Agent SDK s options z rolegen a vlastním JWT (O-2 check O2i); `roles/` má 5 definic (account, architekt, vyvojar, reviewer, sre); SRE jako modelová role až s deploy MCP serverem (P1) | [`tools/harness_p0_o2`](../../tools/harness_p0_o2/README.md) |
| Identita: Keycloak JWKS místo HMAC JWT (role = service-account klient, `tenant_id`/`agent_id` z atributů uživatele, `aud=memory`, server paměti HS256 odmítá); approval token podepisuje **OpenBao transit** (ed25519, neexportovatelný, aplikace jen sign/verify, audit device) | ✅ mock 2026-10-24 (O-2 `--scenario identity` 5/5): padělek s legacy HMAC → `HITL_INVALID_TOKEN`; zbývá SVID ze SPIRE jako druhý credential, tajemství klientů z OpenBao, klienti z rolegen | [`tools/harness_p0_o2`](../../tools/harness_p0_o2/README.md) |
| Rozpočet per role × zakázka v agentgateway (`apiKey.keys[].budgets`) místo součtu usage; cena zakázky z logu gateway (`role` z klíče, `zakazka` z hlavičky); Block → 429 → `BUDGET_EXCEEDED` → eskalace vlastníkovi (HITL `rozpocet`) → pauza; Audit jen loguje | ✅ mock 2026-10-24 (O-2 `--scenario budget` 5/5); zbývá klíče z OpenBao a jejich zavedení do gateway při založení zakázky (CRD/xDS), 30d strop jako součet klíčů zakázky | [`tools/harness_p0_o2`](../../tools/harness_p0_o2/README.md) |
| První reálná zakázka: „platforma staví sama sebe“ – generátor konfigurací z `roles/*.yaml` | ✅ ručně (ne ještě agentem) | [`tools/rolegen`](../../tools/rolegen/README.md) R1 6/6: OPA data + jedna Rego, gateway klíče s rozpočty, srt settings, pod spec, approval policy, registr rolí – každý výstup ověřen nástrojem své vrstvy |
| Tatáž zakázka **provedená platformou**: zadání „vytvoř roli SRE“ → Vývojář v sandboxu (options z rolegen) → PR s hashem souboru → H4 člověk → merge-executor materializoval `roles/sre.yaml` → akceptace rolegen R1 7/7 | ✅ mock 2026-10-24 (O-2 `--scenario sre` 5/5); commit do gitu = člověk | [`tools/harness_p0_o2`](../../tools/harness_p0_o2/README.md) |

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
- 2026-10-24: HITL přes GitHub (bridge) 5/5 proti mock GitHubu; design v procesy.md.
- 2026-10-24: publikace artefaktů do GitHubu (issue, větev+PR, merge) – suchý běh 4/4; ostrý zápis gated flagem a PAT.
- 2026-10-24: čtyři modelové role přes Agent SDK (O2i), roles/account.yaml a architekt.yaml; rolegen R1 7/7 s pěti rolemi.
- 2026-10-24: zakázka P0-3 „role SRE“ provedená platformou (mock) – první artefakt dodaný do vlastního repa; rolegen agent_sdk.
- 2026-10-24: O-2 live hotové (5/0/3) – model injekci odmítl sám; nález: agent runtime součást hranice sandboxu.
- 2026-10-23: rolegen R1 6/6 – generátor konfigurací z rolí; v P0 zbývá nechat ji provést agentem.
- 2026-10-23: první verze – P0 rozpracováno (O-1, O-2 mock hotové), P1–P3 jako checklist.
