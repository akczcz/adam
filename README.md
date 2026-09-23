# Adam

Adam je můj osobní multiagentní pomocník – virtuální představa mě samotného.
Postupně získává znalosti (`knowledge/`), dovednosti (`.claude/skills/`)
a specializované agenty (`.claude/agents/`), kteří za mě řeší různá témata.

Prostředí: **Claude Code** (desktop app nebo terminál) spuštěný v kořeni tohoto repozitáře.

## Struktura

```
adam/
├── CLAUDE.md                  # Kdo je Adam – identita, principy, pravidla práce
├── knowledge/                 # Verzovaná znalostní báze (Markdown)
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
└── inbox/                     # Odkládací místo pro poznámky, odkazy, podklady ke zpracování
```

## Jak Adam roste

1. Nová oblast zájmu → nová složka v `knowledge/`.
2. Opakující se postup → nový skill v `.claude/skills/`.
3. Oblast, která potřebuje samostatnou roli → nový agent v `.claude/agents/`.
4. Vše se commituje, takže je vidět, jak se Adam v čase vyvíjí.

## Rychlý start

```bash
cd ~/Documents/Github/akczcz/adam
claude
```

Příklady příkazů pro Adama:
- „Použij protocol-scout a zkontroluj, co je nového v MCP.“
- „Porovnej A2A a MCP z pohledu autentizace a navrhni, jak je kombinovat v naší platformě.“
- „Zpracuj poznámky v inbox/ a zařaď je do knowledge/.“
