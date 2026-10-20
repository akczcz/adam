---
tema: A2UI (Agent-to-User Interface)
naposledy_overeno: 2026-10-20
zralost: preview (v0.9.1 produkční, v1.0 stále RC; renderery v1.0 jen plánované)
primarni_zdroje:
  - https://github.com/a2ui-project/a2ui
  - https://a2ui.org/
  - https://developers.googleblog.com/introducing-a2ui-an-open-project-for-agent-driven-interfaces/
  - https://developers.googleblog.com/en/a2ui-and-mcp-apps/
---

# A2UI – Agent-to-User Interface

## Účel
Umožnit (i vzdálenému) agentovi dodat bohaté interaktivní UI bez posílání spustitelného kódu.
Agent popíše *co* zobrazit, klient rozhodne *jak* to vykreslit.

## Aktuální stav
- Iniciováno Googlem (open-source, prosinec 2025); CopilotKit jako launch/design partner.
- Repozitář přesunut z `google/A2UI` do **`a2ui-project/a2ui`** (GitHub redirect; ověřeno 2026-10-20).
  Governance nedokumentovaná – žádná nadace ani TSC, copyright Google; datum a důvod přesunu nenalezeny.
- Aktuální produkční verze: **v0.9.1**; **v1.0 stále release candidate** (dříve v0.10) – stabilní bude
  „až dost rendererů adoptuje“; v0.8 legacy. Ověřeno 2026-10-20.
- Python SDK: `a2ui-core` 0.4.0, `a2ui-agent-sdk` 0.9.0, nově oddělené `a2ui-adk` 0.1.0 a `a2ui-a2a` 0.1.0
  (vše 2026-10-17); **každý release od 2026-09-28 označen jako breaking** (cca 14denní kadence).
- Renderery (10/2026): React, Lit, Angular, Flutter GenUI = stable pro v0.8 a v0.9.1, **v1.0 u všech
  „Planned“**; SwiftUI jen planned, Jetpack Compose alpha (v0.9). Komunitní: json-render (Vercel), Lynx,
  AGenUI, a2ui-react-native (v0.8). Zdroj: docs/public/reference/renderers.md v repu.

## Klíčové koncepty
- Agent emituje **deklarativní JSON zprávy** omezené schématem.
- Renderer je validuje a vykresluje proti **předem schválenému katalogu komponent**.
- Pouze protokol – nezavádí vlastní renderovací framework; renderery existují pro web, mobil i desktop.
- Formát je navržen pro aktualizovatelné UI (surfaces, datový model).

## Místo v architektuře
Payload/formát UI. Nese se přes A2A (vzdálený agent → hostitelský agent) nebo přes AG-UI (agent → frontend).
Hostitelský agent může A2UI zprávy propustit beze změny, nebo je upravit.

## Změny v0.9 → v1.0 (breaking)
Zdroj: `specification/v1_0/docs/evolution_guide.md` v repu (ověřeno 2026-10-20).
- `theme` a `primaryColor` odstraněny (layout vs. branding odděleno).
- `callFunction` → obousměrné `callRendererFunction` / `rendererFunctionResponse` a `callAgentFunction` /
  `agentFunctionResponse`; runtime autorizace `allowedCallers` (`rendererOnly | agentOnly | rendererOrAgent`),
  chyba `INVALID_FUNCTION_CALL`.
- Multi-catalog: `supportedCatalogIds`, `inlineCatalogs`, explicitní `catalogId`; `protocolVersion` povinný
  v katalogu; `instructions` nahrazuje `rules.txt`.
- Prefix `@` rezervován (`@path`, `@call`, `@index`); `updateDataModel` vyžaduje `value` (null = smazání);
  `validationRegexp` → `checks`; `openUrl` vyžaduje user activation; terminologie client/server →
  renderer/agent; MIME `application/a2ui+json`.
- Katalogy z v0.9 v1.0 runtime nefungují bez přepsání.

## Vztah k MCP Apps
Oficiální dokument: Google Developers Blog „A2UI + MCP Apps“ (2026-06-17), spoluautoři tvůrci MCP Apps
(Ido Salomon, Liad Yosef). Tři vzory:
1. *A2UI over MCP* – A2UI payload jako výstup MCP resource/tool (`application/a2ui+json`).
2. *MCP Apps in A2UI* – MCP App jako komponenta A2UI surface (double-iframe, sandbox bez `allow-same-origin`).
3. *A2UI in MCP Apps* – A2UI renderer bundlovaný do iframe pro hostitele bez nativní podpory.
Doporučení Googlu: nativní rendering jako default, iframe jen pro komplexní UI na míru. Google zvažuje
MCP extension pro A2UI. Zdroje: https://developers.googleblog.com/en/a2ui-and-mcp-apps/,
https://a2ui.org/guides/mcp-apps-in-a2ui/, https://a2ui.org/guides/a2ui-in-mcp-apps/.

## Architektonické důsledky (Pozn. Adam)
- Bezpečnost: žádné libovolné HTML/JS od agenta → menší útočná plocha.
- Katalog komponent je governance artefakt (design system pro agenty); v1.0 navíc nese autorizaci
  (`allowedCallers`) – kdo smí volat které funkce.
- **Nestavět produkci na v1.0 RC** (SDK breaking každé 2 týdny, renderery v1.0 jen plánované). v0.9.1 ano,
  ale s plánem na přepis katalogů při migraci (theme pryč, `allowedCallers`, `catalogId`).
- Vendor/governance riziko: fakticky Google bez nadace, přesun repa bez vysvětlení → zapouzdřit za adaptér.

## Otevřené otázky
- [x] Rozdíly v0.9 → v1.0. → viz sekce výše (2026-10-20).
- [x] Vztah k MCP Apps – kdy které. → tři oficiální vzory, viz výše (2026-10-20).
- [x] Open-JSON-UI jako alternativa. → 2026-10-20: žádný první-party zdroj OpenAI (repo 404), jen CopilotKit
      docs; stránka CopilotKitu k němu dnes vrací obsah o A2UI. Neuvažovat.
- [ ] Kdy v1.0 přestane být RC a kdy ji podpoří renderery.
- [ ] Proč a kdy přesun do `a2ui-project` a jaká governance za tím je (nadace? jen rebrand?).

## Changelog
- 2026-09-23: první verze.
- 2026-10-20: přesun repa, v1.0 stále RC, změny v0.9 → v1.0, stav rendererů a SDK, vztah k MCP Apps,
  Open-JSON-UI vyřazeno.
