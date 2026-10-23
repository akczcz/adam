# Adam

Adam je můj osobní multiagentní pomocník – virtuální představa mě samotného.
Postupně získává znalosti (`knowledge/`), dovednosti (`.claude/skills/`)
a specializované agenty (`.claude/agents/`), kteří za mě řeší různá témata.

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
│   └── observability/         # Vrstva 5: Observabilita a evaluace
│       ├── overview.md        # Tok dat, síto, harnessy O1/O2
│       ├── kriteria.md        # Tři otázky O1–O3, kritéria B1–B5
│       ├── standardy.md       # GenAI semconv, co emitují komponenty, kde se trace přeruší
│       └── evaluace.md        # Síto eval frameworků, vrstvy L0–L5, metriky čl. 15
├── .claude/
│   ├── skills/
│   │   ├── protocol-research/  # Postup, jak zkoumat protokoly
│   │   ├── framework-research/ # Postup, jak prověřovat frameworky a licence
│   │   ├── gateway-research/   # Postup, jak prověřovat model gateway a FinOps
│   │   ├── identity-research/  # Postup pro identitu, autorizaci, audit a AI Act
│   │   └── observability-research/  # Postup pro tracing, metriky a evaluaci agentů
│   └── agents/
│       ├── protocol-scout.md   # Podagent na novinky v protokolech
│       ├── framework-scout.md  # Podagent na licenční a governance prověrku
│       ├── gateway-scout.md    # Podagent na gateway, Anthropic passthrough a FinOps
│       ├── identity-scout.md   # Podagent na identitu agentů, policy a regulaci
│       └── observability-scout.md  # Podagent na OTEL, backendy a evaluaci
├── worker/                    # MCP server nad knowledge/ pro Cloudflare Workers
├── tools/                     # Smoke testy a harnessy (Dapr+Claude restart, gateway G1, identita I2, trace O1, evaluace O2)
├── docs/                      # Architektura a postupy
└── inbox/                     # Odkládací místo pro podklady ke zpracování
```

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

## Rychlý start – MCP server

```bash
cd worker
npm install
cp .dev.vars.example .dev.vars    # vyplň testovací tokeny
npm run dev
```

Nasazení a připojení klientů popisuje [docs/vlastni-instance.md](docs/vlastni-instance.md).

## Jak Adam roste

Vrstvy platformy se otevírají postupně – pořadí, stav a společný postup jsou
v [knowledge/platforma/overview.md](knowledge/platforma/overview.md).

1. Nová oblast zájmu → nová složka v `knowledge/`.
2. Opakující se postup → nový skill v `.claude/skills/`.
3. Oblast, která potřebuje samostatnou roli → nový agent v `.claude/agents/`.
4. Vše se commituje, takže je vidět, jak se Adam v čase vyvíjí.

## Licence

[MIT](LICENSE) – kód i obsah znalostní báze.
