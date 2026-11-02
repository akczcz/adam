# Scénář promo videa (≤ 3 min, česky, tech publikum)

Zdroj pravdy je `scenes.py` (text komentáře čte TTS doslova). Tady čitelný přehled pro revizi.

| # | Scéna | Obraz | Komentář (zkráceno) | Komponenty |
|---|---|---|---|---|
| 1 | Intro | karta | autonomní firma, člověk jen u nevratných kroků; AKS, Git, Flux | AKS, Flux |
| 2 | Řídicí pult | GUI: přihlášení, seznam zakázek | AG-UI klient: thread, stream událostí, interrupt s důvodem | AG-UI |
| 3 | Založení zakázky | GUI: formulář, K1–K6, rozpočet | klasifikační brána AI Act před prvním agentem; rozpočet hlídá gateway | AI Act, agentgateway |
| 4 | Vrstva 2 | karta | Dapr Workflows durable + verzované; role = Claude Agent SDK v podu | Dapr, Claude Agent SDK, Postgres |
| 5 | Role Account běží | GUI: subagent running | Kata pod, sandbox-runtime, jediný egress přes gateway | Kata, sandbox-runtime |
| 6 | Vrstva 3 | karta | vše přes agentgateway, klíč per role × zakázka, Key Vault → ESO; neznámý model 404 | agentgateway, Key Vault, ESO, ClickHouse |
| 7 | H1 | GUI: interrupt, důvod, schválit | podepsaný token vázaný na hash artefaktu, executor; schvalovatel = mandát | executor, Keycloak |
| 8 | Vrstva 4 | karta | Keycloak + SPIRE SVID, jedna Rego v OPA, OpenBao | Keycloak, SPIRE, OPA, OpenBao |
| 9 | Návrh → PR → H4 | GUI: architekt, vývojář, PR, H4 | architekt navrhne, vývojář v sandboxu, PR; merge = člověk | sandbox, GitHub |
| 10 | Firma | GUI: verze orchestrátoru, stop tenanta, autonomie | named versioning, stop = limit 0 a pody do minuty, autonomie jen přes metriky | Dapr, gateway |
| 11 | FinOps | GUI: tenanti, zakázky, ledger | dva nezávislé zdroje: rozpočty gateway × ledger ClickHouse přes OTEL | ClickHouse, OTEL |
| 12 | Governance, Audit | GUI: report, risk register, audit | čl. 13 export per tenant, RLS v Postgresu | Postgres RLS, AI Act |
| 13 | Outro | karta | 82 kontrol proti AKS, open source stack, další krok ostrý běh | – |

Časování: komentář ~430 slov → ~2:50 při rate +4 %. `render.py` varuje nad 185 s.
