# GUI nad celou firmou (P3-1)

Vlastní frontend platformy: klient **AG-UI 1.0** (`@ag-ui/core` jen typy, SSE parser vlastní), React + Vite + TypeScript. Backend =
AG-UI server v aplikaci zakázky (`tools/harness_p0_o2/agui.py`), který ho také servíruje na `/gui` (build ve stage `gui` v
`infra/images/app/Dockerfile.aks`).

| Pohled | Co ukazuje | Akce (AG-UI) |
|---|---|---|
| Přihlášení | člověk z Keycloaku (realm role `human`, tenant z claimu) | `POST /agui/login` (server → password grant) |
| Zakázky | thready tenanta: stav, bod HITL, role, rozpočet/útrata | `GET /agui/threads`; nová zakázka = první zpráva uživatele v `POST /agui/run` |
| Zakázka | subagenti (role), zprávy s disclosure čl. 50, aktivity (gate, pod, nástroje, předání, PDP/executor), stav, log událostí | run = SSE; HITL = interrupt → `resume` s povinným důvodem (≥ 10 znaků); stop = `forwardedProps.action=stop` s důvodem |

```bash
npm ci && npm run build                 # dist/ (tsc --noEmit + vite build)
npm run dev                             # http://localhost:5173/gui/ s proxy na AG-UI server na :8010
python ../tools/harness_p1_k8s/gui_fixture.py --gui dist   # lokální AG-UI server bez clusteru (dev účty adam/adam acme, bea/bea beta)
PW_CHROMIUM=/opt/pw-browsers/chromium python ../tools/harness_p1_k8s/gui_checks.py   # U-1 scénář Playwrightem proti fixture
```

Prvky mají `data-testid` (harness U-1 je drží jako kontrakt). Bez i18n, bez mobilu, A2UI renderer zatím není (formuláře jsou vlastní;
A2UI za adaptérem = P3-3/P3-4, viz `knowledge/platforma/p3-zakaznik.md`).
