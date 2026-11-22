# csv2md – Úkol 2/4: CLI a error handling

## Implementace ✓

### argparse setup
- Povinný pozicný argument INPUT (cesta k CSV)
- Volitelný `-o OUTPUT` pro výstupní soubor (default: stdout)
- `--encoding {utf-8,cp1250}` s autodetekací (default: None)
- `--help` vždy dostupný

### Error handling
Chybová hlášení na stderr s návratovými kódy:
- **1**: Input file not found (soubor neexistuje)
- **1**: Unable to decode file (chybné kódování)
- **1**: CSV is empty or has no header (bez hlavičky)
- **1**: Cannot write to output file (nelze psát)
- **0**: Úspěch

### Ověření
✓ `csv2md --help` → usage
✓ `csv2md nonexistent.csv` → exit 1, stderr "Input file not found"
✓ `csv2md test_data/sample_utf8.csv` → exit 0, Markdown na stdout
✓ 24 testů prošlo pytest

## Soubory
- `csv2md.py` (186 řádků): parser + CLI + error handling
- `test_core.py`: 24 testů (parser, Markdown engine, CLI)
- Testovací data: sample_utf8.csv, sample_win1250.csv, test_data/

## Stav
Úkol 2 hotov, připraven k příští fázi.

## ÚKOL 2 (OPRAVA kolo 2) - HOTOVO ✅

**Problém (Review feedback):**
- Chyběl soubor `test_cli.py` s integračními testy CLI

**Řešení:**
- Vytvořen `test_cli.py` s 13 integračními testy:
  - `--help` zobrazí usage a INPUT argument ✓
  - `nonexistent.csv` → exit code 1 + stderr "Input file not found" ✓
  - Validní UTF-8 → exit code 0 + Markdown na stdout ✓
  - `-o OUTPUT input.csv` → zapisuje do souboru (exit 0) ✓
  - `--encoding utf-8` a `--encoding cp1250` ✓
  - Chybové stavy (4 typy) na stderr:
    - "Input file not found" ✓
    - "Unable to decode file" ✓
    - "CSV is empty or has no header" ✓
    - "Cannot write to output file" ✓

**Výsledek:**
- pytest: 37/37 passed (24 core + 13 CLI)
- Všechny požadavky z ADR plnul pokryty


---

## ÚKOL 3/4: Testy a testovací data – HOTOVO ✅

### Obsah
Vytořeny pytest suite a testovací data pro kompletní pokrytí:

#### Testovací soubory
- **test_core.py**: 24 jednotkových testů
  - `TestEscapeMarkdownCell` (8 testů): escapování |, \, newlines, CR
  - `TestReadCsv` (8 testů): čtení CSV, quoted values, pipes, backslashes, encoding fallback
  - `TestCsvToMarkdown` (6 testů): generování tabulek, escaped values, empty cells
  - `TestIntegration` (2 testy): end-to-end workflow UTF-8 i CP1250

- **test_cli.py**: 13 integračních CLI testů
  - `TestCLIBasic` (3 testy): --help, nonexistent file, exit codes
  - `TestCLIOutput` (2 testy): -o flag, stdout
  - `TestCLIEncoding` (2 testy): --encoding utf-8, cp1250
  - `TestCLIErrorHandling` (4 testy): všechny error messages
  - `TestCLIExitCodes` (2 testy): exit codes 0 a 1

- **conftest.py**: 5 pytest fixtures
  - `temp_csv_utf8`: dočasný UTF-8 CSV
  - `temp_csv_cp1250`: dočasný CP1250 CSV
  - `temp_csv_with_special_chars`: CSV s |, \, uvozovkami, newlines
  - `temp_empty_csv`: prázdný soubor
  - `temp_csv_no_data`: jen hlavička bez dat

#### Testovací data
- **test_data/sample_utf8.csv**: UTF-8 s českými znaky, quoted values
  ```
  jméno;věk;město
  Alice;30;Praha
  Bob;25;Brno
  "Čeněk""Novák"";40;Plzeň
  ```

- **test_data/sample_cp1250.csv**: Stejný obsah v Windows-1250 kódování

### Pokrytí testů
✓ CSV parsing s uvozovkami a escaped quotes
✓ Escapování | a \ v Markdown
✓ Nové řádky v buňkách (newline → \<br\>)
✓ Prázdné buňky (zůstávají prázdné)
✓ Chybové stavy:
  - nonexistent file → FileNotFoundError
  - missing header → ValueError
  - decode error (špatné kódování) → ValueError
✓ Fallback kódování UTF-8 → CP1250

### Výsledky
```
pytest test_*.py -v
37 passed in 1.69s
  - 24 core tests ✓
  - 13 CLI tests ✓
```

Všechny testy projdou bez chyb. Žádné warnings.

### Soubory úkolu 3
- `test_core.py` ✓
- `test_cli.py` ✓
- `conftest.py` ✓
- `test_data/sample_utf8.csv` ✓
- `test_data/sample_cp1250.csv` ✓

**Status:** Úkol 3 kompletně hotov, připraven k příští fázi (dokumentace/README).
