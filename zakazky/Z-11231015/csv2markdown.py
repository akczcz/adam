#!/usr/bin/env python3
"""
csv2markdown.py - Convert CSV to GitHub Flavored Markdown table.

Features:
- CSV parser with semicolon delimiter, quote support, and line breaks
- Encoding autodetection (UTF-8 → cp1250 fallback, with --encoding override)
- Markdown generator with escape of | and \ characters
- CLI interface with -o/--output, --encoding, --help
- Exit code 0 for success, 1 for errors
"""

import sys
import csv
import argparse
from pathlib import Path


def detect_encoding(file_path):
    """Autodetect file encoding: try UTF-8, fallback to cp1250."""
    encodings = ['utf-8', 'cp1250']
    for encoding in encodings:
        try:
            with open(file_path, 'r', encoding=encoding) as f:
                f.read()
            return encoding
        except (UnicodeDecodeError, LookupError):
            continue
    return None


def escape_markdown_cell(value):
    """Escape | and \ characters in markdown cell values.
    Order matters: escape \ first, then |."""
    if not isinstance(value, str):
        value = str(value) if value is not None else ""
    # Escape backslash first
    value = value.replace('\\', '\\\\')
    # Then escape pipe
    value = value.replace('|', '\\|')
    # Replace line breaks with <br>
    value = value.replace('\r\n', '<br>')
    value = value.replace('\r', '<br>')
    value = value.replace('\n', '<br>')
    return value


def csv_to_markdown(csv_path, encoding=None):
    """Convert CSV file to GitHub Flavored Markdown table.
    
    Args:
        csv_path: Path to CSV file
        encoding: Explicit encoding (if None, autodetect)
    
    Returns:
        Markdown string or None on error
    """
    # Resolve path
    csv_path = Path(csv_path)
    if not csv_path.exists():
        print(f"Error: File '{csv_path}' not found", file=sys.stderr)
        return None
    
    # Detect or use explicit encoding
    if encoding is None:
        encoding = detect_encoding(csv_path)
        if encoding is None:
            print(f"Error: Could not detect encoding for '{csv_path}'", file=sys.stderr)
            return None
    else:
        # Verify explicit encoding works
        try:
            with open(csv_path, 'r', encoding=encoding) as f:
                f.read()
        except (UnicodeDecodeError, LookupError) as e:
            print(f"Error: Invalid encoding '{encoding}': {e}", file=sys.stderr)
            return None
    
    # Parse CSV
    try:
        with open(csv_path, 'r', encoding=encoding, newline='') as f:
            reader = csv.reader(f, delimiter=';', quotechar='"', quoting=csv.QUOTE_MINIMAL)
            rows = list(reader)
    except Exception as e:
        print(f"Error: Failed to parse CSV: {e}", file=sys.stderr)
        return None
    
    if not rows:
        print("Error: CSV file is empty", file=sys.stderr)
        return None
    
    # Build markdown table
    header = rows[0]
    body_rows = rows[1:]
    
    # Header row
    markdown = "| " + " | ".join(escape_markdown_cell(h) for h in header) + " |\n"
    
    # Separator row (one --- per column)
    markdown += "|" + "|".join("---" for _ in header) + "|\n"
    
    # Body rows
    for row in body_rows:
        # Pad row with empty strings if fewer columns than header
        row = list(row) + [''] * (len(header) - len(row))
        # Keep only as many columns as header
        row = row[:len(header)]
        markdown += "| " + " | ".join(escape_markdown_cell(cell) for cell in row) + " |\n"
    
    return markdown


def main():
    parser = argparse.ArgumentParser(
        description="Convert CSV to GitHub Flavored Markdown table",
        prog="csv2markdown.py"
    )
    parser.add_argument(
        "csv_file",
        help="Path to CSV file (semicolon-delimited)"
    )
    parser.add_argument(
        "-o", "--output",
        help="Output file (default: stdout)"
    )
    parser.add_argument(
        "--encoding",
        help="Explicit encoding (default: autodetect UTF-8 or cp1250)"
    )
    
    args = parser.parse_args()
    
    # Convert CSV to markdown
    markdown = csv_to_markdown(args.csv_file, encoding=args.encoding)
    if markdown is None:
        sys.exit(1)
    
    # Write output
    if args.output:
        try:
            with open(args.output, 'w', encoding='utf-8') as f:
                f.write(markdown)
        except Exception as e:
            print(f"Error: Failed to write to '{args.output}': {e}", file=sys.stderr)
            sys.exit(1)
    else:
        print(markdown, end='')
    
    sys.exit(0)


if __name__ == "__main__":
    main()
