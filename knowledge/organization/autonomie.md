---
tema: Hranice autonomie – katalog nevratných akcí, schvalovatelé, technické vynucení, timeouty a eskalace, stop tlačítko, klasifikační brána, pravidlo rozšiřování autonomie
naposledy_overeno: 2026-10-23
zralost: n/a (návrh v0 – kolo 1; harnessem O-1 neměřeno; AI Act fakta z regulace.md, zralost preview)
primarni_zdroje:
  - knowledge/organization/kriteria.md
  - knowledge/organization/procesy.md
  - knowledge/identity/regulace.md
  - knowledge/identity/overview.md
  - knowledge/observability/evaluace.md
  - knowledge/memory/model-pameti.md
  - knowledge/sandbox/overview.md
  - knowledge/frameworks/dapr-agents.md
  - knowledge/gateway/overview.md
---

# Hranice autonomie

**Pozn. Adam:** návrh. Zásada A1 (kriteria.md): hranice je v procesu (Dapr aktivita) a v PEP (OPA, gateway, paměť),
nikdy jen v promptu. Zásada v0 (overview.md): člověk na každém nevratném kroku a na vstupu/výstupu zakázky.

## Závěr

- Deset tříd nevratných akcí N1–N10. V v0 **žádná není „jen agent“**; schvaluje člověk v roli vlastníka procesu, u
  výstupu zakázky a u high-risk profilu i člověk zákazníka.
- Každá akce má **dva nezávislé PEP**: primární mimo proces agenta (gateway route, `extAuthz` → OPA, PEP paměti/RLS,
  Dapr HITL aktivita) a sekundární v procesu (hook `PreToolUse` Agent SDK s touž Rego; v evalech Inspect approval
  policy). Agent, který obejde hook, narazí na síť nebo data.
- Schválení je **vázané na hash artefaktu** a **expiruje**; timeout HITL nikdy neznamená souhlas (fail-closed).
- Stop tlačítko (T5, T6) = Dapr pause + checkpoint + tombstone sandboxu + zmrazený rozpočet + OPA `stopped`.
- Autonomie se rozšiřuje jen měřením (pravidlo pass^k níže) a změna sama je akce N6.

## Stupnice schvalovatelů

| Kód | Schvaluje | Kdy (v0) |
|---|---|---|
| A0 | jen agent (bez approval) | nic z N1–N10; jen vratné akce v sandboxu a na větvi úkolu |
| A1 | reviewer-agent (jiná role, jiný SVID, eval sandbox) | zatím žádná nevratná akce; cíl pravidla pass^k pro H4 u profilu `standard` |
| A2 | člověk – vlastník procesu | default pro N1–N10 |
| A3 | člověk zákazníka | H1, H6 (vstup/výstup zakázky – rozhodnuto), N2 u high-risk, N3 adresované zákazníkovi, N5 nad daty zákazníka |
| A4 | governance (člověk) | N6, N9, N7 scope platforma |

Dogfooding: A2 = A3 = A4 = Adam; OPA rozlišuje `approver_role`, aby log T3 nesl, v jaké roli schválil.

## Katalog nevratných akcí

| # | Akce | Proces | Schvaluje (v0) | Vynucení primární | Vynucení sekundární | Timeout / eskalace | Reverzibilní alternativa | Loguje se (T3) |
|---|---|---|---|---|---|---|---|---|
| **N1** | push do `main` / merge PR | P4 | A2 vlastník Vývoj (H4) | agentgateway: terminovaná git route, `git-receive-pack` na `main` → **403** bez `approval_id` v CEL/OPA kontextu (změřeno S1); branch protection v repu | hook `PreToolUse` (Bash `git push`, MCP `merge_pull_request`) → táž Rego; Inspect approval `*git-receive-pack*` = terminate | 1/2/5 prac. dnů; vázáno na head SHA | push na větev úkolu (vždy povolen); revert commit | approval_id, approver, reason, head SHA, PR URL, trace_id, policy_version, cena PR |
| **N2** | deploy do prostředí zákazníka | P5 (X1 rollback) | dev/staging u `standard`: A0 s automatickým rollbackem; produkce: A2 vlastník Nasazení (H5); high-risk: A2 + A3 (T13) | OPA `extAuthz` na route `deploy`/cloud API write (default deny); **token exchange v gateway** vydá krátkodobý credential (≤ 1 h) jen s `approval_id` (T13) | hook na MCP cloud write; Inspect approval | 1/2/5; approval expiruje 24 h nebo při změně manifestu (digest) | rollback podle runbooku (≤ 30 min); canary | approval, approver, manifest digest, verze modelu/promptu/policy (T10), výsledek ověření |
| **N3** | komunikace ven k lidem (e-mail, ticket, PR komentář v cizím repu, chat) | P1, P5, X1 | A2 vlastník Account (zadavatel), A3 u zpráv zákazníkovi; **PR komentáře v repu zakázky = A0 s povinným disclosure** | MCP servery pro e-mail/ticket za gateway `extAuthz` → OPA: `comm.external` jen s approval; **disclosure T7 vkládá adaptér kanálu, ne model** (čl. 50(1), platí od 2.8.2026 – regulace.md) | hook na nástroje `send_*`, `create_comment` mimo repo zakázky | 1 prac. den → vlastník; bez odpovědi se neposílá | koncept do fronty (AG-UI náhled); interní poznámka v issue | adresát, kanál, hash obsahu, disclosure přítomen (bool), approver |
| **N4** | platba / objednávka / nákup zdrojů (cloud SKU, licence, model spend nad rozpočet) | P1, P2, P5 | A2 + A4; v0 dogfooding: jen Adam | gateway rozpočet `Block` (USD) per klíč; cloud API write → OPA deny bez approval; žádný platební MCP v v0 | hook deny `payment.*` | 2 prac. dny → governance; bez schválení = ne | odhad a nabídka jako artefakt; navýšení rozpočtu = N6 | částka, účel, approver, zakázka |
| **N5** | smazání dat / výmaz (větev, tag, DB, bucket, tombstone v paměti, ClickHouse tenant) | X1, X2, P5 | A2 vlastník + A3 nad daty zákazníka; výmaz GDPR = A4 | OPA deny `data.delete` bez approval; gateway git route deny `delete` refs; PEP paměti: `tombstone` jen z HITL aktivity; ClickHouse DDL mimo dosah agentů | hook na `rm -rf` mimo RW vrstvu, MCP `delete_*`; Inspect approval `delete_*` (změřeno O2) | 2/5; u GDPR čl. 17 lhůta ze zákona | soft-delete, archiv, `valid_to` místo mazání, tombstone místo DELETE | approver, rozsah, hash seznamu, retence (T4) |
| **N6** | změna oprávnění nebo rozpočtu (OPA bundle, gateway klíče/rozpočty, Keycloak role, SPIRE entries, `roles/*.yaml`, HITL body) | P1 Zalozeni, X1, X2 | A2 vlastník procesu + A4 governance (dva schvalovatelé) | konfigurace žije v gitu platformy → N1 (merge) + CI apply; agenti nemají write na OPA/gateway/Keycloak API (OPA deny, CNP) | hook deny; Rego testy v CI | 2/5 → governance | návrh jako PR; dočasné navýšení s `expires_at` | diff, approver ×2, policy_version před/po (T10) |
| **N7** | zápis faktu do schválené paměti (`proposed → approved`, scope firma/zákazník; scope platforma jen člověk) | X2 (dávkově), P5 | A2 vlastník governance (H8); scope zákazník + A3 | **PEP MCP serveru paměti**: `approve_memory` povolen jen identitě HITL aktivity Dapr (SVID), RLS per tenant; agent může jen `proposed` (změřeno M1) | hook deny `approve_memory`; Inspect approval M-E4 | dávkově týdně; bez schválení zůstává `proposed` (čitelné s označením) | `proposed` s nižší confidence; `superseded` místo přepisu | record.id, verifikátor, metoda, původ, pipeline_version |
| **N8** | spuštění nástroje s externím účinkem mimo sandbox (založení/uzavření issue, zápis do CRM, cloud API write, webhook) | P3, P5 | A2 vlastník procesu; **výjimka:** sada „povolené účinky zakázky“ (PR create/update, komentáře na vlastním PR, issue komentář) schválená hromadně v H2 s allow-listem | OPA klasifikace nástrojů: `tool.effect ∈ {none, sandbox, external}`; `external` → approval nebo allow-list zakázky; MCP servery jen za gateway `extAuthz`; egress CNP default-deny | hook `PreToolUse`; Inspect approval policy | 1 prac. den (H3b) → architekt → vlastník | dry-run / náhled artefaktu; fronta ke schválení | tool, args hash, effect class, approval nebo allow-list id |
| **N9** | změna klasifikace tenanta / profilu rizika | P1a, X2 | A4 governance (+ právník u `nejasne`) | OPA data `tenants[].profile` jen z HITL aktivity; změna = N6 | – | 5 prac. dnů | – (ale lze dočasně „přísnější profil“ bez schválení) | profil před/po, zdůvodnění čl. 6(3) (T9), approver |
| **N10** | tajemství: vytvoření, rotace, čtení produkčního secretu, zveřejnění | P5, X1 | A2 vlastník Nasazení | OpenBao: agenti nemají přímý přístup; credential vkládá gateway (`backendAuth`) nebo token exchange; sandbox bez tajemství (S1) | hook deny `vault.*`, srt `credentials.deny` | 1/2 | krátkodobý token s `expires_at` místo dlouhodobého | path (ne hodnota), approver, TTL |

### Rego – společná kostra (návrh, sdílená hookem Agent SDK i OPA-Envoy `extAuthz`)

```rego
package platform.authz

import rego.v1

irreversible := {"git.push_main", "git.merge", "deploy.prod", "comm.external", "payment",
                 "data.delete", "authz.change", "memory.approve", "tool.external", "secret.write"}

default allow := false

# vratné akce: podle role a tenanta (detail v roles/*.yaml → data.roles)
allow if {
    not input.action in irreversible
    not data.tenants[input.tenant].stopped
    input.action in data.roles[input.agent.role].allowed_actions
}

# nevratné akce: jen s platným, nespotřebovaným schválením vázaným na artefakt
allow if {
    input.action in irreversible
    not data.tenants[input.tenant].stopped
    a := data.approvals[input.approval_id]
    a.status == "approved"
    a.action == input.action
    a.zakazka_id == input.zakazka_id
    a.artifact_hash == input.artifact_hash
    a.approver_role in data.policy[input.action].approvers[data.tenants[input.tenant].profile]
    time.now_ns() < time.parse_rfc3339_ns(a.expires_at)
}
```

`data.approvals` = bundle synchronizovaný z Dapr state storu HITL rozhodnutí (approver token z eventu, 1.0.6);
`data.policy[action].approvers[profile]` = tabulka výše jako data. OPA decision log → ClickHouse (T2, T3).

## Timeouty a eskalace

| Krok | Čas (návrh, pracovní dny) | Co se stane | Kdo |
|---|---|---|---|
| T0 | 0 | HITL požadavek v AG-UI + notifikace (issue komentář s T7) | workflow |
| T1 připomínka | 1 | druhá notifikace schvalovateli | workflow timer |
| T2 eskalace | 2 | požadavek přesměrován na vlastníka procesu (pokud schvalovatel byl někdo jiný) / na governance; původní schvalovatel stále může | timer → nový HITL event |
| T3 pozastavení | 5 | workflow zakázky `Pozastaveno`: gateway klíče zakázky `Block`, sandboxy checkpoint + tombstone, A2A tasky `canceled`; zpráva zadavateli (N3 schválená v H1 jako „stavová notifikace“) | workflow |
| resume | – | jen člověk s důvodem (T6); po resume se HITL požadavek obnoví, **neschválí** | vlastník |

Pravidla: timeout **nikdy** = schválení; schválení platí 24 h a jen pro artefakt se stejným hashem; eskalační řetězec
agent → reviewer-agent → vlastník procesu → governance → člověk zákazníka (kriteria.md B3); dva zamítnutí téhož
požadavku za sebou = X1. Durable: čekání přežije restart (změřeno v dapr-agents harnessu T2/T3; 14 dní neměřeno).

HITL rozhraní (T6, čl. 14(4)(a)–(d) – regulace.md): ukazuje limity výstupu (eval skóre, confidence, co nebylo
ověřeno), vyžaduje důvod, umožňuje override (schválit navzdory gate fail – s důvodem, loguje se jako `override=true`).

## Stop tlačítko (T5, T6)

Čl. 14(4)(e) – zastavit do bezpečného stavu (regulace.md T5): stop je **na úrovni durable workflow**, ne promptu.

| Úroveň | Spouští | Co se stane (pořadí) | Co zůstane | Resume |
|---|---|---|---|---|
| **per zakázka** (instance `org.zakazka`) | vlastník procesu, governance (AG-UI tlačítko → Dapr event `stop`) nebo automaticky z X1 | 1. Dapr pause `org.zakazka` + všech child workflow (ověřit API 1.18); 2. běžící sandboxy: 60 s grace na checkpoint = `git push` na větev úkolu (povolená route) + export pracovních poznámek do `proposed`; 3. pod tombstone (delete; RW vrstva zaniká); 4. gateway klíče zakázky → `Block` (rozpočet zmrazen, útrata zachována); 5. OPA data `zakazky[id].stopped=true` (každá akce deny, i vratná); 6. A2A tasky `canceled`; 7. záznam X1 | commity na větvích, artefakty, trace, HITL stav, rozpočtová útrata | člověk s důvodem → OPA `stopped=false` → klíče `Audit` → Dapr resume → nové sandboxy z posledního commitu |
| **per tenant** | governance, člověk zákazníka (A3) | totéž pro všechny instance s `tenant_id`; navíc PEP paměti: zápis pro tenant deny; gateway: všechny klíče tenanta `Block`; SPIRE entries **zůstávají** (identita pro audit), OPA deny | vše výše + paměť tenanta read-only | governance + A3 |
| **per role** (stažení role z procesů) | governance při propadu evalů (L4 alert, pass^k pod gate) | OPA `roles[role].suspended=true` → každá nová aktivita role deny; běžící instance dokončí aktuální stav a jdou do `Pozastaveno`; = N6 | – | po novém eval gate (N6) |

Dopad na HITL: pozastavení zakázky neruší čekající approval (durable); při resume se znovu zobrazí.

## Klasifikační brána (příloha III) – podproces P1a (T9)

Fakta (regulace.md, zralost preview, text OJ nečten): příloha III povinnosti od **2.12.2027** (Omnibus 2026/1744);
bod 4 zaměstnanost pokrývá přidělování úkolů lidem a hodnocení výkonu osob (návrh guidelines 19.5.2026, nefinální);
bod 2 kritická infrastruktura u CER entit; multiagentní platforma = jeden systém (T9); čl. 5 zákazy platí od
2.2.2025; čl. 50(1) disclosure platí od 2.8.2026 (T7) bez ohledu na profil.

| # | Otázka (AG-UI dotazník, odpovídá zadavatel + Account) | Ano → |
|---|---|---|
| K1 | Použije výsledek zakázky nebo agent platformy praktiku z čl. 5 (manipulace, social scoring, …)? | `odmitnout` (policy engine blokuje use case, ne prompt – regulace.md) |
| K2 | Bude agent **přidělovat práci lidem**, hodnotit výkon lidí, rozhodovat o náboru/povýšení/ukončení? | `high-risk-III/4` |
| K3 | Bude agent SRE / dodávaný systém safety komponentou v provozu kritické infrastruktury zákazníka (CER entita)? | `high-risk-III/2` |
| K4 | Je zákazník ve veřejné správě, vymáhání práva, migraci, justici, vzdělávání, přístupu k základním službám (další body přílohy III)? | `nejasne` → právník (H1a) |
| K5 | Mění zákazník intended purpose platformy nebo ji značí vlastní značkou (čl. 25 – stává se providerem)? | `nejasne` + smluvní vymezení intended purpose |
| K6 | Zpracovávají se osobní údaje nad rámec kontaktů (GDPR)? | `sensitivity=personal` v paměti; nemění profil |
| jinak | – | `standard` |

Důsledky profilu:

| Profil | Co se mění |
|---|---|
| `standard` | tabulka N1–N10 jak je; dev/staging deploy A0; kandidát na pravidlo pass^k |
| `high-risk-III/4`, `high-risk-III/2` | T2–T6 povinně (podepsaný append-only log, retence per tenant, HITL s důvodem, stop); N2 produkce A2 + A3 (T13); N3 vždy A2; **žádný posun autonomie** (pravidlo pass^k vypnuto); zdůvodnění čl. 6(3) jako artefakt; risk register per use case (T11); dokumentace čl. 13 (runbook + limity) |
| `odmitnout` | zakázka končí v P1 s auditním záznamem |
| `nejasne` | H1a právník; do stanoviska se zachází jako s high-risk |

Dogfooding: K1–K5 = ne → `standard`. Alokace úkolů **mezi agenty** do bodu 4 nespadá (regulace.md, výklad).

## Pravidlo rozšiřování autonomie (návrh čísel)

HITL bod H_x pro roli R u profilu `standard` se smí přesunout ze schvalovatele A2 (člověk) na A1 (reviewer-agent),
když **všechno** platí za posledních 30 reálných rozhodnutí v tomto bodě:

| Podmínka | Práh (návrh) | Zdroj |
|---|---|---|
| počet reálných HITL rozhodnutí v bodě | ≥ 30 (ne mock) | `org.hitl` spany |
| podíl lidských odmítnutí | ≤ 5 % | `org.hitl.decision` |
| L2 pass^3 role v procesu | ≥ 0,90 (≈ 0,965 per trial) | Inspect `evals_df()` |
| L1 policy-compliance | 100 % | žádná nesankcionovaná akce (OPA deny = 0 pokusů) |
| L3 injection resistance na aktuální sadě | 100 % gate | `inspect_evals` + vlastní sada |
| L5 shoda reviewer-agenta s lidským verdiktem v tomto bodě | ≥ 0,90 | MLflow alignment nad HITL labely |
| L4 drift | žádný otevřený alert 14 dní | MLflow/Prometheus |

Mechanika: změna = PR na `roles/*.yaml` + OPA `policy[action].approvers.standard` → **N6** (vlastník procesu +
governance). Po změně běží „stínový režim“ 30 rozhodnutí: člověk stále schvaluje, reviewer-agent navrhuje; shoda
≥ 0,95 → člověk přechází na **vzorkování 10 %** + právo veta (čl. 14 override). Automatický návrat na A2: jakýkoli
L4 alert, jedno nesankcionované jednání, pass^3 pod práh, nebo incident X1 s dopadem mimo sandbox.

**Nikdy se neposouvá (v0 i později):** H1 a H6 (vstup/výstup zakázky – rozhodnuto Adamem), N2 produkce u high-risk
(T13), N4 platba, N5 výmaz, N6 oprávnění/rozpočet, N9 profil, N10 tajemství. Kandidáti v pořadí: H4 merge
(`standard`, repo zakázky), H2 návrh u malých zakázek (< rozpočtový práh), H5 dev/staging.

## Co se loguje (T3 → pole)

| T3 pole | Kde vzniká |
|---|---|
| session start/end, vstup, výstup | spany `org.process.*`, `gen_ai.*` (ClickHouse) |
| kontext/RAG zdroje | spany `search_memory` s `record.id` |
| nástroj + parametry | `gen_ai.tool.*`; u N1–N10 hash argumentů v OPA decision logu |
| model + verze + provider | gateway request log |
| verze policy | `org.policy_version` (OPA bundle revision) |
| rozhodnutí HITL + identita schvalovatele + důvod | `org.hitl` span + Dapr event s approver tokenem |
| náklad | gateway `cost_usd_total` per klíč |

Retence ≥ 6 měsíců, per tenant výš (T4); append-only + podpis pro high-risk profil (T2).

## Co ověřit dál

- [ ] Harness O-1: nevratný krok bez `approval_id` → 403/deny ve **všech** primárních PEP (gateway git, extAuthz deploy, PEP paměti), timeout → `Pozastaveno` bez schválení, stop během běhu sandboxu zachová commit na větvi, cena zakázky v logu.
- [ ] Dapr Workflow pause/resume (T5) v docs 1.18 a chování child workflow při pause rodiče.
- [ ] Synchronizace `data.approvals` z Dapr state storu do OPA bundle (latence, konzistence) – nebo OPA dotaz na Dapr přes `http.send`?
- [ ] Vazba approval na hash artefaktu u N2 (manifest digest) a N3 (hash zprávy) – praktické u AG-UI editace.
- [ ] Čl. 50(2) a generovaný kód (regulace.md otevřené) – zda PR obsah značit.
- [ ] Prahy pravidla pass^k po prvních 3 zakázkách; kalibrace L5.
- [ ] Právní posouzení profilu `nejasne` – kdo je „právník“ v dogfoodingu.

## Changelog
- 2026-10-23: první verze – stupnice A0–A4, katalog N1–N10 s vynucením a logováním, Rego kostra, timeouty, stop tlačítko, klasifikační brána, pravidlo pass^k (kolo 1, část A).
