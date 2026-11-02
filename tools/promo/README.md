# Promo video – komentovaný průlet autonomní firmou

Technické publikum, česky, ≤ 3 min, mp4. Komentář mluví o komponentách vrstev (Dapr Workflows, Claude Agent SDK, agentgateway,
Keycloak, SPIRE, OPA, OpenBao, Kata, ClickHouse, OTEL, AG-UI) nad skutečným během zakázky v GUI na AKS.

| Soubor | Co |
|---|---|
| `scenes.py` | scénář: pořadí scén (karta / GUI), titulky, odrážky komponent, text komentáře (TTS čte doslova) |
| `record.py` | natáčení: Playwright nad `gui_checks.Gui` harnessu, `record_video` 1920×1080, časové značky scén → `out/scenes.json`, karty → `out/cards/*.png` |
| `render.py` | TTS Azure AI Speech (REST, SSML, `SPEECH_KEY` jen v env) + ffmpeg: karta = statický obraz s pomalým zoomem, GUI = klip s dolní lištou; `promo.mp4` + `promo.srt` |
| `.github/workflows/promo.yml` | běh na runneru proti clusteru: dočasný Speech resource F0 (vytvořit → použít → smazat + purge), artifact `promo-<run>` |

Postup: cluster běží (`cluster.yml` start), neběží měření → workflow `promo` → stáhnout artifact → `promo.mp4`.
Bez `SPEECH_KEY` render vloží ticho (kontrola střihu bez útraty). Změna textu = `scenes.py` → stačí znovu `render.py` nad starou nahrávkou.

Předpoklady: provider `Microsoft.CognitiveServices` registrovaný v předplatném (dělá Adam z Macu, identita Actions providery neregistruje);
Speech F0 není v Poland Central, West Europe nepřijímá nové zákazníky → workflow zkouší regiony po řadě (North Europe, Sweden Central, …). Zakázka pro video běží na mock modelu (bez útraty), nic se nepublikuje ven.
