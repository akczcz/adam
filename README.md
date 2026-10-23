# Adam

Adam je můj osobní multiagentní pomocník – virtuální představa mě samotného.
Postupně získává znalosti (`knowledge/`), dovednosti (`.claude/skills/`)
a specializované agenty (`.claude/agents/`), kteří za mě řeší různá témata.

Hlavní téma repozitáře je **návrh autonomní multiagentní platformy – „virtuální IT firmy“**:
osm vrstev (protokoly, frameworky, gateway, identita, observabilita, paměť, sandboxy, organizace),
každá prověřená stejným postupem (kritéria → skill → agent → síto → hloubkové kolo → rozhodnutí → harness).
Stav k 2026-10-23: **všech osm vrstev rozhodnuto a změřeno harnessy**; další postup je produkt ve fázích P0–P3.

Znalostní báze se dá konzumovat dvěma cestami:

- **lokálně** – Claude Code spuštěný v kořeni tohoto repozitáře,
- **vzdáleně** – jako MCP server běžící na Cloudflare Workers.

## Struktura

```
adam/
├── CLAUDE.md                  # Kdo je Adam – identita, principy, pravidla práce
├── knowledge/                 # Verzovaná znalostní báze (Markdown) – zdroj pravdy
│   ├── README.md              # Konvence pro znalostní soubory
│   ├── platforma/             # Mapa vrstev platformy, pořadí otevírání, cílová architektura
│   │   ├── overview.md        # Které vrstvy, v jakém stavu, společný postup
│   │   └── cilova-architektura.md  # Živý soubor rozhodnutí po vrstvách
│   ├── protocols/             # Vrstva 1: AI protokoly pro multiagentní platformy
│   │   ├── overview.md        # Mapa vrstev a vztahů mezi protokoly
│   │   ├── a2a.md
│   │   ├── mcp.md
│   │   ├── a2ui.md
│   │   └── ag-ui.md
│   ├── frameworks/            # Vrstva 2: Agentní frameworky a runtimy
│   │   ├── overview.md        # Mapa vrstev, široké síto kandidátů, top 3
│   │   ├── kriteria.md        # Hodnoticí rubrika
│   │   ├── licencni-vzorce.md # Licenční pasti a jak je poznat
│   │   ├── durable-execution.md
│   │   ├── kagent.md
│   │   ├── dapr-agents.md
│   │   └── microsoft-agent-framework.md
│   ├── gateway/               # Vrstva 3: Model gateway a FinOps
│   │   ├── overview.md        # Síto kandidátů, kolo 2, harness G1
│   │   └── kriteria.md        # Hodnoticí rubrika (Anthropic passthrough, rozpočty, identita)
│   ├── identity/              # Vrstva 4: Identita, autorizace a governance
│       ├── overview.md        # Tok identity, síto, kolo 2, harness I2
│       ├── kriteria.md        # Čtyři otázky I1–I4, kritéria N1–N6
│       ├── standardy.md       # MCP auth, A2A, ID-JAG, Entra Agent ID
│       ├── regulace.md        # AI Act po Omnibusu, ISO 42001, NIST – požadavky T1–T15
│       ├── keycloak.md        # Token exchange V2 změřený harnessem
│       ├── agentgateway-identity.md  # Gateway jako PEP: jwtAuth, extAuthz, exchange
│       └── spire.md           # Workload identita vs. Dapr sentry
│   ├── observability/         # Vrstva 5: Observabilita a evaluace
│       ├── overview.md        # Tok dat, síto, harnessy O1/O2
│       ├── kriteria.md        # Tři otázky O1–O3, kritéria B1–B5
│       ├── standardy.md       # GenAI semconv, co emitují komponenty, kde se trace přeruší
│       └── evaluace.md        # Síto eval frameworků, vrstvy L0–L5, metriky čl. 15
│   ├── memory/                # Vrstva 6: Paměť a znalosti
│       ├── overview.md        # Čtyři druhy paměti, síto, model původu, harness M1
│       ├── nativni-schopnosti.md  # Co dává Claude, Dapr, MCP a OTEL
│       ├── model-pameti.md    # Schéma záznamu s původem, poisoning, životní cyklus, evaly
│       └── kriteria.md        # Otázky M1–M4, kritéria B1–B6
│   ├── sandbox/               # Vrstva 7: Sandboxy a pracovní prostředí
│       ├── overview.md        # Co se izoluje, síto kandidátů, kolo 2, harness S1
│       ├── azure-kata-gvisor.md   # AKS Pod Sandboxing, gVisor na AKS, egress a cena
│       ├── anthropic-sandboxing.md # sandbox-runtime, Claude Code a Agent SDK sandbox
│       ├── egress-agentgateway.md  # CONNECT proxy, git přes gateway, Inspect k8s provider
│       └── kriteria.md        # Otázky S1–S4, kritéria B1–B6
│   └── organization/          # Vrstva 8: Organizační vrstva (návrhová)
│       ├── overview.md        # Tok zakázky, role, kolo 1, otázky Q1–Q9
│       ├── procesy.md         # Katalog procesů P1–P5, X1–X2, mapování na vrstvy
│       ├── autonomie.md       # Nevratné akce N1–N10, timeouty, stop, brána, pass^k
│       ├── role.md + roles/   # Šablona role (YAML), profily sandboxu, Rego data per roli
│       ├── metriky.md         # Metriky, zdroje dat, registr agentů T12, risk register T11
│       └── kriteria.md        # Otázky O1–O4, zásady návrhu
├── .claude/
│   ├── skills/
│   │   ├── protocol-research/  # Postup, jak zkoumat protokoly
│   │   ├── framework-research/ # Postup, jak prověřovat frameworky a licence
│   │   ├── gateway-research/   # Postup, jak prověřovat model gateway a FinOps
│   │   ├── identity-research/  # Postup pro identitu, autorizaci, audit a AI Act
│   │   ├── observability-research/  # Postup pro tracing, metriky a evaluaci agentů
│   │   ├── memory-research/    # Postup pro paměť, znalosti, původ a výmaz
│   │   ├── sandbox-research/   # Postup pro sandboxy, izolaci a pracovní prostředí agentů
│   │   └── organization-design/ # Návrhová metoda: procesy → role → hranice autonomie
│   └── agents/
│       ├── protocol-scout.md   # Podagent na novinky v protokolech
│       ├── framework-scout.md  # Podagent na licenční a governance prověrku
│       ├── gateway-scout.md    # Podagent na gateway, Anthropic passthrough a FinOps
│       ├── identity-scout.md   # Podagent na identitu agentů, policy a regulaci
│       ├── observability-scout.md  # Podagent na OTEL, backendy a evaluaci
│       ├── memory-scout.md     # Podagent na memory frameworky, DB a původ faktů
│       ├── sandbox-scout.md    # Podagent na izolaci, egress a pracovní prostředí
│       └── organization-designer.md # Podagent na návrh rolí, procesů a schvalovacích bodů
├── worker/                    # MCP server nad knowledge/ pro Cloudflare Workers
├── tools/                     # Smoke testy a harnessy (Dapr+Claude restart, gateway G1, identita I2, trace O1, evaluace O2, paměť M1, sandbox S1, organizace O-1, P0 dogfooding O-2, rolegen R1)
├── docs/                      # Architektura a postupy
└── inbox/                     # Odkládací místo pro podklady ke zpracování
```

## Cílová architektura (stav 2026-10-23)

Živý soubor rozhodnutí: [knowledge/platforma/cilova-architektura.md](knowledge/platforma/cilova-architektura.md)
(celkový diagram, přijatá rizika, fáze produktu). Mapa vrstev a postup: [knowledge/platforma/overview.md](knowledge/platforma/overview.md).

| Vrstva | Rozhodnutí | Harness (`tools/`) |
|---|---|---|
| Protokoly | MCP k nástrojům; A2A za adaptérem; AG-UI + A2UI k lidem | `smoke_mcp_2026_07_28.py` |
| Frameworky a orchestrace | Claude Agent SDK + Dapr Agents / Dapr Workflows | `harness_dapr_claude` (restart uprostřed HITL) |
| Model gateway a FinOps | agentgateway (nativní `/v1/messages`, rozpočty per klíč) | `harness_gateway_g1` (mock 21/21, live 2/2) |
| Identita a governance | Keycloak + SPIRE + token exchange v agentgateway + OPA-Envoy + OpenBao | `harness_identity_i2` (8/8 s OPA) |
| Observabilita a evaluace | OTEL Collector → ClickHouse + Prometheus; Langfuse; Inspect AI + promptfoo + MLflow | `harness_observability_o1` (9/9), `harness_eval_o2` (6/6) |
| Paměť a znalosti | vlastní MCP server paměti s PEP nad Postgres + pgvector (RLS, fakt s původem, `proposed → approved`) | `harness_memory_m1` (11/11) |
| Sandboxy | Kata (AKS Pod Sandboxing) / gVisor + `sandbox-runtime` + agentgateway jako jediný egress; devcontainer, Playwright MCP, wasmtime | `harness_sandbox_s1` (11/11 lokálně, microVM část `aks/`) |
| Organizace | procesy jako Dapr Workflows, role jako YAML svazek, executor nevratných akcí s approval tokenem, autonomie rozšiřovaná měřením | `harness_org_o1` (9/9) |

Všechny harnessy běží lokálně bez Dockeru; výsledky (JSON) a sekce „Pasti“ jsou v README každého harnessu.
Fáze produktu P0 (dogfooding) běží: harness [`tools/harness_p0_o2`](tools/harness_p0_o2/README.md) skládá všechny vrstvy do jednoho běhu,
[`tools/rolegen`](tools/rolegen/README.md) generuje z definic rolí konfigurace všech vrstev
(stav v [knowledge/platforma/produkt.md](knowledge/platforma/produkt.md)).
Nálezy, které se opakují napříč vrstvami, jsou v [knowledge/frameworks/licencni-vzorce.md](knowledge/frameworks/licencni-vzorce.md) (24 vzorců).

## Dokumentace

| Dokument | Pro koho |
|---|---|
| [docs/architektura.md](docs/architektura.md) | Jak to funguje, diagramy, rozhodnutí a jejich důvody, omezení |
| [docs/pripojeni-klienta.md](docs/pripojeni-klienta.md) | Chci se **připojit** k běžícímu serveru (Claude Desktop, Claude Code) |
| [docs/vlastni-instance.md](docs/vlastni-instance.md) | Chci si postavit **vlastní** instanci od nuly |
| [knowledge/README.md](knowledge/README.md) | Konvence pro psaní znalostních souborů |

## Rychlý start – lokálně

```bash
git clone https://github.com/akczcz/adam.git
cd adam
claude
```

Příklady příkazů pro Adama:
- „Použij protocol-scout a zkontroluj, co je nového v MCP."
- „Porovnej A2A a MCP z pohledu autentizace a navrhni, jak je kombinovat v naší platformě."
- „Zpracuj poznámky v inbox/ a zařaď je do knowledge/."
- „Použij sandbox-scout a ověř, jestli agentgateway 1.7 už hlídá loopback u dynamic backendu."
- „Navrhni roli SRE jako YAML podle organization-design."
- „Spusť harness S1 a porovnej výsledek s results/."

## Rychlý start – MCP server

```bash
cd worker
npm install
cp .dev.vars.example .dev.vars    # vyplň testovací tokeny
npm run dev
```

Nasazení a připojení klientů popisuje [docs/vlastni-instance.md](docs/vlastni-instance.md).

## Jak Adam roste

Vrstvy platformy se otevíraly postupně – pořadí, stav a společný postup jsou
v [knowledge/platforma/overview.md](knowledge/platforma/overview.md). Rešeršní fáze je uzavřená;
další krok je produkt (fáze P0 dogfooding zakázka → P1 platforma na AKS → P2 role naostro → P3 externí zákazník).
Znalosti se dál udržují: každá vrstva má „Co ověřit dál“ a skill se sekcí pastí; před každou fází produktu
se verze a stavy specifikací re-verifikují z primárních zdrojů.

1. Nová oblast zájmu → nová složka v `knowledge/`.
2. Opakující se postup → nový skill v `.claude/skills/`.
3. Oblast, která potřebuje samostatnou roli → nový agent v `.claude/agents/`.
4. Vše se commituje, takže je vidět, jak se Adam v čase vyvíjí.

## Licence

[MIT](LICENSE) – kód i obsah znalostní báze.
