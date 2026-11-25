---
oblast: platforma
téma: redesign GUI (řídicí pult firmy) – předávací brief pro samostatnou session
stav: realizace (2026-11-24) – varianta A Nebula, kód ve větvi redesignu, ostré měření čeká
zdroje: gui/src/*, tools/harness_p0_o2/agui.py, tools/harness_p1_k8s/{harness.py,gui_fixture.py}, knowledge/organization/eval-scenare.md
---

# Redesign GUI – brief

## Závěr

GUI (`gui/`, Vite + React, vlastní AG-UI klient) je funkčně kompletní a ověřené pěti eval scénáři, ale vizuálně technické
(39 řádků CSS, jeden světlý motiv, inline styly). Adam chce **reprezentativní „cosmic“ design, tmavý mód výchozí + světlý,
a GUI bez překreslovacích chyb** – a chce **vidět grafický návrh před implementací**. Tenhle soubor je vše, co nová session
potřebuje vědět a co v repu není vidět: požadavky, inventář obrazovek, datový tok a jeho křehká místa, závislosti harnessu
na GUI, nasazení a definice hotového.

## Požadavky Adama (2026-11-24, doslova a výklad)

| Požadavek | Výklad pro návrh |
|---|---|
| „ne čistě technický, hezký, použitelný, fancy, reprezentativní, cosmic design“ | tmavý vesmírný základ (hluboké modročerné plochy, jemné gradienty/záře, akcent 1–2 barvy), typografie s hierarchií, karty s hloubkou; ne hračka – je to řídicí pult firmy pro zadavatele, právníka, operátora |
| „světlý i tmavý mód, default dark“ | design tokeny v CSS proměnných, `prefers-color-scheme` + přepínač v hlavičce, volba v `localStorage`; **výchozí dark i bez preference** |
| „bez banálních chyb, kde se něco překresluje, nedokresluje“ | příčiny jsou v datovém toku (níže), ne v CSS – řešit stavovým modelem, ne záplatami |
| „grafický náhled před implementací“ | 2–3 varianty jako HTML náhled (Artifact, skill `artifact-design`), dark + light, na skutečných obrazovkách a datech; Adam vybere |
| „po zvolení designu napoprvé bez spousty bugů“ | implementace až po výběru; důkaz screenshoty všech obrazovek v obou módech + `tsc` + ostré měření před PR |

Jazyk GUI zůstává **česky**, technické termíny anglicky (AG-UI, run, thread, tenant).

## Doporučený postup

1. **Návrh (bez kódu v `gui/`)**: 2–3 varianty HTML náhledu se stejnými obrazovkami: přihlášení, seznam zakázek + nová zakázka,
   karta zakázky s běžícím streamem, karta zakázky s otevřeným interruptem (H2 a `rozpocet`), Firma, FinOps. Každá varianta dark + light,
   desktop i šířka telefonu. Použít skutečné texty a stavy z tohoto briefu, ne lorem ipsum.
2. **Výběr** – Adam vybere nebo zkombinuje; zapsat rozhodnutí sem (sekce „Rozhodnutí“).
3. **Design systém**: `gui/src/styles/tokens.css` (barvy, plochy, typografie, rozestupy, poloměry, stíny, stavy), `theme.ts`
   (přepínač, persist), komponentová vrstva (Card, Badge, Button, Table, Field, Timeline, InterruptCard, RoleChip, Skeleton, Toast).
   Žádné inline `style={{…}}` pro vzhled, žádné ad hoc barvy.
4. **Stavový model** (viz „Datový tok“): reducer nad AG-UI eventy + odvozené selektory; stávající `useState` sady nahradit.
5. **Harness**: zachovat všechny `data-testid` (níže), přidat testid tam, kde harness dnes sahá na `.err`/`td`; upravit harness ve stejném PR.
6. **Důkaz**: Playwright screenshoty (dark/light × desktop/mobil × všechny obrazovky) z `vite build` + mock dat; `npm run build`
   (`tsc --noEmit` je součást); `images` → `live-sync` → `measure e2e=p4-11` ≥ 101 PASS / 0 FAIL; pak PR.

## Inventář současného GUI

**Stack**: Vite 5.4, React 18.3, TypeScript 5.6, `@ag-ui/core` 1.0.3; žádný CSS framework ani router (hash routing `#/`, `#/t/<id>`,
`#/firma|registr|finops|governance|audit`). Soubory: `App.tsx` (35 kB: Login, Threads, Thread, KlasForm), `Firma.tsx` (17 kB: Nav,
FirmaPage, WfVersions, RegistrPage, FinopsPage, GovernancePage, AuditPage, Table), `api.ts` (token, login/refresh, AG-UI run přes SSE,
gov API), `styles.css` (39 řádků), `main.tsx`, `index.html` (`<title>Platforma – řídicí pult firmy</title>`, `lang="cs"`).

**Obrazovky a prvky**

| Obrazovka | Prvky | Poznámky |
|---|---|---|
| Přihlášení | karta, uživatel/heslo, chyba, `idle-notice` (odhlášení po nečinnosti) | před ním ještě Cloudflare Access (OTP) – mimo GUI |
| Hlavička | název, tenant, jméno, odhlášení, `Nav` (6 položek) | sem patří přepínač motivu |
| Zakázky (`#/`) | karta **Nová zakázka** (id, poptávka, rozpočet, flag Ostrý běh, klasifikační otázky K1–K4 `KlasForm`), karta **Zakázky** (tabulka: id, badge `live`, tenant, stav, bod, mandát, útrata, start; `refresh`) | stav zakázky = badge; řádky `thread-row-<id>` |
| Karta zakázky (`#/t/<id>`) | hlavička (id, AG-UI verze, run id, stav běhu, Stop/Resume s povinným důvodem ≥ 10 znaků), **stav** (`state-*`: status, stav, bod, profil, SLA, rozpočet/útrata, mandát, verze orchestrátoru, live), **role** (`role-box`, `subagents`, mandát per role), **časová osa** (`timeline`: zprávy rolí s `disclosure`, aktivity `act-<typ>`, HITL, stop), **karta interruptu** (`interrupt`, varianty podle bodu), **log událostí** (`event-log`, řádky s `data-event-type`), `mandat-card`, `stalled-notice`, `run-error` | nejsložitější obrazovka; interrupt dnes jeden – server při pauze/obnově vystaví týž bod znovu |
| Interrupt – varianty | `H1a`/`H1`/`H2`: schválit/odmítnout s důvodem (`approve-reason`, `reason-hint`, `reason-roles-hint`); `H4`: verdikt Reviewera + odkaz na PR (`h4-box`, `h4-verdict`); `H5`: potvrzení nasazení; `rozpocet`: útrata/strop/zdroj + nový strop (`budget-*`); `publikace`: chyba publikace (`publish-box`, `publish-error`); `role`: chyba role (`role-error`); `dialog:account`: otázky Accounta a odpověď (`dialog-*`); `klasifikace`: K-otázky (`klas-K<n>`, `klas-reason`) | text „bez rozhodnutí → Pozastaveno; pokračuje po Obnovit běh“ (nález 23) |
| Firma | tabulka role × tenant (verze, eval gate, autonomie), formulář posunu autonomie (`auto-*`), Tenanti se Stop/Resume tenanta (`tstop-*`, `tresume-submit`), verze orchestrátoru (`wf-*`) | admin pohled (platform-admin) |
| Registr agentů | instance rolí, události registru | tabulky |
| FinOps | tenanti, zakázky, per role, ledger z gateway (`finops-tenants`, `ledger-source`) | čísla v USD, 30d okno |
| Governance | report úplnosti T11–T15 (`report-*`), risk register, SLA bodů, export JSONL (`export-*`) | AI Act čl. 13 |
| Audit | rozhodnutí lidí (org.approvals) | tabulka |

**Stavy k vizuálnímu návrhu** (badge + barva + ikona): `RUNNING`, `SUSPENDED` (Pozastaveno – dnes bez vlastního stylu, kandidát
z eval), `COMPLETED`/`Dokonceno`, `FAILED`/`RoleFailed`/`BudgetExceeded`, `STALLED`, čekání na člověka (`waiting`, bod H1a…H5), `live`
(ostrý běh – důležitý, dnes červený badge; z eval kandidát „GUI varuje mock v hlavičce a u H4“), SLA překročeno.

## Datový tok a proč dnes „nedokresluje“

- Jeden **AG-UI run přes SSE** na otevřenou kartu (`runAgent` v `api.ts`); server (`agui.py` `/agui/run`) přehraje ledger zakázky
  jako eventy: `RUN_STARTED`, `STATE_SNAPSHOT`, `TEXT_MESSAGE_*`, `ACTIVITY_SNAPSHOT`, `SUBAGENT_*`, `RUN_FINISHED` (outcome
  `interrupt` | `cancelled` | výsledek), `RUN_ERROR`. Rozhodnutí člověka = nový run s `resume`; Stop/Resume = nový run s `forwardedProps.action`.
- `Thread` drží **šest nezávislých `useState`** (events, msgs, acts, subs, state, interrupt) a každý event je samostatný `setState`
  s `filter`/`map`. Při každém novém runu `reset()` všechno vymaže → **bliknutí prázdné karty** a při pomalém streamu „nedokreslené“
  mezistavy. Interrupt se bere **jen z posledního `RUN_FINISHED`**; mezi tím běží polling `threadState` každých 5 s (interrupt/stalled)
  a keepalive mandátu každých 30 s, které `state` přepisují – závod mezi snapshotem a pollingem (`setState(prev => running ? prev : s)`).
- Reconnect po síťové chybě (do 30×, 3 s) spouští celý run znovu včetně `reset()`.

**Návrh řešení** (závazné pro implementaci): jeden `reducer(threadView, event)` s normalizovanými entitami (messages, activities,
subagents podle id), odvozené selektory (timeline, otevřený interrupt = poslední `HITL_WAIT` bez pozdějšího rozhodnutí/timeoutu –
stejně jako `pending_interrupt` na serveru), **nový run nemaže pohled** – nahradí ho až první `STATE_SNAPSHOT`/`RUN_FINISHED`
(do té doby jemný indikátor „synchronizuji“), polling jen doplňuje pole, která stream nenese, klíčované seznamy se stabilními `key`,
žádný `index` jako key, skeletony místo „načítám…“. Chyby streamu jako toast, ne přepis obsahu.

## Závislosti harnessu na GUI (nesmí se rozbít)

Harness `tools/harness_p1_k8s/harness.py` (+ `gui_fixture.py`) ovládá GUI Playwrightem v kontrolách U1a–h, U2a–h, K1a–g, E3a–c,
E6/E13 (stalled, verze), N3a–c (přes Cloudflare), M1, R1–R3, L1c, V2c a dalších; screenshoty ukládá do `gui_shots/`.

- Všechny statické `data-testid` dnes v GUI (zachovat beze změny významu): `approve-reason approve-submit auto-level auto-reason
  auto-result auto-role auto-submit auto-tenant budget-box budget-limit budget-new budget-source budget-spent dialog-answer
  dialog-questions dialog-round dialog-submit disclosure event-log export-button export-lines export-preview finops-tenants h4-box
  h4-verdict idle-notice interrupt interrupt-bod interrupt-hash klas-reason klas-submit ledger-source login-error login-pass
  login-submit login-user logout mandat-card mandat-msg mandat-renew nav new-budget new-id new-live new-poptavka new-submit
  publish-box publish-error reason-hint reason-roles-hint refresh reject-submit report-gaps report-summary report-table
  resume-button resume-confirm resume-reason role-box role-error roles-table run-error run-id run-protocol run-status stalled-notice
  state state-bod state-budget state-live state-mandat state-profile state-sla state-spent state-status state-stav state-wf-version
  stop-button stop-confirm stop-reason subagents thread-live thread-mandat thread-stav thread-tenant threads-empty threads-table
  timeline tresume-submit tstop-reason tstop-result tstop-submit tstop-tenant user-name user-tenant wf-missing wf-stalled-count
  wf-summary wf-versions`.
- Dynamické: `thread-row-<id>`, `act-<typ>`, `msg-<id>`, `subagent-<id>`, `mandat-role-<role>`, `klas-K<n>`, `wf-version-<v>`,
  `nav-<stránka>`, `report-<x>` s atributem `data-missing`, `event-log [data-event-type]`.
- Křehké selektory v harnessu, které redesign má nahradit testid a harness upravit: `locator(".err")` (2×), `locator("td")` (2×).
- Texty, které harness čte z prvků (`inner_text`, porovnání s očekávaným řetězcem, např. „SLA překročeno: H1“, stav Pozastaveno,
  hodnoty badge): před změnou jakéhokoli popisku prohledat `grep -n 'inner_text\|text_content\|wait_for_selector' tools/harness_p1_k8s/harness.py`.

## Nasazení a ověření

- Build: `infra/images/app/Dockerfile.aks` stage `gui` (`npm ci`, `npm run build` = `tsc --noEmit && vite build`) → `/app/gui`,
  servíruje FastAPI `StaticFiles(html=True)` na `/gui` (`app.py`). Obraz staví workflow `images` z dané větve; do běžícího clusteru
  ho dostane `cluster` → `live-sync`; cluster startuje/zastavuje workflow `cluster` (`start`/`stop`), měření `measure`
  (`s1=false`, `e2e=p4-11`, `stop=true` = cluster se po měření zastaví sám). Adresa: `https://platform.autonomous.place/gui`
  (Cloudflare Access OTP → Keycloak). Cluster musí být mimo práci **zastavený** (soukromá karta).
- **Flux sleduje větev `claude/intelligent-hypatia-4d7uun`** (nastaveno Terraformem, vstup `gitops_branch` workflow `infra`). Nová
  session bude mít jinou větev: manifesty se z ní neaplikují, dokud se Flux nepřepne (`infra` → `apply` s `gitops_branch` = nová větev,
  nebo prázdné = `main` a testovat až po merge). GUI samo je v obrazu aplikace (stačí `images` + `live-sync` z nové větve), ale
  rozhodnout to na začátku session s Adamem.
- Lokální vývoj bez clusteru: `python tools/harness_p1_k8s/gui_fixture.py --port 8010 --gui gui/dist` = lokální AG-UI server bez Dapru
  a Keycloaku, který zakázku „přehrává“ do ledgeru (dev účty `adam/adam` tenant acme, `bea/bea` tenant beta); `cd gui && npm ci && npm run dev`
  proxuje `/agui` a `/zakazky` na `127.0.0.1:8010` (`vite.config.ts`). Screenshoty pro náhled i důkaz dělat nad touto fixture.

## Známé nálezy k GUI z eval scénářů (zapracovat do návrhu)

| Zdroj | Nález | Co má redesign udělat |
|---|---|---|
| scénář 1, nález 1 | zakázka bez flagu Ostrý běh běžela na mocku, poznalo se až z ledgeru | zřetelný režim v hlavičce karty (mock / ostrý) a u H4 |
| scénář 1, nález 5 | H4 bez verdiktu a odkazu na PR | karta H4: verdikt, odkaz na PR, seznam úkolů a kol review |
| scénář 3 (Z-11221144) | nevyřešený verdikt úkolu 3 skrytý za posledním `ok` | H4 ukazuje nevyřešené úkoly (`REVIEW_UNRESOLVED`) výrazně |
| scénář 4, nález 17 | chyběl Resume zakázky (přidán) | Stop/Resume jako jasná akce stavu, ne tlačítko v řádku hlavičky |
| scénář 5 | karta H1a jen hash poptávky, bez textu a důvodu K4; krátké stanovisko právníka bez obsahu | H1a ukáže poptávku a důvod klasifikace; nápověda, co má stanovisko obsahovat |
| scénář 5, nález 23 | timeout bodu = pauza; `SUSPENDED` bez vlastního stylu | stav Pozastaveno s vlastní barvou/ikonou a akcí Obnovit přímo na kartě |
| Adam | „něco se překresluje, nedokresluje“ | stavový model výše; žádný `reset()` pohledu při novém runu |

## Definice hotového

- [ ] Vybraná varianta zapsaná v sekci „Rozhodnutí“; tokeny a komponenty podle ní, dark výchozí, light přepínatelný a persistovaný.
- [ ] Všechny obrazovky z inventáře, včetně všech variant interruptu, v obou módech a na šířce telefonu bez horizontálního scrollu.
- [ ] Stavový model (reducer) místo šesti `useState`; nový run nemaže pohled; interrupt odvozený, ne jen z posledního eventu.
- [ ] Všechny `data-testid` zachované; `.err`/`td` selektory v harnessu nahrazené testid v tomtéž PR.
- [ ] Screenshoty (Playwright) všech obrazovek dark/light/mobil přiložené v PR (`gui/screenshots/` nebo artefakt workflow).
- [ ] `npm run build` čisté; `measure e2e=p4-11` ≥ 101 PASS / 0 FAIL; cluster po měření `Stopped`.
- [ ] Docs: `knowledge/platforma/produkt.md` (changelog), tento brief (Rozhodnutí + výsledek), README `gui/`.

## Rozhodnutí

- **2026-11-24 – varianta A „Nebula“** (Adam vybral z náhledu tří variant A Nebula / B Observatory / C Aurora; nic z B a C se nepřebírá).
  Paleta: hluboké indigo (`#090c1a`), skleněné karty, akcent fialová `#8b7cf6` + azurová `#38bdf8`, sémantika stavů ok/warn/err/info + `live`
  (magenta) pro ostrý běh a `susp` (azurová) pro Pozastaveno; světlý motiv `#eef0fb` se stejnými akcenty. Typografie: Inter (text),
  Space Grotesk (nadpisy, čísla), JetBrains Mono (id, hash, kód) – self-hosted přes `@fontsource-variable`, bez CDN. Poloměry 14/9 px,
  horní navigace s gradientním podtržením, kosmické pozadí (dvě záře + hvězdy) jen jako `::before/::after` stránky.
- **Flux zůstává na `claude/intelligent-hypatia-4d7uun`** (shodný commit s `main`): redesign nemění manifesty, GUI je v obrazu aplikace
  (`zakazka-app:p1`, `live-sync` = rollout restart), takže ostrý test = `images` + `live-sync` z větve redesignu.
- Stavový model: reducer `gui/src/threadView.ts` + hook `useThreadRun.ts` (viz `gui/README.md`); interrupt odvozený z aktivit, ne jen z posledního
  `RUN_FINISHED`; nový run pohled nemaže (generace), chyby streamu jako toast.
- Harness: `.err` → `[data-testid=page-error]`, buňky řádků zakázek `thread-<pole>` místo pořadí `td`, buňky verzí `wf-col-<pole>`; fixture simuluje
  bod `rozpocet` (strop ≤ 0,01 USD), skript `gui_screenshots.py` dělá důkazní screenshoty.

## Changelog

- 2026-11-25 (3. běh, run 45589022104): **97 PASS / 4 FAIL / 24 INFO / 1 SKIP**; N2c po opravě `threads_list` PASS. Čtyři FAILy jsou
  časování infrastruktury, všechny ve 2. běhu se stejným buildem GUI prošly: E13b (karta verzí ve Firmě se po restartu podu aplikace nenačetla
  do 60 s – požadavek přes tunel visel, žádná chyba v GUI), E13c (přihlášení přes tunel po dalším restartu podu nestihlo 30 s), N2a (přihlášení
  po odemknutí účtu vrátilo 502 z Cloudflare, origin se zrovna neozval), R3b (jeden `FINOPS_ERROR` při rotaci hesel od zakázky
  `P31-073538-o3b` z předchozího běhu – zombie zakázka, nález 18). Sjednocením tří běhů prošel každý ze 102 checků aspoň jednou; v jednom běhu
  zatím max. 100 PASS / 1 FAIL. Kandidáti pro harness: po restartu podu aplikace počkat na průchodnost tunelu před GUI kroky (E13b/E13c),
  `stop-zakazky` zombie zakázek z předchozího běhu před R-toky, `db()` s obnovou port-forwardu.
- 2026-11-25: ostré měření `measure e2e=p4-11` z větve redesignu, 2 běhy: (1) 64 PASS / 0 FAIL, pak pád harnessu v M1 – Azure spustil automatický
  upgrade image systémového uzlu, zanikl pod `pgfwd` a port-forward na Postgres (`db()` v harnessu obnovu nemá, `http` ano – kandidát); AKS se
  kvůli témuž upgradu nezastavil, zastaven ručně `cluster stop`. (2) **100 PASS / 1 FAIL / 24 INFO / 1 SKIP** – všechny GUI checky naostro
  prošly (U1, U2, K1, E3, E13, M1, N3a na `platform.autonomous.place`), jediný FAIL N2c byl v harnessu: nový `threads_list` četl 520 řádků
  seznamu po jednom dotazu Playwrightu na buňku (≈ 19 s na 600 řádků), GUI se mezitím odhlásilo po 20 s idle limitu měření → nahrazeno jedním
  `page.evaluate` (0,2 s). Brána Fluxu: harness přijme commit se shodným stromem `infra/k8s` (Flux zůstal na větvi
  `claude/intelligent-hypatia-4d7uun`); bez toho měření z jiné větve neprojde kontrolou P21a.
- 2026-11-24: varianta A Nebula vybrána a implementována (tokeny, motiv, komponenty, reducer karty zakázky, harness na testid, screenshoty v `gui/screenshots/`); lokálně `gui_checks.py` 17/17; ostré měření AKS čeká na start clusteru.
- 2026-11-24: brief založen (uzavření eval scénářů 1–5; GUI je další krok produktu). Realizace v samostatné session.
