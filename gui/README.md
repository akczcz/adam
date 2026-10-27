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

```bash
npm ci && npm run build                 # dist/ (tsc --noEmit + vite build)
npm run dev                             # http://localhost:5173/gui/ s proxy na AG-UI server na :8010
python ../tools/harness_p1_k8s/gui_fixture.py --gui dist   # lokální AG-UI server bez clusteru (dev účty adam/adam acme, bea/bea beta)
PW_CHROMIUM=/opt/pw-browsers/chromium python ../tools/harness_p1_k8s/gui_checks.py   # U-1 scénář Playwrightem proti fixture
```

Prvky mají `data-testid` (harness U-1 je drží jako kontrakt). Bez i18n, bez mobilu, A2UI renderer zatím není (formuláře jsou vlastní;
A2UI za adaptérem = P3-3/P3-4, viz `knowledge/platforma/p3-zakaznik.md`).

## P3-4 (2026-10-27)
- Nová zakázka: dotazník klasifikační brány K1–K6 (`GET /agui/klasifikace`, checkboxy `new-k-K1..K6`) jde s poptávkou jako `forwardedProps.klasifikace`;
  zakázka založená bez něj (interní API) ukáže interrupt `reason=klasifikace` (formulář `klas-*`, resume `{answers, reason}`).
- Stav zakázky: profil rizika (`state-profile`) a „SLA překročeno“ (`state-sla`); při otevřeném interruptu GUI čte stav threadu každých 5 s
  (`GET /agui/threads/<id>`), protože run AG-UI končí interruptem. Aktivity `klasifikace`, `sla`, `channel` v průběhu; Governance: tabulka SLA.
