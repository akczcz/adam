---
name: gateway-research
description: Postup pro průzkum, licenční prověrku a porovnání model gateway a FinOps vrstvy multiagentní platformy (LiteLLM, agentgateway, Envoy AI Gateway, Bifrost, Portkey Gateway, Kong AI Gateway, TensorZero, Higress a další) a pro aktualizaci knowledge/gateway/. Použij vždy, když Adam řeší přístup agentů k modelům, přepínání mezi Azure OpenAI, Bedrockem, Vertexem a vLLM, rozpočty a limity na agenta či tým, cenu provozu use casu, rate limiting, fallback mezi modely, průchod Anthropic Messages API a prompt cachingu přes proxy, nebo cost tracking – i když slovo "gateway" výslovně nezazní.
---

# Průzkum model gateway a FinOps

## 1. Vyjdi ze znalostní báze
- Přečti `knowledge/gateway/overview.md` a `kriteria.md`; u dotčených kandidátů jejich soubor.
- Přečti rozhodnutí v `knowledge/frameworks/overview.md` – agentní smyčka je **Claude Agent SDK**,
  trvalost **Dapr Agents**. Gateway musí sedět pod tuhle smyčku, ne obráceně.
- Zkontroluj `naposledy_overeno`. Gateway projekty mění licenční hranici OSS/enterprise
  často a tiše – cokoliv staršího než ~2 měsíce ber jako neověřené.

## 2. Licenci ověřuj u proxy, ne u SDK

Postup je stejný jako v `framework-research` (sekce 2) a vzorce v `knowledge/frameworks/licencni-vzorce.md`.
Pro gateway navíc:

1. **Rozliš SDK a proxy.** Klientská knihovna bývá MIT, server s klíči, rozpočty a admin UI
   mívá `enterprise/` adresář nebo funkce odemykané licenčním klíčem za běhu.
2. Najdi **seznam enterprise funkcí** v dokumentaci a zapiš doslovně, co z G2–G5 je za hranicí
   (typicky SSO, audit log, guardrails, RBAC, tagy pro útratu).
3. Ověř, jestli OSS build **kontroluje licenční klíč přes síť** nebo odesílá telemetrii – padá A3.
4. U projektů pod nadací (CNCF, Linux Foundation) ověř, že se governance vztahuje na **tenhle** repozitář.

## 3. Ověř protokolovou věrnost, ne marketing
„Podporuje Anthropic" znamená tři různé věci. Zjisti, kterou:

| Úroveň | Co to je | Pro Claude Agent SDK |
|---|---|---|
| Překlad | OpenAI formát → Anthropic na backendu | **Nestačí** – ztrácí cache_control, thinking, část tool use |
| Passthrough | `/v1/messages` proxy beze změny těla | Stačí, pokud zachová streaming a usage |
| Nativní | Gateway rozumí Anthropic formátu, umí na něm budgety, fallback, logging | Ideál |

Referenční kontrakt je [code.claude.com/docs/en/llm-gateway-protocol](https://code.claude.com/docs/en/llm-gateway-protocol):
forward `anthropic-beta` jako otevřený seznam, `cache_control` všude, `system` nepřeskládávat, `ping` nebufferovat,
chybová těla neobalovat. Pasti z kola 2 (2026-10-22): Bifrost blokuje `anthropic-beta` by default a slučuje
po sobě jdoucí tool zprávy; Portkey OSS má allowlist parametrů; LiteLLM při překladu na ne-Anthropic providera
`cache_control` zahodí.

Ověř v dokumentaci a changelogu, nikdy z blogů. Pokud to jde, ověř harnessem:
`ANTHROPIC_BASE_URL` na gateway, jeden turn s nástrojem a `cache_control`, porovnat `usage` s přímým voláním.
Weby dokumentace bývají z prostředí nedostupné – čti **zdrojové repozitáře docs** na GitHubu (stejný obsah
před renderem) a uváděj commit.

## 4. Prověř podle kritérií
`knowledge/gateway/kriteria.md`: nejdřív vyřazovací A1–A5, pak G1–G7.
U BUSL, ELv2 a SSPL nerozhoduj – **otázka na právníka**, zapiš doslovně omezení.

## 5. Analyzuj architektonicky
- Je to L7 proxy nebo aplikační server? Co to znamená pro latenci, škálování a bezpečnost?
- Kde leží klíče, rozpočty a útrata – a jak drahé je je vzít jinam?
- Pokrývá gateway i MCP/A2A? Je to plus, nebo rozmazání vrstvy do orchestrace?
- Cena odchodu: co zůstane funkční, když se gateway vymění za jinou? (Cíl: jen změna `base_url`.)

## 6. Výstup
- Odpověď Adamovi: česky, závěr první, fakta odděl od doporučení, u každého faktu zdroj a datum.
- Licenční zjištění vždy s odkazem na **primární** zdroj.
- Návrh úpravy souborů v `knowledge/gateway/` jako diff (konvence z `knowledge/README.md`,
  aktualizuj `naposledy_overeno` a Changelog).
- Když z prověrky plyne rozhodnutí pro platformu, navrhni řádek do
  `knowledge/platforma/cilova-architektura.md`.
- Soubory měň až po Adamově souhlasu.

## 7. Nový kandidát
Založ `knowledge/gateway/<nazev>.md` podle šablony z `knowledge/README.md`
a doplň řádek do tabulky síta v `overview.md`.

## 8. Čemu se vyhni
- Netvrď nic o licenci nebo o enterprise hranici z paměti. Vždy ověř.
- Nepočítej počet podporovaných poskytovatelů jako argument.
- Latenci gateway neopisuj z marketingu – buď změřeno harnessem, nebo „neměřeno".
