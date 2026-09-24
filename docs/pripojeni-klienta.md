# Připojení k běžícímu MCP serveru

Tenhle postup je pro **konzumenty** – chceš se připojit k instanci, kterou provozuje někdo jiný.
Když si chceš postavit vlastní, jdi na [vlastni-instance.md](vlastni-instance.md).

## Co potřebuješ

| | |
|---|---|
| URL | `https://adam-knowledge-mcp.a-k-cz.workers.dev/mcp` |
| Token | dostaneš od provozovatele – **nikdy ho nedávej do gitu, Slacku ani do issue** |
| Ověření bez tokenu | `curl https://adam-knowledge-mcp.a-k-cz.workers.dev/health` |

Health endpoint funguje bez autentizace a je dobrý první test, že vůbec vidíš na server:

```bash
curl -s https://adam-knowledge-mcp.a-k-cz.workers.dev/health
# {"status":"ok","server":{"name":"adam-knowledge","version":"0.1.0"},"documents":6,...}
```

## Krok 1 – ověř token mimo klienta

Než budeš cokoliv konfigurovat, ujisti se, že token funguje. Ušetří ti to hodinu ladění špatného místa.

```bash
export MCP_TOKEN='sem-vloz-token'

curl -s -X POST https://adam-knowledge-mcp.a-k-cz.workers.dev/mcp \
  -H "Authorization: Bearer $MCP_TOKEN" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'
```

- Vrátí seznam nástrojů → token i endpoint jsou v pořádku.
- `401` → špatný token, nebo ti ho už provozovatel odvolal.

> `export` s mezerou na začátku řádku (` export …`) se ve většině shellů neuloží do historie. Hodí se.

## Krok 2a – Claude Code

Nejjednodušší cesta, protože Claude Code umí vzdálené HTTP MCP servery nativně, včetně hlaviček.

```bash
claude mcp add --transport http adam-knowledge \
  https://adam-knowledge-mcp.a-k-cz.workers.dev/mcp \
  --header "Authorization: Bearer $MCP_TOKEN"
```

Ověření:

```bash
claude mcp list
```

## Krok 2b – Claude Desktop (macOS)

Desktopová appka **neumí** u custom connectoru zadat statický bearer token – UI nabízí jen URL a OAuth.
Řeší se to lokálním mostem `mcp-remote`, který hlavičku doplní.

Otevři konfiguraci:

```bash
open -a TextEdit ~/Library/Application\ Support/Claude/claude_desktop_config.json
```

A do `mcpServers` přidej:

```json
"mcpServers": {
  "adam-knowledge": {
    "command": "/opt/homebrew/bin/npx",
    "args": [
      "-y",
      "mcp-remote",
      "https://adam-knowledge-mcp.a-k-cz.workers.dev/mcp",
      "--transport", "http-only",
      "--header", "Authorization:${AUTH_HEADER}"
    ],
    "env": {
      "AUTH_HEADER": "Bearer SEM_VLOZ_TOKEN"
    }
  }
}
```

Pak Claude úplně ukonči a spusť znovu – zavření okna nestačí:

```bash
osascript -e 'quit app "Claude"' && sleep 2 && open -a Claude
```

### Tři věci, na kterých to typicky padne

| Příznak | Příčina | Řešení |
|---|---|---|
| `spawn npx ENOENT` | GUI aplikace nedědí shell PATH | absolutní cesta k `npx` (`which npx`) |
| Token „nefunguje", ale curl projde | `mcp-remote` seká argumenty po mezerách | token musí být v `env`, v `--header` jen `Authorization:${AUTH_HEADER}` |
| Dlouhý start, divné chyby v logu | klient zkouší nejdřív SSE | `--transport http-only` |

Log mostu:

```bash
tail -50 ~/Library/Logs/Claude/mcp-server-adam-knowledge.log
```

## Krok 3 – vyzkoušej, že to opravdu čte bázi

Zeptej se něčím, co jde ověřit:

- „Použij `protocol_status` na `mcp` a řekni mi `naposledy_overeno`."
- „Prohledej znalostní bázi na `stateless` a cituj, ze kterého souboru to je."

Když odpověď obsahuje název souboru a datum ověření, jede to přes MCP. Když je obecná a bez zdroje, klient server nepoužil.

## Co server umí

| Typ | Název | K čemu |
|---|---|---|
| Tool | `search_knowledge` | fulltext, vrací sekce i se zdrojem a datem ověření |
| Tool | `protocol_status` | verze, zralost, `naposledy_overeno`, zdroje, otevřené otázky pro jeden protokol |
| Resource | `knowledge://<id>` | celý dokument jako Markdown |

Server je **read-only**. Nic, co přes něj uděláš, bázi nezmění – ta se edituje jen v gitu.

## Hygiena tokenu

- Token je vázaný na tebe a má v logu serveru svůj štítek, takže je vidět, kdo se připojuje.
- Když ho vyzradíš, řekni to – odvolání jednoho tokenu ostatní neshodí.
- Nedávej ho do repozitáře, do screenshotů ani do URL.
