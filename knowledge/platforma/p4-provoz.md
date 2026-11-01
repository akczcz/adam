---
tema: P4 – provoz platformy se zákazníkem po P3 (položky po jedné, každá PR + měření na AKS)
naposledy_overeno: 2026-11-01
---

# P4 – provoz

**Závěr:** P3 skončilo uzavřením P3-6 (2026-11-01). P4 nemá pevný checklist – Adam zadává položky po jedné; kandidáti vycházejí
z [p3-zakaznik.md](p3-zakaznik.md) „Co zůstává zjednodušené i v P3“. Postup práce stejný: větev → `measure` s `e2e=p4-n` → PR → merge → cluster `stop`.

## Kroky

| Krok | Co | Stav |
|---|---|---|
| **P4-1** Obnova mandátu z GUI | mandát role = access token člověka (30 min) – role bez HITL před sebou jednala bez mandátu (E2 nález 5); Keycloak `act` nepomůže ani po GA | 🟡 kód 2026-11-01, měření AKS RUNRESULT (`measure` run RUNID, RUNCOUNT běhy) |
| kandidát | ostrý běh s živým modelem a GitHubem (PAT/klíč jen v Key Vaultu) | ⬜ |
| kandidát | mTLS mesh uvnitř clusteru (zbytek plaintextu mezi službami) | ⬜ |
| kandidát | realm per tenant (vlastní IdP federace zákazníka) | ⬜ |
| kandidát | SLA reporting (smluvní pohled místo timerů) | ⬜ |

## P4-1 Obnova mandátu z GUI

**Rozhodnutí:** mandát („jedná jménem“) zůstává `sub` schvalovatele + `azp` klienta role z Keycloak V2 exchange v podu (P3-6 E2). Co se mění:
aplikace drží **poslední známý mandát** zakázky mimo stav workflow – dá ho založení, každé schválení a **obnova z GUI**; před startem role vybere
ten a vypršelý nepoužije (role běží bez mandátu, ale **viditelně**: ledger `MANDAT missing`, GUI karta „Role bez mandátu“ s tlačítkem). Živý mandát
držitele, který má GUI otevřené, se prodlužuje sám (keepalive každých 30 s, když zbývá < 10 min); **vypršelý mandát obnoví jen člověk kliknutím** –
automatická resuscitace by z přítomnosti v GUI dělala souhlas.

| Varianta | Proč ne / proč ano |
|---|---|
| Keycloak delegace `act` | preview; GA (27.0) nezruší souhlas per session ani 1 actor/login ([identity/keycloak.md](../identity/keycloak.md)) |
| offline / refresh token člověka v aplikaci | aplikace by držela dlouhodobý credential člověka – mandát bez člověka; proti Q6 |
| blokující HITL „obnov mandát“ před každou rolí | zastaví autonomii; degradace s viditelností + obnova z GUI zachová tok, stricter policy může přijít z OPA (high-risk profil → vyžadovat mandát) |
| **poslední známý mandát + obnova/keepalive z GUI** (zvoleno) | token žije jen 30 min, pochází vždy od přihlášeného člověka, GUI = místo, kde člověk je |

Tok: GUI → `POST /agui/threads/<id>/mandat` (token člověka tenanta zakázky; tenant platform 403) → aplikace `subject_set` (soubor 0600 na PVC,
ledger `MANDAT` bez tokenu) → `agent_run` → Secret podu `P0_SUBJECT_TOKEN` → exchange v podu (E2) → paměť `on_behalf_of`, `org.agents.on_behalf_of`.
Měření `tools/harness_p1_k8s --step p4-1` (M1a–c): vypršení se simuluje `POST /_mandat/expire` (plynutí času), ne čekáním 30 min.

Výsledek: **doplním po měření** (`measure` run RUNID). Nálezy: doplním.

## Rizika

| Riziko | Řešení |
|---|---|
| Mandát obnoví jiný člověk tenanta než schvalovatel → role jedná jeho jménem | ledger `MANDAT renewed by`, GUI ukazuje držitele; kdo klikne, přebírá odpovědnost (T1) – stejné jako schválení |
| Keepalive = GUI otevřené v zapomenuté záložce drží mandát „navždy“ | jen dokud žije refresh token GUI (Keycloak SSO session); prodlužuje jen živý mandát držitele; zapsat do GUI timeout session (kandidát) |
| Tokeny v souboru aplikace | krátkodobé (30 min), 0600, tytéž tokeny jsou v historii workflow v Postgresu; úklid po 30 dnech |

## Changelog
- 2026-11-01: založeno; P4-1 návrh a kód (obnova mandátu z GUI), měření doplním.
