#!/usr/bin/env python3
"""CLI entry point for CSV to Markdown converter."""
import argparse
import json
import sys
from converter import convert_csv_to_markdown


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description='Convert CSV files to Markdown tables',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
  python main.py data.csv
  python main.py data.csv --delimiter ";"
  python main.py data.csv --encoding "latin-1" --output table.md
        '''
    )
    
    parser.add_argument(
        'input',
        help='Input CSV file path'
    )
    parser.add_argument(
        '--delimiter',
        default=',',
        choices=[',', ';'],
        help='CSV delimiter (default: comma)'
    )
    parser.add_argument(
        '--encoding',
        default='UTF-8',
        help='File encoding (default: UTF-8)'
    )
    parser.add_argument(
        '--output',
        help='Output markdown file (optional, prints to stdout if not specified)'
    )
    parser.add_argument(
        '--json',
        action='store_true',
        help='Output as JSON (default: Markdown)'
    )
    
    args = parser.parse_args()
    
    # Convert CSV to Markdown
    result = convert_csv_to_markdown(
        args.input,
        delimiter=args.delimiter,
        encoding=args.encoding
    )
    
    if args.json:
        # Output JSON format
        print(json.dumps(result, indent=2))
        sys.exit(0 if result['status'] == 'ok' else 1)
    else:
        # Output Markdown
        if result['status'] == 'ok':
            markdown = result['data']['markdown']
            if args.output:
                with open(args.output, 'w', encoding='UTF-8') as f:
                    f.write(markdown)
                print(f"Markdown table written to: {args.output}", file=sys.stderr)
            else:
                print(markdown)
            sys.exit(0)
        else:
            print(f"Error: {result['message']}", file=sys.stderr)
            sys.exit(1)


if __name__ == '__main__':
    main()
