# csv2markdown – Konvertor CSV na Markdown tabulku

## Úvod

`csv2markdown` je nástroj pro převod CSV souborů na tabulky ve formátu **GitHub Flavored Markdown (GFM)**.
Používá se v prostředí, kde potřebujete CSV export z vašeho informačního systému převést na wiki formát
vhodný pro publikaci na GitHub nebo GitLab.

Nástroj je napsán čistě v Pythonu se standardní knihovnou – nevyžaduje instalaci dalších balíčků
a pracuje offline.

## Instalace

### Požadavky

- **Python 3.7** nebo novější
- Operační systém: Linux, macOS, Windows

Ke spuštění nejsou potřebné žádné externí balíčky (pip).

### Získání skriptu

Stáhněte soubor `csv2markdown.py` z repozitáře a umístěte ho do pracovního adresáře:

```bash
# Jednoduše spustíte z adresáře, kde máte CSV soubor:
python3 csv2markdown.py vstup.csv
```

Skript lze spustit z libovolné cesty:

```bash
# Z libovolného místa s absolutní nebo relativní cestou
python3 /cesta/k/csv2markdown.py /cesta/k/vstup.csv
```

## Spuštění a příklady

### Základní příkaz

Převod CSV na stdout:

```bash
python3 csv2markdown.py vstup.csv
```

**Příklad vstupu** (`vstup.csv`):
```csv
jmeno;mesto;poznamka
Jan Novák;Brno;"zkouška; s čárkou | a svislítkem"
```

**Výstup na stdout**:
```
| jmeno | mesto | poznamka |
|---|---|---|
| Jan Novák | Brno | zkouška; s čárkou \| a svislítkem |
```

### Zápis do souboru

Převod CSV do souboru Markdown:

```bash
python3 csv2markdown.py vstup.csv -o výstup.md
```

Výsledný soubor `výstup.md` obsahuje GFM tabulku.

### Specifikace kódování

Pokud je CSV v jiném kódování (Windows-1250, cp1250), použijte:

```bash
python3 csv2markdown.py data_cp1250.csv --encoding cp1250
```

Bez parametru se kódování detekuje automaticky (UTF-8 → cp1250).

### Nápověda

Zobrazení kompletní nápovědy:

```bash
python3 csv2markdown.py --help
```

Výstup:
```
usage: csv2markdown.py [-h] [--output OUTPUT] [--encoding ENCODING] path

Convert CSV (semicolon-delimited) to GitHub Flavored Markdown table.

positional arguments:
  path                  Path to CSV file

optional arguments:
  -h, --help            show this help message and exit
  --output OUTPUT, -o OUTPUT
                        Output file (default: stdout)
  --encoding ENCODING   Explicit encoding (default: autodetect UTF-8 → cp1250)
```

## Parametry

### Poziční argument

**`<cesta>`** (povinný)
- Cesta k CSV souboru (absolutní nebo relativní)
- Příklad: `vstup.csv`, `/home/user/data.csv`

### Volitelné parametry

**`-o <soubor>`, `--output <soubor>`**
- Zápis výstupu do souboru místo stdout
- Příklad: `-o výstup.md`, `--output result.md`
- Default: Markdown se tiskne na standardní výstup (stdout)

**`--encoding <kódování>`**
- Explicitní specifikace znakové sady souboru
- Podporovaná kódování: `utf-8`, `cp1250` (Windows-1250)
- Příklad: `--encoding cp1250`
- Default: Automatická detekce (nejdřív UTF-8, pak cp1250)

**`-h`, `--help`**
- Zobrazí nápovědu a skončí
- Příklad: `python3 csv2markdown.py --help`

## Příklady vstup/výstup

### Příklad 1: Jednoduché data bez speciálních znaků

**Vstup** (`jednoduche.csv`):
```csv
Jméno;Věk;Město
Alice;28;Praha
Bob;34;Plzeň
```

**Příkaz**:
```bash
python3 csv2markdown.py jednoduche.csv
```

**Výstup**:
```markdown
| Jméno | Věk | Město |
|---|---|---|
| Alice | 28 | Praha |
| Bob | 34 | Plzeň |
```

### Příklad 2: Speciální znaky (pipe, backslash)

**Vstup** (`specialni.csv`):
```csv
Popis;Příkaz
Oddělení řádků;echo "text | tabulka"
Cesta;C:\data\soubor.txt
```

**Příkaz**:
```bash
python3 csv2markdown.py specialni.csv
```

**Výstup**:
```markdown
| Popis | Příkaz |
|---|---|---|
| Oddělení řádků | echo "text \| tabulka" |
| Cesta | C:\\data\\soubor.txt |
```

### Příklad 3: Uvozovky a středníky v hodnotách

**Vstup** (`uvozovky.csv`):
```csv
Jméno;Poznamka
Jan;"Pozn.: přijít; v 15:00 | prosím"
```

**Příkaz**:
```bash
python3 csv2markdown.py uvozovky.csv
```

**Výstup**:
```markdown
| Jméno | Poznamka |
|---|---|---|
| Jan | Pozn.: přijít; v 15:00 \| prosím |
```

### Příklad 4: Zalomení řádků v buňce

**Vstup** (`zalomeni.csv`):
```csv
Nadpis;Obsah
Instrukce;"1. Stáhni soubor
2. Otevři editor
3. Ulož soubor"
```

**Příkaz**:
```bash
python3 csv2markdown.py zalomeni.csv
```

**Výstup**:
```markdown
| Nadpis | Obsah |
|---|---|---|
| Instrukce | 1. Stáhni soubor<br>2. Otevři editor<br>3. Ulož soubor |
```

### Příklad 5: Windows-1250 kódování

**Vstup** (`cesky.csv`) – soubor v kódování cp1250:
```csv
Příjmení;Město
Čech;Čelákovice
Žák;Žebrák
```

**Příkaz**:
```bash
python3 csv2markdown.py cesky.csv --encoding cp1250
```

**Výstup**:
```markdown
| Příjmení | Město |
|---|---|---|
| Čech | Čelákovice |
| Žák | Žebrák |
```

## Troubleshooting

### Chyba kódování

**Problém**: Při spuštění se objeví chyba `UnicodeDecodeError` nebo znaky nejsou čitelné.

**Řešení**: Zkuste explicitně zadat kódování:

```bash
# Pokud je soubor v Windows-1250:
python3 csv2markdown.py vstup.csv --encoding cp1250

# Pokud je v UTF-8:
python3 csv2markdown.py vstup.csv --encoding utf-8
```

Pokud s odhadem stále máte problém, otevřete si soubor v textovém editoru (VS Code, Notepad++)
a zkontrolujte kódování v statusbaru.

### Soubor nenalezen

**Problém**: `FileNotFoundError: [Errno 2] No such file or directory: 'vstup.csv'`

**Řešení**: Zkontrolujte, že:
- Cesta k souboru je správná (je v aktuálním adresáři?)
- Píšete správné jméno souboru (včetně přípony `.csv`)
- Máte práva na čtení souboru

```bash
# Zkontrolujte obsah aktuálního adresáře:
ls -la

# Nebo použijte absolutní cestu:
python3 csv2markdown.py /cesta/k/vstup.csv
```

### Chybový formát CSV

**Problém**: Výstup vypadá divně, sloupce nejsou správně odděleny.

**Řešení**: Zkontrolujte, že:
- Oddělovač v CSV je **středník** (`;`) – ne čárka, ne tabulátor
- Pokud hodnota obsahuje středník, musí být v **uvozovkách**:
  ```csv
  Jméno;Popis
  Jan;"pozn.: toto; je seznam"
  ```
- Pokud hodnota obsahuje uvozovky, zdvojte je v uvozovkách:
  ```csv
  Nadpis;Text
  Příklad;"řekl: ""Ahoj"""
  ```

Pokud si nejste jisti formátem, otevřete CSV v Excelu nebo LibreOffice a ověřte strukturu.

## Limitace a poznámky

### Maximální velikost

- Nástroj podporuje CSV soubory do **10 000 řádků** (bez hlavičky)
- Vhodné pro CSV velikosti řádově do **několika MB**
- Více řádků nebo větších souborů může vyžadovat specializovaný nástroj

### Oddělovač

- Nástroj podporuje **pouze středník** (`;`) jako oddělovač
- Pokud máte CSV s čárkami nebo tabulátory, musíte soubor nejdřív převést
  (Např. v Excelu: Uložit jako → CSV (s oddělovačem `;`)

### Markdown formát

- Výstup je ve formátu **GitHub Flavored Markdown (GFM)** bez rozšíření
- Tabulka používá základní syntax: `| buňka |` a `|---|---|` pro řádek s oddělovačem
- **Levé zarovnání** – bez specifikace zarovnání (`:---`, `:---:`, `---:`)
- Speciální znaky se escapují:
  - `|` (pipe) → `\|`
  - `\` (backslash) → `\\`
- Zalomení řádků se nahrazují: `\n`, `\r\n`, `\r` → `<br>`

### Prázdné buňky

- Prázdné hodnoty v CSV zůstávají prázdné i v Markdown tabulce
- Nejsou nahrazeny žádným znakem (jako `-`, `N/A` apod.)

### Exit kódy

- `0` – Úspěšná konverze, skript skončil bez chyby
- `1` – Chyba (soubor nenalezen, špatné kódování, chyba parsování CSV, chyba při zápisu)

Používejte exit kódy v bash skriptech:
```bash
python3 csv2markdown.py vstup.csv -o výstup.md
if [ $? -eq 0 ]; then
  echo "Konverze úspěšná"
else
  echo "Konverze selhala"
fi
```

---

**Verze**: 1.0  
**Poslední aktualizace**: 2026-11-23
