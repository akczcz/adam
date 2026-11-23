# csv2md – Konvertor CSV na Markdown

Nástroj pro konverzi CSV tabulek (s oddělovačem **středník**) na **GitHub Flavored Markdown** tabulky.

## Popis

Slouží k export datových tabulek z firemního systému do formátu Markdown vhodného pro wiki a dokumentaci. Podporuje kódování UTF-8 a Windows-1250, automaticky detekuje mezní znaky a zavádí správné escapování.

## Instalace

**Jediný požadavek: Python 3** (bez dodatečných balíčků – všechny knihovny jsou součástí standardní knihovny).

```bash
python3 csv2md.py vstup.csv
```

## Příklady použití

### Základní konverze – výstup na stdout
```bash
python3 csv2md.py vzorek.csv
```

### Zápis do souboru parametrem `-o`
```bash
python3 csv2md.py vzorek.csv -o vystup.md
```

### Určení kódování (výchozí: autodetekce UTF-8 → cp1250)
```bash
python3 csv2md.py vzorek.csv --encoding cp1250
```

### Nápověda
```bash
python3 csv2md.py --help
```

## Formát vstupu

**CSV oddělený středníkem** (`;`), první řádek = názvy sloupců.

Příklad:
```
jmeno;mesto;poznamka
Jan Novák;Brno;"zkouška; s čárkou | a svislítkem"
```

## Formát výstupu

**GitHub Flavored Markdown tabulka** s levým zarovnáním:

```
| jmeno | mesto | poznamka |
|---|---|---|
| Jan Novák | Brno | zkouška; s čárkou \| a svislítkem |
```

## Speciální znaky

- **Backslash** (`\`) → `\\` (escapován)
- **Pipe** (`|`) → `\|` (escapován)
- **Zalomení řádku** (`\n`) → `<br>` (HTML tag)
- **Prázdné buňky** zůstávají prázdné

## Návratové kódy

- `0` = úspěch
- `1` = chyba (soubor nenalezen, chyba kódování)

---

**Poznámka:** Nástroj **nepoužívá žádné externí balíčky** – všechny funkce jsou postaveny na standardní knihovně Pythonu 3.
