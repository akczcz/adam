# csv2md – CSV do Markdown

Nástroj pro konverzi CSV souboru se středníkem jako oddělovačem do tabulky ve formátu GitHub Markdown (GFM).

## Účel

Tento nástroj zjednoduší export dat z vnitřních systémů do wiki nebo dokumentace v Markdown. Podporuje:
- CSV s oddělovačem `;` (středník)
- Uvozovaná pole a zdvojené uvozovky uvnitř polí
- Speciální znaky (`|`, `\\`, nové řádky)
- Kódování UTF-8 i Windows-1250 (automatická detekce nebo explicitní specifikace)

## Instalace

Nástroj vyžaduje Python 3.6+ a používá pouze standardní knihovnu (bez externích závislostí).

```bash
# Klonuj repozitář (nebo zkopíruj csv2md.py do svého projektu)
git clone <repo-url>
cd csv2md

# Ověř, že Python je dostupný
python3 --version
```

## Spuštění

### Základní použití: výstup na stdout

```bash
csv2md input.csv
```

**Příklad 1:** Konverze CSV na Markdown s výstupem v terminálu

```bash
$ csv2md examples/input.csv
| Jméno | Věk | Město |
|---|---|---|
| Alice | 30 | Praha |
| Bob | 25 | Brno |
```

### Uložení do souboru: `-o / --output`

```bash
csv2md -o output.md input.csv
```

**Příklad 2:** Uložení konvertovaného souboru

```bash
$ csv2md examples/input.csv -o examples/output.md
$ cat examples/output.md
| Jméno | Věk | Město |
|---|---|---|
| Alice | 30 | Praha |
| Bob | 25 | Brno |
```

### Specifikace kódování: `--encoding`

Pokud autodetekce nepostačuje, specifikuj kódování explicitně:

```bash
# UTF-8 (výchozí pokus, obvykle zbytečné)
csv2md input.csv --encoding utf-8

# Windows-1250 (pro staršíexporty)
csv2md input.csv --encoding cp1250
```

**Příklad 3:** Konverze souboru s kódováním Windows-1250

```bash
$ csv2md examples/input.csv --encoding cp1250
```

## Příklad vstupu a výstupu

### Vstup (CSV)

Soubor `examples/input.csv`:

```csv
Jméno;Věk;Město
Alice;30;Praha
Bob;25;Brno
"David|Michal";35;Plzeň
```

Všimni si:
- První řádek je hlavička
- Pole s `|` jsou v uvozovkách
- Speciální znaky se v Markdown escapují

### Výstup (Markdown)

Příkaz:
```bash
csv2md examples/input.csv
```

Výstup:
```markdown
| Jméno | Věk | Město |
|---|---|---|
| Alice | 30 | Praha |
| Bob | 25 | Brno |
| David\|Michal | 35 | Plzeň |
```

Pozoruj:
- Znaková `|` je escapednuta na `\|`
- Všechny buňky jsou zarovnány do tabulky
- Nové řádky v polích se nahradí `<br>`

## Chybové stavy a návratové kódy

Nástroj vrací následující kódy:

| Situace | Kód | Stderr zpráva | Příklad |
|---------|-----|---|----------|
| Úspěch | 0 | Žádná | `csv2md input.csv` → Markdown na stdout |
| Soubor neexistuje | 1 | `Error: Input file not found` | `csv2md neexist.csv` |
| Chybné kódování | 1 | `Error: Unable to decode file` | Pokud soubor není UTF-8 ani cp1250 |
| Bez hlavičky | 1 | `Error: CSV must contain at least one row (header)` | CSV s 0 řádky |
| Chybná použití CLI | 2 | `usage: csv2md [-h] [-o OUTPUT] ...` | `csv2md` (bez argumentů) |

### Příklady chyb

```bash
# Chyba: soubor neexistuje
$ csv2md nemam.csv
Error: Input file not found
$ echo $?
1

# Chyba: bez hlavičky (soubor je prázdný)
$ echo -n "" > prazdny.csv
$ csv2md prazdny.csv
Error: CSV must contain at least one row (header)
$ echo $?
1

# Chyba: nevhodné argumenty
$ csv2md
usage: csv2md [-h] [-o OUTPUT] [--encoding {utf-8,cp1250}] INPUT
csv2md: error: the following arguments are required: INPUT
$ echo $?
2
```

## Nápověda

```bash
csv2md --help
```

Výstup:
```
usage: csv2md [-h] [-o OUTPUT] [--encoding {utf-8,cp1250}] INPUT

Konvertuj CSV do Markdown tabulky

positional arguments:
  INPUT                 Cesta k vstupnímu CSV souboru

options:
  -h, --help            show this help message and exit
  -o OUTPUT, --output OUTPUT
                        Cesta k výstupnímu souboru (výchozí: stdout)
  --encoding {utf-8,cp1250}
                        Kódování CSV souboru (výchozí: autodetekce
                        utf-8/cp1250)
```

## Poznámky pro praktické použití

- **Speciální znaky:** Znaek `|` a `\\` jsou v Markdown escapovány backslash (resp. `\\|` a `\\\\`)
- **Nové řádky:** Pokud CSV obsahuje nové řádky v poli (CRLF nebo LF), budou nahrazeny `<br>`
- **Prázdné buňky:** Zůstávají prázdné (bez speciálních znaků)
- **Uvozovky:** Pole s uvozovkami jsou automaticky zpracovány; zdvojené uvozovky (`""`) uvnitř pole se stanou jednoduchou uvozovkou

## Testování

Projekt obsahuje testovací sadu:

```bash
# Spusť všechny testy
pytest -q

# Spusť konkrétní test
pytest test_cli.py::test_basic_conversion -v
```

Testy ověřují:
- Konverzi na stdout i do souboru
- Správné escapování speciálních znaků
- Podporu obou kódování (UTF-8, cp1250)
- Chybové stavy a návraty
