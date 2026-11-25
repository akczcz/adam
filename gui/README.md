# GUI nad celou firmou (P3-1)

Vlastní frontend platformy: klient **AG-UI 1.0** (`@ag-ui/core` jen typy, SSE parser vlastní), React + Vite + TypeScript. Backend =
AG-UI server v aplikaci zakázky (`tools/harness_p0_o2/agui.py`), který ho také servíruje na `/gui` (build ve stage `gui` v
`infra/images/app/Dockerfile.aks`).

| Pohled | Co ukazuje | Akce (AG-UI) |
|---|---|---|
| Přihlášení | člověk z Keycloaku (realm role `human`, tenant z claimu) | `POST /agui/login` (server → password grant) |
| Zakázky | thready tenanta: stav, bod HITL, role, rozpočet/útrata | `GET /agui/threads`; nová zakázka = první zpráva uživatele v `POST /agui/run` |
| Zakázka | subagenti (role), zprávy s disclosure čl. 50, aktivity (gate, pod, nástroje, předání, PDP/executor), stav, log událostí | run = SSE; HITL = interrupt → `resume` s povinným důvodem (≥ 10 znaků); dialog Account = interrupt `reason=dialog` → `resume {answer}`; stop = `forwardedProps.action=stop` s důvodem |
| Firma (P3-3) | role × tenant: verze, eval gate, úroveň autonomie; tenanti | `POST /agui/gov/autonomy` (nahoru jen při splněných podmínkách), `POST /agui/gov/tenant/<id>/stop|resume` |
| Registr agentů, FinOps, Governance, Audit (P3-3) | org.* přes Governance MCP (org_reader, RLS per tenant): agenti, události, útrata vs. strop (alert ≥ 80 %), governance report T11–T15, risk register, export JSONL, approvaly | `POST /agui/gov/tools/<name>`, `GET /agui/gov/export.jsonl` |
| FinOps – ledger | per zakázka a per tenant × zakázka × role z ClickHouse (spany gateway, P3-6 E4), delta vs. registr | Governance MCP nástroj `ledger` (`POST /agui/gov/tools/ledger`) |
| Registr agentů – `on_behalf_of` | sub schvalovatele, jehož jménem role běžela (token exchange v podu, P3-6 E2) | nástroj `agents` |

```bash
npm ci && npm run build                 # dist/ (tsc --noEmit + vite build)
npm run dev                             # http://localhost:5173/gui/ s proxy na AG-UI server na :8010
python ../tools/harness_p1_k8s/gui_fixture.py --gui dist   # lokální AG-UI server bez clusteru (dev účty adam/adam acme, bea/bea beta)
PW_CHROMIUM=/opt/pw-browsers/chromium python ../tools/harness_p1_k8s/gui_checks.py   # U-1 scénář Playwrightem proti fixture
```

Prvky mají `data-testid` (harness U-1 je drží jako kontrakt). Bez i18n, A2UI renderer zatím není (formuláře jsou vlastní;
A2UI za adaptérem = P3-3/P3-4, viz `knowledge/platforma/p3-zakaznik.md`).

## Redesign „Nebula“ (2026-11-24)

Zadání a rozhodnutí: `knowledge/platforma/gui-redesign-brief.md`. Tmavý „cosmic“ motiv je výchozí, světlý se přepíná v hlavičce
(`theme-toggle`; volba v `localStorage.gui_theme`, bez volby `prefers-color-scheme`, bez preference dark). Šířka telefonu bez horizontálního
scrollu (tabulky se skládají do karet řádků).

| Soubor | Role |
|---|---|
| `src/styles/tokens.css` | design tokeny (plochy, text, akcenty, sémantika stavů, záře, poloměry, písma) – dark na `:root`, light pod `html[data-theme="light"]`; písma self-hosted (`@fontsource-variable/*`), žádný externí CDN |
| `src/styles.css` | komponentové styly jen z tokenů; žádné inline `style` pro vzhled |
| `src/theme.ts` | motiv: uložená volba > systémová preference > dark; `index.html` ho nastaví před prvním vykreslením |
| `src/ui.tsx` | komponenty: Card, Badge (`statusTone`, `stavLabel`), Button, Field, Tile, Progress, RoleChip, DataTable (karty řádků na telefonu), Skeleton, Toast, ThemeToggle, PageError (`page-error`) |
| `src/threadView.ts` | **stavový model karty zakázky**: reducer nad AG-UI událostmi s entitami podle id (zprávy, aktivity, subagenti) a generací runu – nový run pohled nemaže, replay ledgeru entity jen nahradí, co run nepotvrdí do `RUN_FINISHED`, se odstraní; otevřený interrupt je odvozený z aktivit jako `pending_interrupt` na serveru (poslední *_WAIT bez pozdějšího rozhodnutí) a potvrzený detailem z `RUN_FINISHED`; po rozhodnutí člověka je optimisticky skrytý, dokud ho stream nevystaví znovu (pauza/obnova) |
| `src/useThreadRun.ts` | životní cyklus runu: start/retry bez resetu, polling při interruptu/STALLED jen doplňuje stav, keepalive mandátu, chyby streamu jako toast (+ `run-error` pro harness) |
| `src/App.tsx`, `src/Firma.tsx` | obrazovky; všechny `data-testid` z briefu zachované, navíc `thread-id/bod/roles/spent/started`, `wf-col-*`, `h1a-box`, `artifact-preview`, `h4-tasks`, `h4-unresolved`, `page-error` |

Z nálezů eval scénářů: režim **ostrý/mock** v hlavičce karty, **Pozastaveno** s vlastní barvou a tlačítkem *Obnovit běh* přímo na kartě,
H1a s poptávkou a důvodem klasifikace + nápovědou ke stanovisku, H2/H1 s náhledem artefaktu role, H4 s verdiktem, odkazem na PR a úkoly
(`REVIEW_UNRESOLVED` výrazně), `rozpocet` s útratou/stropem a novým stropem.

```bash
PW_CHROMIUM=/opt/pw-browsers/chromium python ../tools/harness_p1_k8s/gui_screenshots.py   # screenshoty všech obrazovek dark/light × desktop/telefon nad fixture → screenshots/
```

Fixture (`gui_fixture.py`) navíc simuluje bod `rozpocet`: zakázka se stropem ≤ 0,01 USD narazí před Vývojářem na `BUDGET_EXCEEDED`
(zdroj `agentgateway`), schválení s novým stropem → `BUDGET_RAISED`.

## P3-4 (2026-10-27)
- Nová zakázka: dotazník klasifikační brány K1–K6 (`GET /agui/klasifikace`, checkboxy `new-k-K1..K6`) jde s poptávkou jako `forwardedProps.klasifikace`;
  zakázka založená bez něj (interní API) ukáže interrupt `reason=klasifikace` (formulář `klas-*`, resume `{answers, reason}`).
- Stav zakázky: profil rizika (`state-profile`) a „SLA překročeno“ (`state-sla`); při otevřeném interruptu GUI čte stav threadu každých 5 s
  (`GET /agui/threads/<id>`), protože run AG-UI končí interruptem. Aktivity `klasifikace`, `sla`, `channel` v průběhu; Governance: tabulka SLA.
