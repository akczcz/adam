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
| **P4-1** Obnova mandátu z GUI | mandát role = access token člověka (30 min) – role bez HITL před sebou jednala bez mandátu (E2 nález 5); Keycloak `act` nepomůže ani po GA | ✅ 2026-11-01 AKS 79/79 + 14 INFO (`measure` run 41297792885, 4 běhy) |
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

Výsledek: **79/79 + 14 INFO** (`measure` run 41297792885, 4 běhy; detail a tabulka běhů v [harness README](../../tools/harness_p1_k8s/README.md#p4-1-m1--obnova-mandátu-z-gui-2026-11-01-aks---step-p4-1--p3-6--m1ac)).
Ověřeno: vypršelý mandát = role bez mandátu **viditelně** (ledger `MANDAT missing`, GUI karta), kliknutí obnoví, keepalive prodlouží jen živý mandát
držitele, další role (architekt) jedná s obnoveným mandátem (`sub` adam v exchange podu, `org.agents.on_behalf_of`).

Nálezy:

- **Stav v modulu aplikace = jedna kopie modulu, jedna replika.** Aplikace běží jako `__main__`, líný `import app` z aktivit rolí vytvořil druhou kopii
  modulu s vlastním slovníkem mandátů a přepsal callbacky AG-UI → obnova z GUI šla jinam, než odkud role čtou (běh 2). Opraveno aliasem
  `sys.modules["app"]`. Důsledek pro návrh: Deployment aplikace má `replicas: 1` (Recreate); škálování aplikace vyžaduje mandát ve sdíleném úložišti
  (Dapr state / Postgres) – kandidát, až bude potřeba víc replik.
- **Registr agentů drží poslední běh role**, ne historii: Account po odpovědi na dialog běží druhé kolo už s obnoveným mandátem → `on_behalf_of` adam.
  Otázka „kdo kdy jednal bez mandátu“ se odpovídá z ledgeru (`MANDAT`, `ROLE_POD`), ne z registru (běh 3).
- Měřicí: Playwright v `measure.yml` jen pro `p3-*` (běh 1), kolize prefixu `data-testid` v GUI (U1b), stará hodnota v GUI prošla kontrolou keepalive
  (M1c), pád port-forwardu aplikace během GUI části (E13b/c, harness ho obnoví) – vše v harness README.

## Rizika

| Riziko | Řešení |
|---|---|
| Mandát obnoví jiný člověk tenanta než schvalovatel → role jedná jeho jménem | ledger `MANDAT renewed by`, GUI ukazuje držitele; kdo klikne, přebírá odpovědnost (T1) – stejné jako schválení |
| Keepalive = GUI otevřené v zapomenuté záložce drží mandát „navždy“ | jen dokud žije refresh token GUI (Keycloak SSO session); prodlužuje jen živý mandát držitele; zapsat do GUI timeout session (kandidát) |
| Tokeny v souboru aplikace | krátkodobé (30 min), 0600, tytéž tokeny jsou v historii workflow v Postgresu; úklid po 30 dnech |

## Changelog
- 2026-11-01: založeno; P4-1 návrh a kód (obnova mandátu z GUI).
- 2026-11-01: P4-1 hotovo na AKS (79/79 + 14 INFO, 4 běhy) – nálezy: dvojí import `app.py` (stav v modulu ⇒ jedna replika), registr = poslední běh role.
