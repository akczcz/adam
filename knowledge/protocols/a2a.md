---
tema: Agent2Agent Protocol (A2A)
naposledy_overeno: 2026-09-23
zralost: stable (v1.0), adopce v počátcích
primarni_zdroje:
  - https://a2a-protocol.org/latest/specification/
  - https://a2a-protocol.org/latest/whats-new-v1/
  - https://a2a-protocol.org/latest/roadmap/
---

# A2A – Agent2Agent Protocol

## Účel
Otevřený standard pro to, jak se autonomní agenti navzájem objevují, delegují si úkoly
a spolupracují napříč frameworky, dodavateli a organizacemi.

## Aktuální stav
- **v1.0** – první stabilní, produkčně připravená verze (RC v březnu 2026).
- Původ: Google (duben 2025), následně předáno Linux Foundation.
- Governance: technický steering committee (8 velkých firem); Growth Stage projekt v Agentic AI Foundation (AAIF).
- SDK: Python, Go, JavaScript, Java, .NET. Existují kompatibilní vrstvy pro fallback v1.0 → v0.3.
- Nástroje: A2A Inspector, A2A Protocol TCK (conformance testy).

## Klíčové koncepty
- **Agent Card** – JSON dokument, kterým se agent popisuje (schopnosti, typy úkolů, vstupní formáty, autentizace, endpointy). Ve v1.0 podpora podpisu karty.
- **Task** – jednotka delegované práce se stavem a streamovanými událostmi.
- **Opacity** – agenti nesdílejí vnitřní paměť, nástroje ani logiku.
- Transportní vazby: JSON-RPC, gRPC, REST.
- Extensions s víceúrovňovým procesem povýšení (jádro zůstává stabilní).

## Novinky v1.0
- Formální opora v RFC 9457 (chyby), RFC 8785 (kanonický JSON), RFC 7515 (JWS).
- Sjednocení typů Part, refaktoring Agent Card, zjednodušené ID a HTTP cesty.
- Multi-tenancy, řízení execution mode, vyjednávání verzí.

## Místo v architektuře
Vrstva agent ↔ agent. Typicky: klientský agent deleguje přes A2A, vzdálený agent používá MCP pro své nástroje.

## Architektonické důsledky (Pozn. Adam)
- Agent Card registry = klíčová komponenta platformy (discovery, důvěra, podpisy).
- V mixovaném prostředí počítat s v0.3 i v1.0 → verzování a kompatibilita v gateway.
- Adopce v produkci je zatím raná → A2A zapouzdřit, nepropisovat přímo do doménové logiky.

## Otevřené otázky
- [ ] Autentizace a autorizace mezi agenty v rámci organizace vs. napříč organizacemi.
- [ ] Observabilita a tracing delegovaných úkolů.
- [ ] Jak A2A kombinovat s MCP Tasks pro dlouhotrvající práci (překryv?).

## Changelog
- 2026-09-23: první verze.
