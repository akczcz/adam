---
tema: Fáze P3 – první externí zákazník: tenant model, GUI nad celou firmou (AG-UI + A2UI), klasifikační brána a čl. 50 naostro, SLA, multi-tenant harness
naposledy_overeno: 2026-10-26
zralost: návrh (čeká na Adamovo potvrzení rozsahu a pořadí)
primarni_zdroje:
  - knowledge/platforma/cilova-architektura.md
  - knowledge/platforma/produkt.md
  - knowledge/platforma/p2-role.md
  - knowledge/protocols/ag-ui.md
  - knowledge/protocols/a2ui.md
  - knowledge/organization/procesy.md
  - knowledge/organization/autonomie.md
  - knowledge/organization/metriky.md
  - knowledge/identity/regulace.md
  - knowledge/memory/model-pameti.md
---

# P3 – první externí zákazník

**Závěr (doporučení):** P2 skončilo tím, že role běží z YAML naostro, ale firma má jediný kanál k lidem – GitHub issue/PR
a `/schvaluji` – a jediný tenant `acme` zadrátovaný v env. P3 má udělat dvě věci: **(a) dát firmě jedno GUI**, přes které
člověk zakázku zadá, vidí ji téct mezi rolemi, schvaluje s důvodem, zastaví ji a čte registr/governance; **(b) oddělit
tenanty** tak, aby tentýž cluster obsloužil zákazníka vedle dogfoodingu. Doporučené pořadí: **P3-1 AG-UI server + minimální
frontend nad existujícími HITL body** (bez toho nejde nic z čl. 50 ani SLA měřit) → **P3-2 tenant model** (Keycloak,
RLS, klíče, CNP, člověk v tokenu) → **P3-3 GUI nad celou firmou** (zakázky, role, registr, FinOps, governance, stop) →
**P3-4 klasifikační brána + čl. 50 + SLA naostro** (jako A2UI dialogy v GUI) → **P3-5 O-3 multi-tenant harness** (M-E3 přes
dva tenanty, stop per tenant) → **P3-6 produkční hrany** (token exchange, ESO/cert-manager, ledger do ClickHouse, cap
v gateway). Měřítko zůstává: **každý krok má harness; GUI se měří Playwrightem proti clusteru, ne okem.** Odhad 5–7 týdnů
při jednom člověku s agentní podporou (*spekulace*; P2 trvalo 2 dny čistého času, ale GUI je nový druh práce).

## Co P2 předává do P3

| Z P2 (cluster, jeden tenant) | V P3 | Co se mění |
|---|---|---|
| HITL = `wait_for_external_event("hitl:<bod>")` + timer; event vyvolá harness nebo GitHub bridge (`/schvaluji`) | tentýž event vyvolá **AG-UI server** z akce ve frontendu; důvod povinný (T6); GitHub bridge zůstává jako druhý kanál | GUI je jen další producent eventu – workflow se nemění |
| Disclosure čl. 50 z `roles.json` vkládá platforma do issue/PR (T7) | totéž pro AG-UI zprávy (`MESSAGES`/`ACTIVITY` z role) a pro e-mail/ticket adaptér zákazníka | disclosure per kanál, ne per role |
| Tenant `acme` = `P0_TENANT` v env, Keycloak atribut `tenant_id`, RLS v paměti (M1), klíče `k-{tenant}-{zakazka}-role` z rolegen | tenant = řádek `org.tenants` + Keycloak **organizace/atributy** v jednom realmu + namespace `tenant-<id>` pro role pody + CNP + klíče + RLS v `org.*` | nic nového v rolích – šablony `{tenant}` už existují |
| Registr `org.zakazky`, `org.agents`, `org.agent_events`, `org.approvals` plní harness/aktivity; čte se SQL | **Governance MCP server** (`org_reader`) → AG-UI server → GUI; zápisy jen z workflow | registr přestává být vedlejší produkt měření |
| Klasifikační brána = proces bez reálného dotazníku (dogfooding: K1–K5 = ne) | K1–K6 jako A2UI formulář v P1a; profil → OPA data zakázky; `high-risk` zamyká pass^k | poprvé reálná data v `org.zakazky.profil` |
| Stop = `stopped` flag v instanci (O-1) | stop per zakázka a **per tenant** z GUI (autonomie.md T5): pause instancí, 60 s grace sandboxů, gateway `Block` klíčů tenanta, PEP paměti deny | nový Dapr event `stop` + aktivita nad gateway/OPA |
| Mock GitHub, mock mirror, mock upstream modelu; harness vydává TLS Secrety | zůstává pro měření; ostrý běh jen na vyžádání; **cert-manager + ESO** nahradí harness-issued Secrety (P3-6) | – |

## GUI nad celou firmou – co to je a co ne

Rozhodnutí z cílové architektury: **vlastní frontend přes AG-UI (spec 1.0, 2026-09-17) + A2UI v0.9.1 jako payload za
adaptérem** (ag-ui.md, a2ui.md, ověřeno 2026-10-20). GUI není chat s jedním agentem – je to **řídicí pult firmy**: jeden
backend (AG-UI server v Pythonu, FastAPI + `ag-ui-protocol` 1.0) a jeden frontend (TypeScript, React, `@ag-ui/core` 1.0.x +
A2UI React renderer 0.9.1). Každá zakázka = jeden AG-UI *thread*; firma = seznam threadů + průřezové pohledy ze čtecích
MCP serverů.

```mermaid
flowchart LR
    subgraph GUI["Frontend (TypeScript/React, vlastní)"]
        Z[Zakázky: tok P1→P5, HITL s důvodem, stop]
        F[Firma: role, registr agentů, evaly, FinOps, risk register, governance report]
        D[A2UI dialogy: zadání, klasifikace K1–K6, Account dotazy, approval]
    end
    GUI -->|"AG-UI 1.0 (SSE, RunAgentInput, protocolVersion)"| GW[agentgateway: OIDC token člověka ↔ thread/tenant]
    GW --> AGS[AG-UI server (FastAPI, adaptér AG-UI/A2UI)]
    AGS -->|"raise_event hitl:*, stop; schedule_new_workflow"| DAPR[Dapr Workflow org.zakazka]
    AGS -->|"MCP tools/resources (org_reader)"| GOV[Governance MCP: org.*, FinOps, evaly]
    DAPR -->|"ACTIVITY_SNAPSHOT/DELTA, MESSAGES, SUBAGENT_*"| AGS
    DAPR --> ROLE[Role pody (Kata): Account dialog → A2UI payload]
    ROLE -->|"A2A task + A2UI část"| AGS
    AGS --> KC[Keycloak: člověk + tenant_id + role; on_behalf_of do tokenu zakázky]
```

| Pohled v GUI | Zdroj pravdy | Protokol / payload | HITL / akce |
|---|---|---|---|
| **Zakázka** – stav instance, aktivity rolí, artefakty (hash, odkaz), rozpočet vs. útrata | Dapr workflow (`get_workflow_state` + custom status) + ledger (`agent_events`) | AG-UI `ACTIVITY_SNAPSHOT/DELTA` (JSON Patch), `SUBAGENT_STARTED/FINISHED` per role | H1–H5, `rozpocet`, `hitl:pravnik`: A2UI formulář s **povinným důvodem**, token do `raise_event`; **stop** zakázky |
| **Nová zakázka** – poptávka, rozpočet, tenant, dialog s Account (≤ 3 kola), klasifikace K1–K6 | role Account (Agent SDK) + workflow P1/P1a | AG-UI `MESSAGES` s disclosure T7 + A2UI dotazník | odpovědi = `raise_event klasifikace`; H1 |
| **Firma / role** – verze rolí, eval gate (L0–L3, pass^k), úroveň autonomie A0–A3 per role × tenant, pozastavené role | `org.role_definitions`, `org.eval_gates`, `org.agent_events` | MCP resources (Governance MCP) | posun autonomie nahoru (vlastník procesu, důvod → `autonomy_changed`); pozastavení role = OPA `suspended` |
| **Registr agentů** (T12) – instance rolí per zakázka, SVID, klíč hash, poslední aktivita | `org.agents`, `org.agent_events` | MCP | jen čtení |
| **FinOps** – útrata per zakázka/role/tenant, 30d okno, cap; alert 80 % | `org.zakazky.spent_by_role`, `budget_usage` gateway, ledger ClickHouse (P3-6) | MCP | zvýšení capu z HITL `rozpocet` (P3-6; dnes jen pauza) |
| **Governance** – risk register, incidenty X1, post-mortemy, týdenní report (úplnost T11–T15), export JSONL per tenant | `org.risk_register`, `org.risk_events`, `org.postmortems` | MCP + stažení souboru | stop **tenanta** (governance, A3 člověk zákazníka) |
| **Audit** – kdo co schválil, kdy, s jakým důvodem, podpis OpenBao | `org.approvals` (append-only, podepsané) | MCP | jen čtení |

**Pozn. Adam (návrh, k rozhodnutí):**
- **Jeden AG-UI server pro celou firmu, ne jeden per role.** Role nemají vlastní AG-UI endpoint; jejich výstup k člověku
  teče přes workflow (aktivita `notify` → event stream threadu). Důvod: thread = zakázka = jednotka autorizace, stopu
  a auditu; role jsou subagenti (`SUBAGENT_*`). Alternativa „AG-UI per role" dává hezčí streaming, ale rozbíjí hranici
  sandboxu (role by musela mít ingress).
- **A2UI jen za adaptérem** (`a2ui-core` 0.4.0 breaking co 14 dní): vlastní schéma formulářů (approval, klasifikace,
  dotaz) → převod na A2UI v0.9.1 na serveru; renderer v GUI za jedním modulem. Když v1.0 rendererů nedorazí, nahradí se
  vlastním JSON-schema formulářem bez změny workflow.
- **Žádný CopilotKit v produkční cestě**: `@ag-ui/core` + vlastní SSE klient stačí; CopilotKit jen k ověření kompatibility
  v harnessu (riziko: ekosystém v migraci na 1.0, ag-ui.md).
- **Auth na transportu** (spec AG-UI auth neřeší): Keycloak OIDC login člověka v GUI, token na každém `RunAgentInput`;
  agentgateway (nebo AG-UI server) mapuje `sub`+`tenant_id` ↔ thread; cizí thread = 404.

## Kroky

| Krok | Co se postaví | Zdroj pravdy → nástroj | Co se měří | Hotovo, když |
|---|---|---|---|---|
| **P3-1** AG-UI server + minimální GUI nad HITL | FastAPI AG-UI server (`tools/agui_server/`): `POST /agui/run` (SSE, `RUN_STARTED` s `protocolVersion`), thread = `zakazka_id`, eventy z ledgeru/Dapr stavu (`ACTIVITY_*`, `MESSAGES` s T7 disclosure, `SUBAGENT_*` per role, `RUN_FINISHED.outcome=interrupt` na HITL); akce `approve/reject` s důvodem → `raise_event hitl:<bod>` (token vázaný na artefakt hash jako dnes), `stop`; React GUI (`gui/`, Vite, `@ag-ui/core` 1.0.x): seznam zakázek, detail threadu, approval formulář; obraz `gui` + Deployment/Ingress přes agentgateway (HTTPS listener `gui.platform.internal`, OIDC Keycloak) | `procesy.md` HITL body H1–H5, `app.py hitl()` → AG-UI server + GUI; `roles.json.disclosure` → kanál `agui` | harness **U-1** (Playwright headless v `measure`, nový `e2e=p3-1`): U1a login člověka (Keycloak) a seznam zakázek; U1b thread zakázky streamuje aktivity 4 rolí v pořadí; U1c H1 schválení **bez důvodu odmítnuto**, s důvodem → `HITL_APPROVED by=<sub>` v ledgeru + řádek `org.approvals` s důvodem; U1d cizí thread 404; U1e disclosure T7 v první zprávě každé role; U1f stop zakázky → instance `Pozastaveno`, sandbox pod ukončen do 60 s; U1g `protocolVersion` na `RUN_STARTED` a interrupt–resume vzor dle spec 1.0 | U-1 100 % na AKS; zakázka projde P1→P5 jen klikáním v GUI (žádný `/schvaluji`) |
| **P3-2** tenant model | tabulka `org.tenants` (id, název, profil, stav, SLA, kontakt A3); Keycloak: **jeden realm**, tenant jako atribut + skupina (`tenant_id` mapper už existuje), lidé zákazníka s rolí `zakaznik`, service accounty `svc-{tenant}-{proces}`; `on_behalf_of` = schvalovatel vstupu v tokenu zakázky (Q6, token exchange v P3-6, do té doby claim z Keycloaku); RLS per `tenant_id` ve všech `org.*` tabulkách (jako M1), `org_reader/org_writer` role; rolegen `--tenant` → namespace `tenant-<id>` pro role pody, CNP per namespace (jen gateway, DNS), OPA data `tenants[]`, gateway klíče `k-{tenant}-{zakazka}-role` s rozpočtem tenanta; AG-UI server filtruje thready podle `tenant_id` z tokenu | `roles/*.yaml` (`{tenant}` šablony), `realm-p0.json` → `realm-platform.json`, `metriky.md` §4 schéma | harness **T-1** (`e2e=p3-2`): T1a dva tenanti `acme` (dogfooding) + `beta` (zákazník), zakázka v každém; T1b role pody v `tenant-beta` namespace, CNP: pod beta nedosáhne na pod acme ani na Postgres přímo; T1c RLS: `org_reader` s `app.tenant_id=beta` nevidí zakázky acme (0 řádků), ani přes agregace; T1d klíče gateway: klíč beta má `metadata.tenant=beta`, útrata se sčítá per tenant; T1e GUI: uživatel beta vidí jen své zakázky, admin platformy vidí tenant `platform` průřez; T1f SPIRE ID role obsahuje tenant (`spiffe://platform/role/<role>/beta`) | T-1 100 %; dvě zakázky dvou tenantů paralelně na jednom clusteru bez společného stavu mimo `platform` |
| **P3-3** GUI nad celou firmou | Governance MCP server (`tools/governance_mcp/`, `org_reader`, resources: role, registr, evaly, FinOps, risk register, approvals, SLA) → AG-UI server (tools/resources do `STATE_SNAPSHOT` a stránek); GUI stránky: Firma (role × tenant, autonomie, eval gate, suspend), Registr agentů, FinOps (zakázka/role/tenant, 30d, alert 80 %), Governance (risk register, incidenty, post-mortemy, týdenní report, export JSONL), Audit; akce: posun autonomie s důvodem (`autonomy_changed`), stop tenanta, založení zakázky (A2UI formulář + dialog s Account ≤ 3 kola) | `metriky.md` §4–6, `autonomie.md` (stop, A0–A3) → Governance MCP + GUI | harness **U-2** (`e2e=p3-3`): U2a každý pohled má data z `org.*` (ne z ledgeru harnessu); U2b založení zakázky z GUI: Account dialog (mock model) 2 kola, H1 → běží; U2c posun autonomie A1→A2 bez splněných podmínek **odmítnut** (metriky), se splněnými zapsán s důvodem; U2d stop tenanta: obě zakázky tenanta `Pozastaveno`, gateway klíče `Block`, paměť deny (M1 PEP), SPIRE entries zůstávají; U2e governance report vyjmenuje chybějící T11–T15 pro zakázku bez klasifikace; U2f export JSONL per tenant jen vlastní řádky; U2g Governance MCP se `org_writer` tokenem = deny (jen čtení) | U-2 100 %; Adam řídí dogfooding zakázku z GUI, bez SQL a bez harnessu |
| **P3-4** klasifikační brána, čl. 50, SLA naostro | P1a jako aktivita workflow: A2UI dotazník K1–K6 zadavateli + Account (GUI), výsledek → `org.zakazky.profil` + OPA data (`high-risk` zamyká pass^k, N2/N3 A2); `odmitnout` ukončí zakázku s auditem, `nejasne` → H1a právník (`hitl:pravnik`); čl. 50: disclosure T7 na všech kanálech (AG-UI, issue, PR, **e-mail a ticket adaptér zákazníka** – SMTP/REST stub v clusteru jako mock), T8 značení výstupů pro lidi (metadata artefaktu `generated_by`, kód = otevřená otázka, nebrání); SLA per proces (procesy.md) jako timery v workflow + `org.sla_events` (porušení → eskalace vlastníkovi v GUI) | `autonomie.md` K1–K6 + profily, `regulace.md` T7/T8, `procesy.md` SLA → aktivity + OPA data + GUI | harness **K-1** (`e2e=p3-4`): K1a K2=ano → profil `high-risk-III/4`, OPA `pass_k=false`, pokus o posun autonomie deny; K1b K1=ano → zakázka `Odmitnuto`, řádek `org.approvals` s auditem, žádný role pod nespuštěn; K1c K4=ano → `hitl:pravnik`, do stanoviska jako high-risk; K1d disclosure v mock e-mailu a ticketu (`/_debug/messages` mock adaptéru) i v GUI; K1e artefakty pro lidi nesou `generated_by`, mezikroky ne; K1f SLA timer P1 (zkrácený) vyprší → `org.sla_events` + eskalace v GUI, zakázka pokračuje (SLA ≠ stop) | K-1 100 %; každá zakázka v registru má profil a každý kanál k lidem disclosure (governance report = 0 chybějících) |
| **P3-5** O-3 multi-tenant harness | složení T-1 + M-E3 přes dva tenanty **v clusteru** (paměť MCP server s PEP, role beta se ptá na fakta acme → 0 záznamů, kanárky), stop per tenant uprostřed běhu (P3-3 U2d, ale s běžícími Kata pody a otevřenými HITL), obnovení (resume) tenanta: HITL se znovu zobrazí, útrata navazuje; SLA a FinOps report per tenant | `model-pameti.md` M-E3, `autonomie.md` stop → `tools/harness_p1_k8s --step p3-5` | **O-3** (`e2e=p3-5`): O3a M-E3 3/3 epochy přes gateway a MCP server (ne přímo SQL); O3b stop tenanta beta při běžící roli vývojář: pod ukončen ≤ 60 s, checkpoint uložen, acme běží dál; O3c resume beta: HITL H2 znovu v GUI, approval projde; O3d žádný `record.id`/`zakazka_id` tenanta beta ve spanech/ledgeru acme (ClickHouse dotaz); O3e útrata per tenant = součet klíčů tenanta ± eventually consistent (P1-G) | O-3 100 % na AKS = **P3 měřitelně hotové** pro „první externí zákazník“ |
| **P3-6** produkční hrany (nezávislé na P3-1…5, průběžně) | token exchange SVID → Keycloak token s `on_behalf_of` (Q6) v gateway místo claimu; cap zakázky i v gateway (`budgets` per zakázka klíč-skupina) a zvýšení capu z HITL `rozpocet` v GUI; per-request ledger `request_logs` → ClickHouse přes Collector (FinOps pohled bez `budget_usage`); cert-manager + External Secrets Operator (Key Vault) místo harness-issued Secretů; SPIRE bundle do namespace rolí bez `insecure_bootstrap`; registr plněný workflow (ne harnessem); TLS listener OpenBao; VNet integrace Flexible Serveru; L2 s živým modelem jako ruční běh | p2-role.md changelog „otevřené do P3“ → `infra/`, `rolegen`, `app.py` | existující harnessy (P21b/P23/P26) + rozšíření: E1 ESO vydá Secret z Key Vaultu, harness žádný Secret nevytváří; E2 token zakázky nese `on_behalf_of=<sub schvalovatele H1>` z exchange, ověřeno JWKS; E3 cap v gateway: 2. zakázka s `budget 0.01` dostane 429 z gateway, ne jen z `budget_gate`; E4 FinOps v GUI z ClickHouse = ± `budget_usage` | každá položka samostatný PR s měřením; žádný „harness vydává tajemství“ v produkční cestě |

## Co zůstává zjednodušené i v P3 (vědomě)

| Zjednodušení | Proč zůstává | Kdy |
|---|---|---|
| Mock model, mock GitHub, mock mirror, mock e-mail/ticket adaptér v clusteru | měří se platforma, ne model; ostrý běh (živý model, GitHub, SMTP zákazníka) jen na vyžádání s PAT/klíčem | ostrý běh po P3-4 |
| Jeden Keycloak realm, tenant jako atribut/skupina (ne realm per tenant) | realm per tenant = N× konfigurace, import, klienti; atributy stačí pro RLS/OPA/gateway; realm per tenant až když zákazník chce vlastní IdP federaci | P4 / na vyžádání |
| GUI bez i18n, bez mobilu, jeden design systém; A2UI renderer za vlastním modulem | A2UI v1.0 renderery jen „planned“; vlastní formulářový fallback | po stabilizaci A2UI v1.0 |
| Dapr bez operátoru, HTTP uvnitř clusteru, mTLS jen tam, kde je SPIRE + gateway | dev cluster; plná mTLS mesh (Cilium/Dapr) je samostatná změna | P4 |
| SLA jako timery + eskalace, ne jako smluvní reporting | nejdřív měřit; smlouva se zákazníkem až po O-3 | P4 |
| Čl. 50 T8 pro kód (značení) | otevřená otázka guidelines 20.7.2026 (regulace.md); metadata artefaktu stačí | až po výkladu |

## Rizika

| Riziko | Dopad | Zmírnění |
|---|---|---|
| AG-UI 1.0 ekosystém v migraci; `ag-ui-protocol` 1.0.0 bez patche, klienti různě vyžadují `protocolVersion` | P3-1 | vlastní tenký server nad `ag-ui-protocol` (jen event typy a SSE), žádný framework-specific middleware; U1g test spec shody; pin verzí v lockfile |
| A2UI breaking každých ~14 dní, renderery v1.0 nedostupné | P3-1, P3-3, P3-4 | A2UI jen za adaptérem; vlastní schéma formulářů; test, že GUI projde U-1/K-1 i s fallback rendererem |
| GUI = nový druh práce (frontend, Playwright v CI, Kata ne, ale obraz a ingress ano); měřicí smyčka ještě delší | všechny U-* | GUI build v `images` jen při změně `gui/`; Playwright testy proti clusteru v `measure` s vlastním jobem; vývoj GUI lokálně proti mock AG-UI serveru (fixture z ledgeru) |
| Multi-tenant na jednom clusteru: chyba v RLS/OPA/CNP = únik mezi zákazníky (třída A) | P3-2, P3-5 | T-1 a O-3 negativní testy (každý pohled, každá tabulka, každý namespace); `platform` tenant jen pro admina; export JSONL per tenant jako důkaz |
| Stop per tenant uprostřed Kata podu: 60 s grace, checkpoint, resume HITL – dosud změřeno jen `stopped` flag | P3-3, P3-5 | O3b/O3c; Dapr pause/resume API ověřit na 1.18 (autonomie.md „ověřit API“) |
| Keycloak token člověka v GUI + `on_behalf_of` v tokenu zakázky bez exchange (P3-2) = claim, ne důkaz | P3-2 | P3-6 E2 token exchange; do té doby `on_behalf_of` jen informativní, audit z `org.approvals` |
| Cena: dva tenanti = dvojnásobek role podů v měření; GUI obraz + Playwright v CI | všechny | pool kata jen během `measure`; O-3 jako jediný „velký“ běh; cluster `stop` mimo měření (jako P1/P2) |

## Postup

| Krok | Stav |
|---|---|
| P3-1 AG-UI server + minimální GUI nad HITL | ⬜ |
| P3-2 tenant model | ⬜ |
| P3-3 GUI nad celou firmou | ⬜ |
| P3-4 klasifikační brána, čl. 50, SLA naostro | ⬜ |
| P3-5 O-3 multi-tenant harness | ⬜ |
| P3-6 produkční hrany | ⬜ (průběžně, položka = PR) |

Postup práce jako v P2: krok na větvi → `measure` s `e2e=p3-n` na AKS → PR → merge → Flux z `main` → cluster `stop`.
Nový `measure` job pro Playwright (Chromium v runneru, cíl `gui.platform.internal` přes port-forward na agentgateway).

## Changelog
- 2026-10-26: první verze – návrh po uzavření P2; GUI nad celou firmou jako P3-1 + P3-3 (AG-UI 1.0 vlastní server,
  A2UI v0.9.1 za adaptérem), tenant model P3-2, brána/čl. 50/SLA P3-4, O-3 P3-5, produkční hrany P3-6 z otevřených
  položek P2. Čeká na Adamovo potvrzení rozsahu a pořadí.
