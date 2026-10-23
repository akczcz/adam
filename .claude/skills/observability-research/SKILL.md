---
name: observability-research
description: Postup pro průzkum a prověrku vrstvy observability a evaluace multiagentní platformy (OpenTelemetry a GenAI semantic conventions, OTEL Collector, Jaeger, Grafana Tempo/Loki/Mimir, Prometheus, ClickHouse, Langfuse, Arize Phoenix, OpenLLMetry, Opik, MLflow, SigNoz, Inspect AI, promptfoo, DeepEval, Ragas) a pro aktualizaci knowledge/observability/. Použij vždy, když Adam řeší tracing agentů, propagaci trace_id, metriky tokenů a nákladů, logování promptů, alerty, evaluaci agentů a trajektorií, LLM-as-judge, regresní testy promptů a agentů v CI, kvalitu výstupů, drift, nebo evidenci přesnosti pro AI Act – i když slovo "observabilita" výslovně nezazní.
---

# Průzkum observability a evaluace

## 1. Vyjdi ze znalostní báze
- Přečti `knowledge/observability/overview.md` a `kriteria.md`; u dotčených kandidátů jejich soubor.
- Přečti rozhodnutí v `knowledge/platforma/cilova-architektura.md` (Claude Agent SDK, Dapr Agents, agentgateway,
  Keycloak/SPIRE/OPA) a výsledky harnessů: `tools/harness_gateway_g1/` (propagace `traceparent` přes gateway),
  `tools/harness_identity_i2/` (audit log gateway, OPA decision log). Observabilita musí **navázat** na to, co
  tyhle komponenty už emitují, ne budovat paralelní instrumentaci.
- Přečti `knowledge/identity/regulace.md` T2–T4 (logging, retence) – observabilita je nosič auditu.

## 2. Rozliš tři otázky
O1 co se stalo (tracing, logy) · O2 dělá to práci dobře (evaluace) · O3 kdy zasáhnout (metriky, alerty).
Nástroj, který tvrdí, že řeší všechny tři, je buď platforma s lock-inem na instrumentaci, nebo marketing.

## 3. Licence a governance jako u frameworků
Postup `framework-research` sekce 2, vzorce v `knowledge/frameworks/licencni-vzorce.md`. Pro tuhle vrstvu navíc:
- **Elastic License 2.0 je tu častá** (Arize Phoenix) a `ee/` adresáře (Langfuse, SigNoz) – zapiš doslovně, co je za hranicí
  (SSO, RBAC, retence, alerty, multi-tenancy, eval funkce).
- Rozliš **SDK** (bývá MIT/Apache) a **backend** (bývá hostovaný nebo za licencí): Logfire, LangSmith, Braintrust.
- Ověř telemetrii nástroje samotného (phone-home) – observabilita, která volá domů, je ironie, ne vlastnost.

## 4. Standard ověřuj z primárních zdrojů
- OTEL GenAI semantic conventions: repo `open-telemetry/semantic-conventions`, stav každé části (spans, metrics, events,
  agent spans) – experimental vs. stable, verze semconv, datum.
- Co emitují zvolené komponenty: Claude Code / Agent SDK (`CLAUDE_CODE_ENABLE_TELEMETRY`, OTEL env, hooky),
  Dapr (W3C trace context, Zipkin/OTLP), agentgateway (`config.tracing`, `gen_ai` vs. OpenInference semconv),
  MCP SDK. Kde se `traceparent` **přeruší** – to je nález, ne detail.
- OpenInference (Arize) vs. OTEL GenAI: překryv, převod, kdo co implementuje.

## 5. Evaluaci posuzuj na trajektorii
- Umí nástroj hodnotit **trajektorii agenta** (nástroje, pořadí, argumenty, kroky, cena), nebo jen input → output?
- Lze z provozního trace udělat eval případ bez přepisování? Lze HITL rozhodnutí použít jako label?
- LLM-as-judge: lze nastavit `base_url` na naši gateway a pinnout model; jak se kalibruje proti lidem.
- CI: CLI s exit code a prahy – quality gate pro ADLC.

## 6. Analyzuj architektonicky
- Tok dat: SDK/hooky → OTLP → Collector (processors: masking, routing per tenant) → backend; evaly nad stejnými daty.
- Kde je instrumentace zadarmo (gateway, Dapr) a kde ji musíme psát (Agent SDK hooky).
- Cena odchodu: OTLP a JSONL datasety = přenositelné; vendor SDK = ne.

## 7. Výstup
- Česky, závěr první, fakta se zdrojem a datem, doporučení jako doporučení.
- Návrh úprav `knowledge/observability/` jako diff; rozhodnutí do `knowledge/platforma/cilova-architektura.md`.
- Soubory měň až po Adamově souhlasu.

## 7b. Pasti z kola 1 (2026-10-23)
- GenAI semconv jsou v repu `semantic-conventions-genai`, vše Development, bez release – verze cituj commitem.
- `genainormalizerprocessor` v Collector contrib převádí OpenInference/OpenLLMetry → GenAI; vendor backend kvůli konvenci není potřeba.
- Claude Code přes vlastní `ANTHROPIC_BASE_URL` neposílá `traceparent` bez `CLAUDE_CODE_PROPAGATE_TRACEPARENT=1`;
  traces CLI jsou beta za `CLAUDE_CODE_ENHANCED_TELEMETRY_BETA=1`. Dapr `samplingRate` default 0.0001.
- U LLM platforem čti stránku telemetry pro **EE režim** (Langfuse EE nelze vypnout) a hledej „authentication available on Enterprise“ (Opik).
- Judge, který vidí jen jednu observaci (Langfuse), trajektorii nehodnotí; red-team pluginy `REMOTE_ONLY` (promptfoo) v air-gapu nejsou.
- Měř harnessem: G1 `HARNESS_TRACE=1` ověřil propagaci CLI → gateway; O1 end-to-end a O2 zbývají.

## 8. Čemu se vyhni
- Nehodnoť podle dashboardu hostované verze ani podle počtu integrací.
- Neber veřejné benchmarky jako evaluaci platformy.
- Netvrď stav semconv z paměti – mění se po měsících.
