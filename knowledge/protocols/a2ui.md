---
tema: A2UI (Agent-to-User Interface)
naposledy_overeno: 2026-09-23
zralost: preview (v0.9.x produkční, v1.0 RC)
primarni_zdroje:
  - https://github.com/google/A2UI
  - https://developers.googleblog.com/introducing-a2ui-an-open-project-for-agent-driven-interfaces/
---

# A2UI – Agent-to-User Interface

## Účel
Umožnit (i vzdálenému) agentovi dodat bohaté interaktivní UI bez posílání spustitelného kódu.
Agent popíše *co* zobrazit, klient rozhodne *jak* to vykreslit.

## Aktuální stav
- Iniciováno Googlem (open-source, prosinec 2025); CopilotKit jako launch/design partner.
- Aktuální produkční verze: **v0.9.1**; **v1.0** ve stavu release candidate; v0.8 legacy.

## Klíčové koncepty
- Agent emituje **deklarativní JSON zprávy** omezené schématem.
- Renderer je validuje a vykresluje proti **předem schválenému katalogu komponent**.
- Pouze protokol – nezavádí vlastní renderovací framework; renderery existují pro web, mobil i desktop.
- Formát je navržen pro aktualizovatelné UI (surfaces, datový model).

## Místo v architektuře
Payload/formát UI. Nese se přes A2A (vzdálený agent → hostitelský agent) nebo přes AG-UI (agent → frontend).
Hostitelský agent může A2UI zprávy propustit beze změny, nebo je upravit.

## Architektonické důsledky (Pozn. Adam)
- Bezpečnost: žádné libovolné HTML/JS od agenta → menší útočná plocha.
- Katalog komponent je governance artefakt (design system pro agenty).
- Před v1.0 počítat se změnami schématu.

## Otevřené otázky
- [ ] Rozdíly v0.9 → v1.0.
- [ ] Vztah k MCP Apps – kdy které.
- [ ] Open-JSON-UI jako alternativa.

## Changelog
- 2026-09-23: první verze.
