#!/usr/bin/env python3
"""
csv2md.py - Konvertor CSV na Markdown tabulku
Podporuje UTF-8 a cp1250 kódování, escapování znaků, zalomení řádků.
"""
import sys
import csv
import argparse
from pathlib import Path


def detect_encoding(file_path):
    """Pokus se detekovat kódování: UTF-8 → cp1250 fallback."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            f.read()
        return 'utf-8'
    except UnicodeDecodeError:
        return 'cp1250'


def escape_markdown(text):
    """Escapovat backslash a pipe pro Markdown, \n nahradit <br>."""
    text = str(text)
    text = text.replace('\\', '\\\\')  # \ → \\
    text = text.replace('|', '\\|')    # | → \|
    text = text.replace('\n', '<br>')  # \n → <br>
    text = text.replace('\r', '')      # odstranit \r
    return text


def csv_to_markdown(input_file, output_file=None, encoding=None):
    """
    Konvertovat CSV na Markdown tabulku.
    
    Args:
        input_file: Cesta ke CSV souboru
        output_file: Cesta k výstupnímu souboru (None = stdout)
        encoding: Kódování (None = autodetekce)
    
    Returns:
        (exit_code, output_text)
    """
    try:
        # Kontrola existence souboru
        if not Path(input_file).exists():
            return 1, f"Chyba: Soubor '{input_file}' nenalezen."
        
        # Detekce/validace kódování
        if encoding is None:
            encoding = detect_encoding(input_file)
        
        # Čtení CSV
        rows = []
        try:
            with open(input_file, 'r', encoding=encoding, newline='') as f:
                reader = csv.reader(f, delimiter=';')
                for row in reader:
                    rows.append(row)
        except UnicodeDecodeError as e:
            return 1, f"Chyba při dekódování: {e}"
        except Exception as e:
            return 1, f"Chyba při čtení CSV: {e}"
        
        if not rows:
            return 1, "Chyba: CSV soubor je prázdný."
        
        # Hlavička a data
        header = rows[0]
        data_rows = rows[1:]
        
        # Odstranit prázdné řádky
        data_rows = [row for row in data_rows if any(cell.strip() for cell in row)]
        
        # Vytvořit Markdown tabulku
        lines = []
        
        # Řádek hlavičky
        header_escaped = [escape_markdown(cell) for cell in header]
        lines.append('| ' + ' | '.join(header_escaped) + ' |')
        
        # Oddělovací řádek
        lines.append('|' + '|'.join(['---'] * len(header)) + '|')
        
        # Data řádky
        for row in data_rows:
            # Doplnit chybějící buňky
            while len(row) < len(header):
                row.append('')
            # Zaříznout na délku hlavičky
            row = row[:len(header)]
            # Escapovat a vytvořit řádek
            row_escaped = [escape_markdown(cell) for cell in row]
            lines.append('| ' + ' | '.join(row_escaped) + ' |')
        
        output = '\n'.join(lines)
        
        # Zápis výstupu
        if output_file:
            try:
                with open(output_file, 'w', encoding='utf-8') as f:
                    f.write(output)
            except Exception as e:
                return 1, f"Chyba při zápisu do souboru: {e}"
        
        return 0, output
    
    except Exception as e:
        return 1, f"Neočekávaná chyba: {e}"


def main():
    parser = argparse.ArgumentParser(
        description='Konvertor CSV na Markdown tabulku (oddělovač: ;)',
        prog='csv2md.py'
    )
    parser.add_argument(
        'input_file',
        help='Cesta ke vstupnímu CSV souboru'
    )
    parser.add_argument(
        '-o', '--output',
        help='Cesta k výstupnímu Markdown souboru (výchozí: stdout)'
    )
    parser.add_argument(
        '--encoding',
        help='Kódování CSV souboru (utf-8, cp1250; výchozí: autodetekce)'
    )
    
    args = parser.parse_args()
    
    exit_code, output = csv_to_markdown(
        args.input_file,
        output_file=args.output,
        encoding=args.encoding
    )
    
    if exit_code == 0:
        if not args.output:
            print(output)
    else:
        print(output, file=sys.stderr)
    
    sys.exit(exit_code)


if __name__ == '__main__':
    main()
