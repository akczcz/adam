# Harness O-1 – zakázka end-to-end jako Dapr Workflow s HITL body a executorem nevratných akcí

Změří organizační vrstvu v1 ([`knowledge/organization/procesy.md`](../../knowledge/organization/procesy.md),
[`autonomie.md`](../../knowledge/organization/autonomie.md)): tok P1→P5 s předáním artefaktů, HITL body jako
`when_any(wait_for_external_event, create_timer)`, **nevratné akce vykonává deterministická aktivita (executor)
s approval tokenem od člověka**, PDP = OPA (`policies/org.rego`), stop tlačítko, timeout, restart.

Vše lokálně **bez Dockeru**: Dapr 1.18.9 (`placement` + `scheduler` s embedded etcd + `daprd`) se **SQLite jako actor
state store**, OPA, FastAPI app s mock rolemi (aktivity bez modelu). Měří se proces, PDP/PEP a durable vrstva, ne agenti.

## Výsledek (2026-10-23)

| Check | Tvrzení | Výsledek |
|---|---|---|
| O1a | Dapr Workflow bez Dockeru: zakázka naplánována a dokončena, historie v SQLite | ✅ |
| O1b | P1→P5: 4 předání s artefaktem a hashem (zadání → ADR → PR → review), výstup Dokonceno s cenou | ✅ |
| O1c | **Injekce v zadání:** naivní Vývojář se pokusí o merge → PDP odmítne (`agent_role_cannot_execute_irreversible`); merge a deploy provedl jen executor, každý 1× | ✅ |
| O1d | Approval token vázaný na artefakt: H4 se špatným hashem → `HITL_INVALID_TOKEN` → Pozastaveno | ✅ |
| O1e | **Timeout HITL nikdy neschvaluje:** → Pozastaveno na H1, žádný EXECUTED | ✅ |
| O1f | **Stop:** pause → SUSPENDED; schválení během stopu neposune; resume agentem/bez důvodu 403; resume člověkem s důvodem → Dokonceno | ✅ |
| O1g | **Restart** daprd + app (SIGKILL) během čekání na H2: RUNNING po startu, schválení doručeno, Dokonceno, executor 1× | ✅ |
| O1h | Schválení agentem (`by_kind=agent`) → PDP `approval_not_by_human` → Zamitnuto; cena per zakázka v ledgeru | ✅ |
| O1i | Audit: každé PDP rozhodnutí s důvodem, OPA decision log, handoffy s hashi | ✅ |

Soubory: `results/o1-20261023-214002.json`, `results/ledger.json` (handoffy, PDP, EXECUTED, BUDGET, STOP/RESUME, NOTIFY).

## Co to říká o návrhu

- **„Agent navrhuje, workflow provádí“ funguje.** Role agenta nemá v Rego žádnou cestu k merge/deploy; i když injekce
  model přesvědčí, PDP ho zastaví a executor se spustí jen s tokenem vázaným na hash artefaktu, akci, zakázku a člověka.
- **HITL v Dapru je durable a fail-closed:** timeout vede do Pozastaveno, ne ke schválení; SIGKILL sidecaru i aplikace
  uprostřed čekání neztratí stav (SQLite) a schválení po restartu doběhne.
- **Stop tlačítko = `pause_workflow`**: schválení vyvolané během stopu se **neztratí, uplatní se po resume** – proto
  resume smí jen člověk s důvodem (a token je stále vázán na artefakt). To je vlastnost, kterou návrh musí znát (T5/T6).
- Cena per zakázka jde sečíst z ledgeru handoffů (v produkci z gateway klíče per zakázka).

## Zjednodušení oproti cílové architektuře

| Harness | Cíl |
|---|---|
| mock role = aktivity bez modelu | Claude Agent SDK přes Dapr Agents executor v sandboxu (S1) |
| HMAC podpis approval tokenu v app | OpenBao transit, ověření v OPA přes PEP |
| AG-UI nahrazeno HTTP voláním `/approve` | AG-UI dialog s disclosure (čl. 50) |
| cena z pevných částek per roli | gateway rozpočet per role × zakázka, `cost_usd_total` |
| SQLite state store, jeden proces | PostgreSQL v2 state store (rozhodnuto), K8s |
| `stopped` jen jako pause | + gateway klíč Block, sandbox tombstone, OPA data `stopped=true` |

## Spuštění

```bash
cd tools/harness_org_o1
uv venv -q -p 3.12 .venv && uv pip install -q -p .venv/bin/python "dapr==1.18.*" "dapr-ext-workflow==1.18.3" httpx pyyaml fastapi uvicorn
# binárky daprd, placement, scheduler z https://github.com/dapr/dapr/releases/download/v1.18.9/<bin>_linux_amd64.tar.gz
export DAPR_BIN_DIR=/cesta/k/dapr-binarkam OPA_BIN=/cesta/k/opa
.venv/bin/python harness.py
```

## Pasti

- Dapr Workflows bez Dockeru: stačí `placement`, `scheduler --etcd-data-dir` a `daprd --placement-host-address --scheduler-host-address`
  + komponenta `state.sqlite` s `actorStateStore: true`; `dapr init` (Redis v Dockeru) není potřeba.
- Python SDK: `dapr` 1.19 už nese `dapr.ext.*` uvnitř; s runtimem 1.18 pinnout `dapr==1.18.*` a `dapr-ext-workflow==1.18.3`
  (po downgrade core balíčku reinstalovat ext, jinak `No module named dapr.ext`).
- `when_any` vrací vítěznou task – porovnávat identitou (`winner == timer`), data z `event.get_result()`.
- `get_workflow_state().serialized_output` je `None`, dokud workflow neskončí – ošetřit.
- Event vyvolaný na SUSPENDED workflow se zařadí a zpracuje až po resume – stop nezahazuje schválení.
