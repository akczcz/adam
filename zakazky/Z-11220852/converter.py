"""CSV to Markdown converter module."""
import csv
import json
from typing import List, Dict, Tuple
from io import StringIO


class CSVToMarkdownConverter:
    """Converts CSV files to Markdown tables."""
    
    def __init__(self, delimiter: str = ',', encoding: str = 'UTF-8'):
        """Initialize converter with delimiter and encoding.
        
        Args:
            delimiter: CSV delimiter (',' or ';')
            encoding: File encoding (default 'UTF-8')
        """
        if delimiter not in [',', ';']:
            raise ValueError(f"Unsupported delimiter: {delimiter}")
        self.delimiter = delimiter
        self.encoding = encoding
    
    @staticmethod
    def _escape_markdown(text: str) -> str:
        """Escape special Markdown characters.
        
        Args:
            text: Text to escape
            
        Returns:
            Escaped text safe for Markdown tables
        """
        if not isinstance(text, str):
            text = str(text)
        # Strip leading/trailing whitespace from cells
        text = text.strip()
        # Replace newlines FIRST with space to keep table valid
        text = text.replace('\n', ' ').replace('\r', '')
        # Escape backslash BEFORE pipe to avoid double-escaping
        text = text.replace('\\', '\\\\')
        # Escape pipe with backslash
        text = text.replace('|', '\\|')
        return text
    
    def csv_to_markdown(self, csv_content: str) -> Tuple[bool, str, str]:
        """Convert CSV content to Markdown table.
        
        Args:
            csv_content: CSV content as string
            
        Returns:
            Tuple of (success: bool, markdown: str, error_msg: str)
        """
        try:
            # Parse CSV
            reader = csv.reader(
                StringIO(csv_content),
                delimiter=self.delimiter
            )
            rows = list(reader)
            
            if not rows:
                return False, "", "CSV is empty"
            
            # Extract header and body
            header = rows[0]
            body = rows[1:]
            
            if not header:
                return False, "", "No header found in CSV"
            
            # Escape header cells
            escaped_header = [self._escape_markdown(cell) for cell in header]
            
            # Build Markdown table
            markdown_lines = []
            
            # Add header
            markdown_lines.append('| ' + ' | '.join(escaped_header) + ' |')
            
            # Add separator (minimum 3 dashes per column)
            separator = '|' + '|'.join([' --- ' for _ in header]) + '|'
            markdown_lines.append(separator)
            
            # Add body rows
            for row in body:
                # Pad row to match header length
                padded_row = row + [''] * (len(header) - len(row))
                escaped_row = [
                    self._escape_markdown(padded_row[i])
                    for i in range(len(header))
                ]
                markdown_lines.append('| ' + ' | '.join(escaped_row) + ' |')
            
            markdown = '\n'.join(markdown_lines)
            return True, markdown, ""
            
        except Exception as e:
            return False, "", f"Error parsing CSV: {str(e)}"
    
    def convert_file(self, filepath: str) -> Tuple[bool, str, str]:
        """Convert CSV file to Markdown table.
        
        Args:
            filepath: Path to CSV file
            
        Returns:
            Tuple of (success: bool, markdown: str, error_msg: str)
        """
        try:
            with open(filepath, 'r', encoding=self.encoding) as f:
                content = f.read()
            return self.csv_to_markdown(content)
        except FileNotFoundError:
            return False, "", f"File not found: {filepath}"
        except UnicodeDecodeError as e:
            return False, "", f"Encoding error ({self.encoding}): {str(e)}"
        except Exception as e:
            return False, "", f"Error reading file: {str(e)}"


def convert_csv_to_markdown(
    filepath: str,
    delimiter: str = ',',
    encoding: str = 'UTF-8'
) -> Dict:
    """High-level function to convert CSV to Markdown.
    
    Args:
        filepath: Path to CSV file
        delimiter: CSV delimiter
        encoding: File encoding
        
    Returns:
        Dict with 'status', 'message', and 'markdown' keys
    """
    try:
        converter = CSVToMarkdownConverter(delimiter=delimiter, encoding=encoding)
        success, markdown, error = converter.convert_file(filepath)
        
        if success:
            return {
                'status': 'ok',
                'message': 'CSV converted successfully',
                'data': {'markdown': markdown}
            }
        else:
            return {
                'status': 'error',
                'message': error,
                'data': {}
            }
    except Exception as e:
        return {
            'status': 'error',
            'message': f"Unexpected error: {str(e)}",
            'data': {}
        }
