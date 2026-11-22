#!/usr/bin/env python3
"""
csv2md core module: CSV parser a Markdown engine
"""
import csv
import sys
import argparse
from io import StringIO
from typing import List, Dict, Optional


def read_csv(filepath: str, encoding: Optional[str] = None) -> List[Dict]:
    """
    Čte CSV soubor se středníkem jako oddělovačem.
    Pokud se encoding neuvedel, zkusí UTF-8, pak cp1250.
    
    Args:
        filepath: cesta k CSV souboru
        encoding: kódování (utf-8, cp1250, None = autodetekce)
    
    Returns:
        seznam řádků jako slovníky
    
    Raises:
        FileNotFoundError: pokud soubor neexistuje
        ValueError: když soubor nelze dekódovat nebo nemá hlavičku
    """
    # Zkontroluj, zda soubor existuje
    try:
        with open(filepath, 'rb') as f:
            pass
    except FileNotFoundError:
        raise FileNotFoundError(f"Input file not found")
    
    # Pokud je encoding specifikován, použij ho
    encodings_to_try = [encoding] if encoding else ['utf-8', 'cp1250']
    
    content = None
    last_error = None
    
    for enc in encodings_to_try:
        if enc is None:
            continue
        try:
            with open(filepath, 'r', encoding=enc) as f:
                content = f.read()
            break
        except (UnicodeDecodeError, LookupError) as e:
            last_error = e
            continue
    
    if content is None:
        raise ValueError(f"Nelze dekódovat soubor '{filepath}' v žádném podporovaném kódování")
    
    # Parsuj CSV se středníkem
    reader = csv.DictReader(StringIO(content), delimiter=';', quotechar='"')
    
    if reader.fieldnames is None or len(reader.fieldnames) == 0:
        raise ValueError(f"Soubor '{filepath}' nemá hlavičku nebo je prázdný")
    
    rows = list(reader)
    return rows


def escape_markdown_cell(value: str) -> str:
    r"""
    Escapuje znaky | a \ v buňce.
    Nahradí newline za <br>.
    Odstraní \r (carriage return).
    
    Args:
        value: hodnota buňky (str nebo None)
    
    Returns:
        escapovaná hodnota
    """
    if value is None:
        return ""
    
    # Odstraň carriage return
    value = value.replace('\r', '')
    
    # Nahraď newline za <br>
    value = value.replace('\n', '<br>')
    
    # Escapuj \ a | (pořadí je důležité!)
    value = value.replace('\\', '\\\\')
    value = value.replace('|', '\\|')
    
    return value


def csv_to_markdown(rows: List[Dict]) -> str:
    """
    Konvertuje seznam řádků (dict) na GFM tabulku.
    
    Args:
        rows: seznam slovníků (z read_csv)
    
    Returns:
        GFM tabulka jako string
    
    Raises:
        ValueError: prázdný seznam řádků
    """
    if not rows:
        raise ValueError("Seznam řádků je prázdný")
    
    # Zjisti sloupce z prvního řádku
    columns = list(rows[0].keys())
    
    # Vytvořit hlavičku
    header = "| " + " | ".join(columns) + " |"
    separator = "|" + "|".join(["---" for col in columns]) + "|"
    
    # Vytvořit řádky
    lines = [header, separator]
    for row in rows:
        escaped_values = [escape_markdown_cell(row.get(col, "")) for col in columns]
        line = "| " + " | ".join(escaped_values) + " |"
        lines.append(line)
    
    return "\n".join(lines)


def main():
    """
    Main CLI entry point s argparse
    """
    parser = argparse.ArgumentParser(
        prog='csv2md',
        description='Konvertuj CSV do Markdown tabulky'
    )
    parser.add_argument(
        'input',
        metavar='INPUT',
        help='Cesta k vstupnímu CSV souboru'
    )
    parser.add_argument(
        '-o', '--output',
        metavar='OUTPUT',
        help='Cesta k výstupnímu souboru (výchozí: stdout)'
    )
    parser.add_argument(
        '--encoding',
        choices=['utf-8', 'cp1250'],
        default=None,
        help='Kódování CSV souboru (výchozí: autodetekce utf-8/cp1250)'
    )
    
    args = parser.parse_args()
    
    try:
        rows = read_csv(args.input, args.encoding)
        markdown = csv_to_markdown(rows)
        
        if args.output:
            try:
                with open(args.output, 'w', encoding='utf-8') as f:
                    f.write(markdown)
            except (IOError, OSError) as e:
                print("Cannot write to output file", file=sys.stderr)
                sys.exit(1)
        else:
            print(markdown)
    
    except FileNotFoundError as e:
        print("Input file not found", file=sys.stderr)
        sys.exit(1)
    except ValueError as e:
        error_msg = str(e)
        # Pro CLI error handling - specifické zprávy podle úkolu 2
        if "Nelze dekódovat" in error_msg:
            print("Unable to decode file", file=sys.stderr)
        elif "nemá hlavičku" in error_msg or "je prázdný" in error_msg:
            print("CSV is empty or has no header", file=sys.stderr)
        else:
            # Pro testy z úkolu 1 - vracíme původní zprávu
            print(error_msg, file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
