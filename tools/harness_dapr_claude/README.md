# Harness: Claude Agent SDK nad Dapr Agents přes restart

Ověřuje cestu zvolenou rozhodnutím z 2026-10-21 (`knowledge/frameworks/overview.md`):
**smyčka = Claude Agent SDK, trvalost = Dapr Agents `ClaudeAgentExecutor` + `DaprSessionStore`.**
Cíl není porovnat frameworky, ale zjistit, co se stane, když proces umře uprostřed
čekání na člověka – a kolikrát se při tom spustí nástroj se side-effectem.

Testovaný objekt (`agent.py`) je záměrně kopie oficiálního příkladu
`examples/13-agent-executor-claude` z dapr-agents 1.0.9. Jediný přidaný prvek je
*ledger*: `transfer_money` zapisuje `start` a `end` do `results/ledger.jsonl`, takže
po restartu jde spočítat skutečná provedení.

## Tvrzení, která harness falsifikuje

| # | Tvrzení | Scénář | Kritérium |
|---|---|---|---|
| T1 | Druhý běh se stejným `session_id` si pamatuje první | `smoke` | odpověď zmiňuje Paříž |
| T2 | Čekající schválení přežije SIGKILL aplikace i sidecaru | `restart-while-waiting` | `GET /hitl/approvals` po restartu vrátí stejné `approval_request_id` |
| T3 | Po restartu lze schválit, běh doběhne, nástroj proběhl přesně jednou | `restart-while-waiting` | status `COMPLETED`, ledger `start=1 end=1` |
| T4 | Transcript po restartu drží celou historii | `restart-while-waiting` | follow-up si pamatuje Paříž i převod Alice |
| T5 | Restart uprostřed běhu schváleného nástroje: kolikrát se spustí? | `restart-during-tool` | měří se; `start≥2` = at-least-once, zapsat |
| T6 | Zamítnutí: nástroj neproběhne, Claude to neopakuje | `deny` | ledger prázdný, `COMPLETED` |
| T7 | Dlouhá pauza s restartem uprostřed (minuty až dny) | `long-pause` | jako T2–T4 s `--pause-seconds` |

T5 je informativní. Dapr Workflow aktivity jsou at-least-once a dapr-agents nic
jiného neslibují; harness jen změří, jak to vypadá v praxi a zda si Claude po
restartu vyžádá **nové** schválení (to by byl zajímavý nález sám o sobě).

## Prerekvizity

- Python 3.11 až 3.13 a `uv`
- Dapr CLI s `dapr init` (spustí Redis v Dockeru na `localhost:6379`)
- Docker Desktop běžící
- Claude přístup: `ANTHROPIC_API_KEY` v `.env`, nebo přihlášený Claude Code CLI
  (`claude` → `/login`); `claude-agent-sdk` nese vlastní CLI, Node.js netřeba
- Volné porty 8001 (app), 3500 a 50001 (sidecar)

Náklady: výchozí model `claude-haiku-4-5`, strop `0.50 USD` na běh. Celý
`--scenario all` je řádově desítky centů.

## Instalace

```bash
cd tools/harness_dapr_claude
uv venv
uv pip install -e .            # dapr-agents[claude]==1.0.9, ~100 MB kvůli bundlovanému CLI
cp .env.example .env           # doplň ANTHROPIC_API_KEY, nebo nech prázdné pro CLI login
```

## Spuštění

```bash
.venv/bin/python harness.py --scenario all
.venv/bin/python harness.py --scenario restart-while-waiting
.venv/bin/python harness.py --scenario restart-during-tool --slow-tool-seconds 30
.venv/bin/python harness.py --scenario long-pause --pause-seconds 3600
```

Harness sám spouští `dapr run -- python app.py`, čeká na health obou procesů,
volá HTTP rozhraní agenta a při restartu posílá **SIGKILL celé procesní skupině**
(aplikace i daprd naráz). Logy každé generace procesu jsou v `logs/app-genN.log`,
výsledky v `results/<scenario>-<timestamp>.json`, ledger v `results/ledger.jsonl`.

Vícedenní test: `--pause-seconds 1209600` (14 dní) s `APPROVAL_TIMEOUT_SECONDS`
v `.env` větším než pauza. Harness při tom jen spí; stroj musí vydržet, Redis
také. Smysl je ověřit, že reminder Scheduleru probudí workflow po dnech.

## Co harness hlásí navíc

- **Cesta rozhodnutí.** `POST /hitl/approvals/{id}/respond` po restartu může vrátit
  404 („this process was restarted“); harness pak použije přímo sidecar
  `raiseEvent` a zapíše, která cesta prošla. Pokud HTTP cesta po restartu
  nefunguje, je to nález pro návrh schvalovacího UI, ne chyba harnessu.
- **Redis důkaz.** Spočítá klíče `claude-session:*` a jejich velikost, aby bylo
  vidět, že transcript leží mimo proces (`keyPrefix: none` v komponentě).
- **Doba restartu** (kill → oba procesy zdravé).
- **Verze**: dapr-agents, claude-agent-sdk, Dapr CLI.

## Co zapsat do knowledge po běhu

Do `knowledge/frameworks/dapr-agents.md` k otevřené otázce s prioritou:

- verdikty T1–T7 s datem a verzemi,
- u T5 sémantiku (exactly-once / at-least-once / nové schválení),
- cestu rozhodnutí po restartu (HTTP vs. sidecar),
- dobu restartu a cokoli z `logs/`, co vypadá jako chyba obnovy.

## Limity

- `dapr run` na jednom stroji není Kubernetes pod: žádný scheduler, žádná síť
  mezi pody, Redis lokální. Pro věrnější test postav `kind` + `dapr init -k`,
  nasaď `app.py` jako Deployment a místo `kill()` dělej `kubectl delete pod`.
  Scénáře i kritéria zůstanou stejné, změní se jen třída `AgentProcess`.
- Claude Agent SDK pracuje s `cwd`; harness ho drží v tomto adresáři, aby
  `project_key` zůstal stejný napříč generacemi procesu. Na k8s musí být `cwd`
  stabilní cesta v image.
- Model je nedeterministický. Když Claude nezavolá `transfer_money`, harness
  to ohlásí jako vyvrácený schvalovací bod – spusť znovu, případně zpřísni
  instrukce v `agent.py`.
- Jeden běh = jedna Claude session (`--session-id` pro navázání). Mezi scénáři
  se session sdílí záměrně, protože T4 měří kontinuitu transcriptu.
