# Postavení vlastní instance

Tenhle postup ti postaví **tvůj vlastní** druhý mozek: znalostní bázi, skills, agenty
a k tomu MCP server na Cloudflare, ke kterému se připojíš z Claude Desktopu i Claude Code.

Když se chceš jen připojit k cizí běžící instanci, jdi na [pripojeni-klienta.md](pripojeni-klienta.md).

## Co budeš potřebovat

| | |
|---|---|
| Node.js | 20+ (`node -v`) |
| Cloudflare účet | stačí Free tier |
| Git | klon nebo fork tohohle repozitáře |
| Čas | ~20 minut do prvního nasazení |

Free tier bohatě stačí: 100 000 requestů denně, 200 000 log událostí denně, 10 ms CPU na request.

---

## Část 1 – Lokální základ

### 1.1 Klon a instalace

```bash
git clone https://github.com/akczcz/adam.git muj-mozek
cd muj-mozek
rm -rf .git && git init        # chceš vlastní historii, ne moji
cd worker && npm install && cd ..
```

### 1.2 Přepiš identitu

`CLAUDE.md` je jádro celé věci – definuje, kdo agent je, jak mluví a co umí.
Projdi ho a přepiš na sebe: roli, kontext, technologický stack, oblasti zájmu, preference výstupů.

> Tohle je nejdůležitější krok celého postupu. Zbytek je infrastruktura; tady vzniká ta hodnota.

### 1.3 Naplň znalostní bázi

Konvence jsou v [`knowledge/README.md`](../knowledge/README.md). Každý soubor má YAML hlavičku:

```yaml
---
tema: <název>
naposledy_overeno: YYYY-MM-DD
zralost: experimental | preview | stable | legacy
primarni_zdroje:
  - <URL oficiální specifikace>
---
```

Buď si nech `knowledge/protocols/` jako vzor, nebo ho smaž a založ vlastní oblast.
Struktura složek je volná – bundler projde `knowledge/` rekurzivně a ID dokumentu odvodí z cesty.

### 1.4 Skills a agenti (volitelné)

- `.claude/skills/<jmeno>/SKILL.md` – opakovaný postup, který má Claude Code umět vyvolat.
- `.claude/agents/<jmeno>.md` – specializovaný podagent s vlastním kontextem a nástroji.

**Přes MCP se nedistribuují** – jsou to instrukce pro Claude Code, ne data. Kolega je získá klonem repozitáře.

### 1.5 Vyzkoušej to lokálně

```bash
claude
```

Zeptej se na něco ze své báze. Dokud to nefunguje lokálně, nemá smysl to nasazovat.

---

## Část 2 – MCP server na Cloudflare

### 2.1 Pojmenuj Worker

V `worker/wrangler.jsonc` změň `name` – tvoří první část veřejné URL a musí být v rámci tvého účtu unikátní:

```jsonc
{
  "name": "muj-mozek-mcp",   // → muj-mozek-mcp.<tvuj-subdomain>.workers.dev
  "main": "src/index.ts",
  ...
}
```

### 2.2 Přihlaš se do Cloudflare

```bash
cd worker
npx wrangler login
```

### 2.3 Vygeneruj tokeny

Pro každého, kdo se bude připojovat, jeden token:

```bash
openssl rand -base64 32 | tr -d '/+=' | head -c 40; echo
```

Server umí **víc tokenů oddělených čárkou**, každý s volitelným štítkem:

```
adam:PRVNI_TOKEN,kolega-jan:DRUHY_TOKEN,kolegyne-eva:TRETI_TOKEN
```

| Vlastnost | Proč to chceš |
|---|---|
| Štítek se loguje při úspěšné autentizaci | ve Workers Logs je vidět, kdo se připojuje |
| Odvolání je smazání jedné položky | ostatním to nespadne |
| Token se do logu nikdy nedostane | loguje se výhradně štítek |

Štítek musí odpovídat `[A-Za-z0-9._-]{1,32}`. Bez štítku dostane token v logu jen `token#1`, `token#2` podle pořadí.

### 2.4 Nahraj tokeny jako secret

```bash
npx wrangler secret put MCP_BEARER_TOKEN
# vlož celý řetězec i se štítky a čárkami
```

Secret je write-only – zpátky ho nepřečteš. Ulož si ho do správce hesel.

> Bez nastaveného `MCP_BEARER_TOKEN` Worker vrací 500 a nic neobsluhuje. Je to schválně:
> lepší tvrdě spadnout než nechat bázi omylem veřejně.

### 2.5 Nasaď

```bash
npm run deploy    # spustí build:knowledge i wrangler deploy
```

Výstup ti vypíše veřejnou URL.

### 2.6 Ověř

```bash
curl -s https://muj-mozek-mcp.<tvuj-subdomain>.workers.dev/health
```

A pak kompletní smoke test (12 kontrol – autentizace, nástroje, resources, obě éry protokolu):

```bash
python3 -m venv ../tools/.venv-smoke
../tools/.venv-smoke/bin/pip install httpx
../tools/.venv-smoke/bin/python scripts/smoke_worker.py \
  https://muj-mozek-mcp.<tvuj-subdomain>.workers.dev PRVNI_TOKEN
```

Čekej `SOUHRN: 12/12 prošlo`.

### 2.7 Zapni observability

V Cloudflare dashboardu → tvůj Worker → **Settings → Observability → Workers Logs: Enable**.
Bez toho neuvidíš, kdo se připojuje. Co kde hledat, ukazuje [architektura.md](architektura.md#cloudflare--co-je-kde-vidět).

---

## Část 3 – Připoj se

Postup je stejný jako pro cizí instanci, jen s tvojí URL a tvým tokenem:
**[pripojeni-klienta.md](pripojeni-klienta.md)**

---

## Provoz

### Změna znalostní báze

`knowledge.generated.ts` je build artefakt mimo git. Po každé změně v `knowledge/`:

```bash
cd worker && npm run deploy
```

Bez redeploye server pořád servíruje starou verzi. `/health` vrací `knowledge_built_at`, podle toho se pozná, co je nasazené.

### Přidání kolegy

```bash
openssl rand -base64 32 | tr -d '/+=' | head -c 40    # nový token
npx wrangler secret put MCP_BEARER_TOKEN              # celý seznam + nová položka
```

Redeploy není potřeba – secret se projeví hned.

### Odvolání

Stejný postup, jen položku vynecháš.

### Lokální vývoj

```bash
cd worker
cp .dev.vars.example .dev.vars    # vyplň testovací tokeny
npm run dev
```

`.dev.vars` je v `.gitignore`. Pozor: `wrangler dev` změnu `.dev.vars` za běhu **nepřenačte** – po úpravě ho restartuj.

---

## Než to dáš veřejně

- [ ] `git log -S'<token>'` nad historií – token nikdy neprošel commitem
- [ ] `.dev.vars` a `.claude/settings.local.json` jsou v `.gitignore`
- [ ] `CLAUDE.md` neobsahuje jména klientů ani interní kontext
- [ ] Screenshoty nemají v rohu e-mail, jméno účtu ani interní URL
- [ ] `knowledge/` neobsahuje nic pod NDA

## Omezení, se kterými počítej

Sdílený bearer token je **dočasné řešení**. Nemá expiraci, rotace je ruční a endpoint nemá rate limiting.
Pro cokoliv nad rámec testování v malé skupině počítej s OAuth podle MCP spec nebo s předřazením Cloudflare Access.
Soupis je v [architektura.md](architektura.md#známá-omezení).
