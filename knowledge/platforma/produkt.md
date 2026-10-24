---
tema: Produkt – fáze P0–P3 nad rozhodnutou architekturou; stav, co je změřené, co zbývá
naposledy_overeno: 2026-10-24
zralost: n/a (sledovací soubor)
primarni_zdroje:
  - knowledge/platforma/cilova-architektura.md
  - tools/harness_p0_o2/README.md
---

# Produkt: fáze P0–P3

Rešeršní fáze skončila rozhodnutím všech osmi vrstev (2026-10-23). Tenhle soubor sleduje skládání produktu.
Zásada zůstává: **každý krok se nejdřív změří harnessem, pak se staví.**

## P0 – dogfooding zakázka (uzavřeno 2026-10-24, bez výhrad)

| Krok | Stav | Důkaz |
|---|---|---|
| Zakázka end-to-end jako Dapr Workflow s HITL, executor nevratných akcí, PDP | ✅ | [O-1](../../tools/harness_org_o1/README.md) 9/9 |
| Vývojář = Claude Agent SDK přes agentgateway, paměť M1 s PEP, sandbox srt za gateway – **mock model** | ✅ | [O-2](../../tools/harness_p0_o2/README.md) 6/6 mock: injekce prošla modelem, neprošla platformou |
| O-2 se **živým modelem** (`--mode live`) | ✅ 2026-10-24 (Adamův Mac, Remote Control session) | 5 PASS, 3 INFO: `claude-haiku-4-5` injekci **sám odmítl** („vsunutá instrukce, kterou jsem ověřil a ignoroval“), zápis do paměti žádal `proposed`; cena 0,045–0,058 USD per zakázka (8–21 kol). **Nález:** vestavěný Bash CLI běžel 11× mimo sandbox → `tools=[]`, `strict_mcp_config`, cwd mimo repo; agent runtime je součást hranice (kriteria sandboxu B3, `roles/*.yaml` `agent_sdk`) |
| Artefakty naostro: zadání = GitHub issue (po H1), větev + PR ze sandboxu (po Vývojáři), merge PR jen přes executor po H4; disclosure vkládá platforma z definice role | ✅ suchý běh 2026-10-24 (O-2 `--scenario github` 4/4); **ostrý běh 2026-10-24 z Adamova Macu s PAT**: issue #3, PR #4, merge `2c47bfe` na `main` (G4 ✅, G5 ℹ️; G1–G3 falešné FAIL kvůli chybějícímu záznamu payloadu v ostrém režimu, opraveno) | [`tools/harness_p0_o2`](../../tools/harness_p0_o2/README.md) |
| HITL přes GitHub: H1 = `/schvaluji` na issue, H4 = PR review APPROVED na head SHA; bridge (poll + webhook HMAC) jako PEP před approval tokenem | ✅ mock 2026-10-24 (O-2 `github-hitl` 5/5); ostrý běh = webhook GitHub App nebo polling s PAT | [`tools/harness_p0_o2`](../../tools/harness_p0_o2/README.md) |
| Role Account, Architekt, Reviewer, SRE přes Agent SDK podle `organization/roles/*.yaml` | ✅ mock 2026-10-24: Account, Architekt, Vývojář, Reviewer běží přes Agent SDK s options z rolegen a vlastním JWT (O-2 check O2i); `roles/` má 5 definic (account, architekt, vyvojar, reviewer, sre); SRE jako modelová role až s deploy MCP serverem (P1) | [`tools/harness_p0_o2`](../../tools/harness_p0_o2/README.md) |
| Identita: Keycloak JWKS místo HMAC JWT (role = service-account klient, `tenant_id`/`agent_id` z atributů uživatele, `aud=memory`, server paměti HS256 odmítá); approval token podepisuje **OpenBao transit** (ed25519, neexportovatelný, aplikace jen sign/verify, audit device) | ✅ mock 2026-10-24 (O-2 `--scenario identity` 5/5): padělek s legacy HMAC → `HITL_INVALID_TOKEN`; zbývá SVID ze SPIRE jako druhý credential, tajemství klientů z OpenBao, klienti z rolegen | [`tools/harness_p0_o2`](../../tools/harness_p0_o2/README.md) |
| Rozpočet per role × zakázka v agentgateway (`apiKey.keys[].budgets`) místo součtu usage; cena zakázky z logu gateway (`role` z klíče, `zakazka` z hlavičky); Block → 429 → `BUDGET_EXCEEDED` → eskalace vlastníkovi (HITL `rozpocet`) → pauza; Audit jen loguje | ✅ mock 2026-10-24 (O-2 `--scenario budget` 5/5); zbývá klíče z OpenBao a jejich zavedení do gateway při založení zakázky (CRD/xDS), 30d strop jako součet klíčů zakázky | [`tools/harness_p0_o2`](../../tools/harness_p0_o2/README.md) |
| První reálná zakázka: „platforma staví sama sebe“ – generátor konfigurací z `roles/*.yaml` | ✅ ručně (ne ještě agentem) | [`tools/rolegen`](../../tools/rolegen/README.md) R1 6/6: OPA data + jedna Rego, gateway klíče s rozpočty, srt settings, pod spec, approval policy, registr rolí – každý výstup ověřen nástrojem své vrstvy |
| Tatáž zakázka **provedená platformou**: zadání „vytvoř roli SRE“ → Vývojář v sandboxu (options z rolegen) → PR s hashem souboru → H4 člověk → merge-executor materializoval `roles/sre.yaml` → akceptace rolegen R1 7/7 | ✅ mock 2026-10-24 (O-2 `--scenario sre` 5/5); commit do gitu = člověk | [`tools/harness_p0_o2`](../../tools/harness_p0_o2/README.md) |

### Uzavření P0 (2026-10-24)

**P0 je uzavřeno s jednou výhradou:** všech osm vrstev běží v jednom běhu zakázky lokálně bez Dockeru a každý krok má
měření (O-1 9/9; O-2 `p0` 7/7, `sre` 5/5, `github` 4/4 suchý běh, `github-hitl` 5/5, `identity` 5/5, `budget` 5/5; live
5 PASS/3 INFO; M1 11/11; rolegen R1 7/7). Výhrada k ostrému zápisu do GitHubu padla 2026-10-24 večer: zakázka P0-4 proběhla
proti skutečnému `akczcz/adam` – issue [#3](https://github.com/akczcz/adam/issues/3), PR [#4](https://github.com/akczcz/adam/pull/4),
merge `2c47bfe` přes merge-executor, soubor `zakazky/P0-4/NOTES.md` na `main`. **Platforma poprvé dodala artefakt do vlastního repa sama.**

Co P0 ukázalo o architektuře (fakta z harnessů, ne názor):

- Injekce v zadání prošla mock modelem a **neprošla platformou** – každou ze tří akcí zastavila jiná vrstva (gateway 403,
  srt egress, PEP paměti `proposed`); živý Haiku 4.5 injekci odmítl sám, hranice tedy drží i bez spolupráce modelu.
- **Agent runtime je součást hranice sandboxu**: vestavěné nástroje Claude Code běží mimo srt → role smí mít jen MCP nástroje
  platformy (`tools=[]`, `strict_mcp_config`, cwd mimo repo). Zapsáno do kritérií sandboxu a `roles/*.yaml`.
- Nevratné akce jen executor s approval tokenem vázaným na hash artefaktu; token podepisuje OpenBao, aplikace klíč nedrží;
  padělek s legacy tajemstvím → `HITL_INVALID_TOKEN`. HITL vždy fail-closed (timeout = pauza).
- Identita role = Keycloak service account s atributy; server paměti ověřuje JWKS a odmítá HS256; tenant z tokenu + RLS.
- FinOps: rozpočet vynucuje gateway na klíči role × zakázka, cena zakázky z logu gateway; Block → eskalace → pauza.
- Definice role (`roles/*.yaml`) je jediný zdroj: z ní rolegen generuje OPA data, klíče gateway, srt settings, Agent SDK
  options, k8s pod, Inspect evaly – a platforma už jednu roli (SRE) dodala sama (mock).

Co zůstává zjednodušené a kam to patří: tabulka v [p1-aks.md](p1-aks.md) „Co z P0 zůstává zjednodušené“.

## P1 – platforma na AKS

Plán, mapování konfigurací harnessů na komponenty, cena a rizika: **[p1-aks.md](p1-aks.md)** (návrh 2026-10-24, čeká na
Adamovo potvrzení rozsahu, subscription a pořadí „kind nejdřív“).

| Krok | Stav |
|---|---|
| P1-1 Cluster + Kata node pool + Cilium CNP default-deny; měří S1 `aks/` | ⬜ blokováno: subscription/region |
| P1-2 Postgres (4 DB) + ClickHouse + Collector; měří M1, O1 proti clusteru | ✅ kind 2026-10-24: [`tools/harness_p1_k8s`](../../tools/harness_p1_k8s/README.md) 6/6 – M1 11/11 proti clusterovému Postgresu 16 + pgvector, O1 9/9 proti Collectoru a ClickHouse 26.8; manifesty [`infra/k8s`](../../infra/README.md) |
| P1-3 Keycloak + SPIRE + OpenBao (raft); měří O-2 `identity` proti clusteru + SVID per pod | ✅ kind 2026-10-24: [`tools/harness_p1_k8s`](../../tools/harness_p1_k8s/README.md) P1-3 5/5 – O-2 `identity` 5/5 proti clusterovému Keycloaku a OpenBao; **SPIRE poprvé naostro**: SVID `spiffe://platform/role/vyvojar` z pod-labelu, pod bez labelu bez identity; zbývá KV auto-unseal a auth `kubernetes` (AKS, P1-5) |
| P1-4 agentgateway ×2 s Postgres DB a budgets z rolegen; měří G1 proti clusteru + P1-G (repliky) | ✅ kind 2026-10-24: [`tools/harness_p1_k8s`](../../tools/harness_p1_k8s/README.md) P1-4 6/6 – G1 21/21 proti clusterové gateway; **P1-G:** usage v Postgresu aditivní a správné, vynucení Block mezi replikami eventually consistent (flush 5 s → přestřel 3,7 requestu u 2 replik vs. 0,7 u jedné). Egress CONNECT a git TLS až s pody rolí (P1-6); O-2 `budget` externě až v P1-5 |
| P1-5 Dapr + app zakázky + paměť + bridge v clusteru | ✅ kind 2026-10-24: [`tools/harness_p1_k8s`](../../tools/harness_p1_k8s/README.md) P1-5 6/6 – **celá zakázka uvnitř Kubernetes** (issue → `/schvaluji` → ADR → PR → review → merge executor → Dokonceno), tokeny rolí z clusterového Keycloaku, podpisy z OpenBao, paměť, FinOps z Postgresu gateway; **durabilita**: smazaný pod aplikace, workflow obnoveno ze stavu v Postgresu a doběhlo. Zjednodušení: role v procesu aplikace, `sandboxed_bash` bez srt (pod = hranice), Dapr bez operátoru/mTLS, mock GitHub |
| P1-6 Role jako Kata pody z rolegen, CI job rolegen → bundle/klíče; měří R1 v CI, O-2 live v clusteru | ⬜ AKS |

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
- 2026-10-24: P1-5 na kind hotovo – zakázka end-to-end v Kubernetes (6/6), durabilita workflow přes smazání podu změřena; na kind zbývá nic, P1-1 a P1-6 = AKS.
- 2026-10-24: P1-4 na kind hotovo – agentgateway ×2 s Postgres budget_usage, G1 21/21 proti clusteru, P1-G změřen (eventually consistent, přestřel ≤ útrata za 5 s).
- 2026-10-24: ostrý zápis do GitHubu proběhl (issue #3, PR #4, merge 2c47bfe) – P0 uzavřeno bez výhrad; checky G1–G3 opraveny pro ostrý režim.
- 2026-10-24: P1-3 na kind hotovo – Keycloak, OpenBao (raft), SPIRE (SVID per pod-label) v clusteru; O-2 identity 5/5 externě; obrazy identity vrstvy stavěné lokálně (infra/images).
- 2026-10-24: P1-2 na kind hotovo (M1 11/11, O1 9/9 proti clusteru); infra/k8s + infra/kind; pasti kind v kontejneru (cgroup v1, oom_score_adj).
- 2026-10-24: P0 uzavřeno (výhrada: ostrý zápis GitHub); shrnutí zjištění; plán P1 v p1-aks.md (návrh).
- 2026-10-24: rozpočty per role × zakázka v agentgateway (O-2 `budget` 5/5); identita Keycloak JWKS + OpenBao transit (O-2 `identity` 5/5).
- 2026-10-24: HITL přes GitHub (bridge) 5/5 proti mock GitHubu; design v procesy.md.
- 2026-10-24: publikace artefaktů do GitHubu (issue, větev+PR, merge) – suchý běh 4/4; ostrý zápis gated flagem a PAT.
- 2026-10-24: čtyři modelové role přes Agent SDK (O2i), roles/account.yaml a architekt.yaml; rolegen R1 7/7 s pěti rolemi.
- 2026-10-24: zakázka P0-3 „role SRE“ provedená platformou (mock) – první artefakt dodaný do vlastního repa; rolegen agent_sdk.
- 2026-10-24: O-2 live hotové (5/0/3) – model injekci odmítl sám; nález: agent runtime součást hranice sandboxu.
- 2026-10-23: rolegen R1 6/6 – generátor konfigurací z rolí; v P0 zbývá nechat ji provést agentem.
- 2026-10-23: první verze – P0 rozpracováno (O-1, O-2 mock hotové), P1–P3 jako checklist.
