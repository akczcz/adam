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
│   └── protocols/             # Oblast 1: AI protokoly pro multiagentní platformy
│       ├── overview.md        # Mapa vrstev a vztahů mezi protokoly
│       ├── a2a.md
│       ├── mcp.md
│       ├── a2ui.md
│       └── ag-ui.md
├── .claude/
│   ├── skills/
│   │   └── protocol-research/ # Postup, jak zkoumat a aktualizovat znalosti o protokolech
│   └── agents/
│       └── protocol-scout.md  # Podagent, který hlídá novinky v protokolech
├── worker/                    # MCP server nad knowledge/ pro Cloudflare Workers
├── tools/                     # Smoke testy proti MCP serverům
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

1. Nová oblast zájmu → nová složka v `knowledge/`.
2. Opakující se postup → nový skill v `.claude/skills/`.
3. Oblast, která potřebuje samostatnou roli → nový agent v `.claude/agents/`.
4. Vše se commituje, takže je vidět, jak se Adam v čase vyvíjí.

## Licence

[MIT](LICENSE) – kód i obsah znalostní báze.
