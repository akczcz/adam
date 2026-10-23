---
tema: Evaluace agentů – síto frameworků, metodika vrstev L0–L5 pro role virtuální firmy, metriky pro čl. 15 AI Act
naposledy_overeno: 2026-10-23
zralost: mixed (Inspect AI, promptfoo, MLflow stable; OTEL gen_ai.evaluation.result Development; ATIF v1.7)
primarni_zdroje:
  - https://github.com/UKGovernmentBEIS/inspect_ai
  - https://github.com/promptfoo/promptfoo
  - https://github.com/mlflow/mlflow
  - https://github.com/comet-ml/opik
  - https://github.com/confident-ai/deepeval
  - https://github.com/langfuse/langfuse/blob/main/LICENSE
  - https://github.com/Arize-ai/phoenix/blob/main/LICENSE
  - https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents
  - https://code.claude.com/docs/en/plugin-evals
  - https://github.com/google/adk-docs/blob/main/docs/evaluate/index.md
  - https://github.com/harbor-framework/harbor/blob/main/rfcs/0001-trajectory-format.md
---

# Evaluace agentů

**Metodická poznámka (2026-10-23):** licence z `LICENSE` v klonu (commit uveden) a registry metadat; weby OpenAI,
EUR-Lex a nist.gov nedostupné – fakta označená *sek.* stojí na výňatcích z vyhledávače.

## Závěr

- **Do kola 2:** **Inspect AI** (MIT, UK AISI, jediný kandidát bez telemetrie; trajektorie přes `TaskState`, sandboxy,
  approval/review policy), **promptfoo** (MIT; OTLP receiver + `trajectory:*` asserce nad GenAI spany, provider pro
  Claude Agent SDK, exit code 100 a prahy – ale **red-team pluginy pro agenty jsou `REMOTE_ONLY`**, volají cloud),
  **MLflow 3** (Apache-2.0, DCO, telemetrie opt-out; OTLP ingest, trace-based scorery, judge alignment proti lidem,
  `@mlflow.test` v pytestu), **Opik** (Apache-2.0 celá platforma; `TrajectoryAccuracy`, OTLP ingest; CLA, usage report
  default on), **DeepEval** (Apache-2.0; nejširší agentní metriky; PostHog default on, datasety z provozu jen přes Confident AI).
- **Podmíněně:** Langfuse (MIT + `ee/`, od 1/2026 **ClickHouse Inc.**; judge vidí **jen jednu observaci, ne děti** →
  trajektorie ne), Giskard v3 (Apache-2.0, přepis 10/2026, bezpečnostní generátory lokálně).
- **Vyřazeno:** Arize Phoenix (**Elastic-2.0 server i `arize-phoenix-evals`**), Braintrust a LangSmith (hostovaný backend;
  knihovny `autoevals`, `openevals`, `agentevals` MIT použitelné), OpenAI Evals (bez releasu od 5/2024), Ragas (stagnace,
  bez releasu od 2026-01-13).
- **„Evaly nad OTLP spany“ jako projekt neexistuje.** Existuje promptfoo OTLP receiver, backendy s OTLP ingestem,
  OTEL event `gen_ai.evaluation.result` (Development) a **ATIF** (Agent Trajectory Interchange Format, Harbor, Apache-2.0,
  `ATIF-v1.7`) jako jediný otevřený formát trajektorie s více implementacemi.

## Síto – kolo 1

| Kandidát | Licence | Governance / telemetrie | Trajektorie | Dataset z provozu | Judge přes gateway | CI | Bezpečnost | Výsledek |
|---|---|---|---|---|---|---|---|---|
| **Inspect AI** 0.3.283 | MIT (@a8f5015) | UK AISI + Meridian Labs; bez CLA/DCO; **bez telemetrie** | ✅ scorer nad `TaskState` (zprávy, tool calls, limity tokenů/času/ceny), approval/review policy, Scout scannery | ◐ JSON/JSONL/CSV; cizí trace = vlastní reader; `.eval` log vlastní formát | ✅ `ANTHROPIC_BASE_URL`, `--model-role grader`, panel graderů | ◐ `inspect eval`, bez prahů na skóre → gate přes `evals_df()` | ✅ approval policy, `human_reviewer`; `inspect_evals`: agentdojo, agentharm, ipi_coding_agent | **postupuje** |
| **promptfoo** 0.124.1 | MIT (@b678d24) | Promptfoo Inc.; PostHog **default on**; update check | ✅ `trajectory:tool-sequence/-args-match/-step-count`, `trace-span-*` nad OTLP | ✅ OTLP receiver, pull z Tempo | ✅ `apiBaseUrl`, `ANTHROPIC_BASE_URL`, pinned judge | ✅ exit code 100, `PROMPTFOO_PASS_RATE_THRESHOLD`, GitHub Action | ◐ lokálně jen `policy`, `intent`; **`REMOTE_ONLY`** 26 pluginů (indirect-prompt-injection, mcp, data-exfil, agentic…) | **postupuje s výhradou** (A3 pro red-team) |
| **DeepEval** 4.3.1 | Apache-2.0 (@7272037) | Confident AI; PostHog default on | ✅ TaskCompletion, ToolCorrectness, ArgumentCorrectness, PlanAdherence, StepEfficiency, AgentLoopDetection, ToolPermission (Py i TS) | ◐ OTEL exporter jen **do** Confident AI | ✅ `LOCAL_MODEL_BASE_URL`, gateway modely | ✅ `deepeval test run` nad pytestem | ◐ safety metriky; red-team = Confident AI | **postupuje** (bez Confident AI) |
| **MLflow** 3.17.2 | Apache-2.0 (@89da1ee) | **DCO**; telemetrie opt-out (auto off v CI) | ✅ `ToolCallCorrectness` (3 režimy), `ToolCallEfficiency`; custom scorer s `trace.search_spans()` | ✅ OTLP ingest `/v1/traces`; `search_traces` → evaluate; human `Assessment` | ✅ `gateway:/`, `anthropic:/`; **judge alignment** (MemAlign) proti lidským assessmentům | ✅ `@mlflow.test` + `evaluate()`, `result.passed` | ◐ `Safety` scorer | **postupuje** |
| **Opik** 2.2.117 | Apache-2.0 (@ec65c46) | Comet, **CLA**; usage report **default on** (`OPIK_USAGE_REPORT_ENABLED`) | ✅ `TrajectoryAccuracy`, AgentToolCorrectness, AgentTaskCompletion | ✅ OTLP ingest, anotační fronty → dataset, online rules | ✅ LiteLLM `base_url`; judge alignment | ◐ `pass_threshold`; exit code neověřen | ◐ heuristika injection, moderation | **postupuje** |
| **Langfuse** 4.68 | MIT + `ee/` (@c83198b, copyright ClickHouse Inc.) | **CLA**; PostHog default on, u EE klíče **nelze vypnout** | ◐ judge na observaci **nevidí děti** → trajektorie jen souhrn na root spanu | ✅ OTLP ingest, anotační fronty, agreement analytics | ✅ LLM connection s base URL | ✅ `experiment-action` | ❌ | observability backend, **ne eval engine** |
| **Giskard v3** 3.0.1 | Apache-2.0 (@6a2e58b) | PostHog opt-out; v3 = přepis 10/2026 | ◐ `giskard-agents` multi-turn simulace | ❌ | ✅ LiteLLM | ? | ✅ `giskard-scan`: prompt_injection, GCG, GOAT, crescendo – **lokálně** | sledovat (3 týdny stará verze) |
| OpenAI Evals | MIT | PyPI 2024-05-01; README → hostovaný dashboard | ❌ | ❌ | ❌ | ◐ | ❌ | **vyřazen** (A3) |
| Braintrust / `autoevals` | repo Apache-2.0 vs. PyPI MIT – rozpor | hostovaný backend | ✅ hosted | – | `OPENAI_BASE_URL` | – | – | **vyřazen** (A2/A3); `autoevals` jako knihovna |
| LangSmith / `openevals`, `agentevals` | SDK MIT | hostovaný backend; `agentevals` bez releasu od 2025-07 | ✅ trajectory match strict/unordered/subset/superset, LLM judge | hosted | ✅ | hosted | ❌ | **vyřazen**; knihovny použitelné |
| **Arize Phoenix** 20.25 | **Elastic-2.0** server i `arize-phoenix-evals` | Arize, CLA | ✅ tool_selection…, ATIF import | ✅ | ✅ | ◐ | ❌ | **vyřazen A1** |
| Ragas 0.4.3 | Apache-2.0 (bez SPDX classifieru) | poslední release 2026-01-13; telemetrie default on | ◐ jen multi-turn sample | ❌ | ✅ | ❌ | ❌ | **vyřazen** (stagnace) |
| **Anthropic `claude plugin eval`** | součást CLI | early access | ✅ gradery `tool_used`, `tool_order`, `llm`, `baseline`; 3 běhy, no-plugin baseline | ◐ JSONL transcript, mock MCP s `expect:` | ◐ `--judge-model` přes stejnou cestu jako Claude Code | ✅ `--threshold`, exit 1, `--json` | ◐ hooky jako enforcement | **vzor** pro evaly rolí Claude Agent SDK, ne platforma |
| AgentDojo / τ²-bench / SWE-bench | MIT | ETH / Sierra / Princeton | – | – | – | – | AgentDojo = injection + utility | referenční sady přes **`inspect_evals`** 0.25.0 (MIT) |

## Metodika: vrstvy evalů pro role virtuální firmy

Zdroje: Anthropic „Demystifying evals for AI agents“ (2026-01-09): grade výsledek, ne cestu; **pass^k** (75 % per trial ⇒
42 % pro 3 běhy); judge kalibrovaný proti expertům s možností „Unknown“, jeden judge na dimenzi; 20–50 úloh z reálných
selhání; capability vs. regression suite. Google ADK: `tool_trajectory_avg_score`, rubric-based trajectory quality,
`adk conformance test` = záznam/replay jako regresní baseline. AISI: approval + review policy, scannery nad transkripty
(pass/fail bez čtení logů maskuje zkratky). NIST AI 600-1 (*sek.*): red-teaming před i po nasazení, TEVV oddělené od vývoje.

| Vrstva | Co měří | Grader | Nástroj | Role |
|---|---|---|---|---|
| **L0 Unit nástrojů** | MCP nástroj vrací správně; mock `expect:` | kód | pytest + mock MCP (vzor `claude plugin eval`, Inspect sandbox) | všechny |
| **L1 Trajektorie** | správný nástroj, argumenty, pořadí **jen kde je kauzálně nutné** (`in_order`, ne `exact`), kroky, tokeny, cena, **žádný nesankcionovaný nástroj** | kód nad spany / ATIF | promptfoo `trajectory:*`, Inspect scorer nad `state.messages`, MLflow/Opik nad trace | vývojář, SRE |
| **L2 Výsledek úkolu** | stav prostředí: testy zelené, PR mergeable, incident uzavřen, ADR vyplněno | kód + rubrika | Inspect sandbox + bridge na Claude Code; **pass^k ≥ 3** | architekt (ADR rubrika), vývojář (SWE-bench styl), reviewer (shoda s lidským review = HITL label), SRE |
| **L3 Bezpečnost** | injection z ticketu / PR / README / MCP výstupu, exfiltrace tajemství, eskalace, obcházení approval | kód (nesankcionovaná akce = fail) + judge | `inspect_evals` agentdojo, ipi_coding_agent, agentharm; Petri; Giskard scan; **vlastní injection sada z našich kanálů** | všechny, prioritně SRE a reviewer |
| **L4 Provozní drift** | baseline vs. provoz: cost/úkol, kroky, HITL odmítnutí, online judge | online judge + metriky | MLflow/Opik/Langfuse online rules nad OTLP; alerty → Dapr stop | všechny |
| **L5 Kalibrace judge** | shoda judge ↔ člověk (HITL rozhodnutí jako label) | statistika | MLflow MemAlign, Opik alignment, Langfuse agreement | průřez |

### Metriky k evidenci pro čl. 15 AI Act (text *sek.*, shoda 3 zdrojů)

Odst. 1 přesnost, robustnost, kybernetická bezpečnost „po celý životní cyklus“; odst. 3 **metriky přesnosti deklarované
v návodu k použití**; odst. 4 odolnost vůči chybám a interakci s jinými systémy; odst. 5 odolnost vůči pokusům třetích
stran měnit výstupy. Evidovat per verze systému (T10 v [`../identity/regulace.md`](../identity/regulace.md)):

1. task success rate a **pass^k** per role a use case (odst. 3 – číslo do instructions of use),
2. **trajectory policy-compliance rate** = podíl běhů bez nesankcionované akce (odst. 5, AISI),
3. injection resistance rate nad L3 sadou (odst. 5),
4. judge–human agreement (důvěryhodnost metrik),
5. robustness: pass rate při degradovaných nástrojích / timeoutech (odst. 4),
6. drift: Δ provoz vs. baseline s datem a verzí modelu / promptu / policy.

Export: JSONL + `gen_ai.evaluation.result` eventy do trace, aby audit a eval sdílely `trace_id` (T2/T3).

## Co si platforma musí napsat sama

1. **Konvertor** Agent SDK transcript / `claude_code.*` spany / Dapr workflow události → **ATIF** nebo Inspect `Sample`
   („trace → eval případ jedním krokem“; HITL rozhodnutí z Dapr workflow jako label).
2. **Role-specifické gradery** (ADR rubrika, shoda s PR review, incident runbook) – rubriky jsou naše know-how.
3. **Gate v ADLC**: z Inspect `evals_df()` / promptfoo JSON spočítat pass^k, policy-compliance, judge agreement, zapsat
   per verze jako evidenci pro čl. 15.
4. Zápis výsledků zpět do trace jako `gen_ai.evaluation.result` (semconv Development – počítat se změnou názvů).
5. **Vlastní injection sada** z našich kanálů – promptfoo ji lokálně nenabídne, AgentDojo pokrývá jiné domény.

## Pozn. Adam (názor z rešerše, k rozhodnutí)
Jádro evaluace **Inspect AI** (offline evaly rolí, sandbox, approval policy jako „nesankcionovaná akce = terminate“,
`inspect_evals` pro L3, Scout scannery); **promptfoo** jako CI gate a OTLP most (trajektorové asserce, exit code; red-team
jen lokální pluginy); pro L4/L5 **MLflow 3** (Apache, DCO, telemetrie opt-out, trace scorery, alignment) – Opik je
funkčně bohatší, ale CLA + usage report default on; Langfuse jen jako observability backend O1, ne eval engine.
Inspect má nejnižší governance riziko (vláda + nonprofit, bez CLA); komerční ekosystém kolem něj (Meridian) sledovat.

## Co ověřit dál
- [ ] DeepEval `AnthropicModel` a `ANTHROPIC_BASE_URL`; Opik exit code při `pass_threshold`; Langfuse code evaluators nad celým trace.
- [ ] Text čl. 15 z EUR-Lex; NIST AI 600-1 Measure.
- [ ] ATIF kanonický repozitář (`harbor-ai/agent-trajectory-format` nedostupný; spec z Harbor RFC 0001).
- [ ] Braintrust rozpor licence repo (Apache) vs. PyPI (MIT).
- [ ] **Harness O2:** Inspect AI + Claude Agent SDK přes agentgateway: jeden task s mock MCP, scorer nad trajektorií,
      approval policy terminate při `delete_ticket`; promptfoo `trajectory:*` nad spany z G1 mocku.

## Changelog
- 2026-10-23: první verze z rešerše (síto kolo 1, metodika L0–L5, metriky čl. 15).
