# CSV to Markdown Converter

A Python CLI tool that converts CSV files to Markdown tables for wiki documentation.

## Features

- **CSV Parsing**: Supports comma (`,`) and semicolon (`;`) delimiters
- **Encoding Support**: Handles UTF-8 and other encodings
- **Special Character Escaping**: Properly escapes pipes (`|`), backslashes (`\`), and newlines
- **JSON API**: Returns structured JSON responses (`status`, `message`, `data`)
- **Multiple Output Formats**: Markdown to stdout or file, or JSON format
- **Comprehensive Testing**: Full unit test coverage with sample test data

## Installation

```bash
# No external dependencies - uses only Python stdlib
python3 -m pip install pytest  # Optional, for running tests
```

## Usage

### Basic CLI Usage

```bash
# Convert CSV to Markdown (output to stdout)
python main.py data.csv

# Save to file
python main.py data.csv --output table.md

# Use semicolon delimiter
python main.py data.csv --delimiter ";"

# Different encoding
python main.py data.csv --encoding "latin-1"

# JSON output
python main.py data.csv --json
```

### Programmatic Usage

```python
from converter import convert_csv_to_markdown

result = convert_csv_to_markdown('data.csv', delimiter=',', encoding='UTF-8')

if result['status'] == 'ok':
    markdown = result['data']['markdown']
    print(markdown)
else:
    print(f"Error: {result['message']}")
```

## Response Format

### Success Response
```json
{
  "status": "ok",
  "message": "CSV converted successfully",
  "data": {
    "markdown": "| Name | Age |\n| --- | --- |\n| John | 28 |"
  }
}
```

### Error Response
```json
{
  "status": "error",
  "message": "File not found: data.csv",
  "data": {}
}
```

## Examples

### Example 1: Basic CSV Conversion

**Input** (`sample1.csv`):
```
Name,Age,City,Occupation
John Doe,28,New York,Engineer
Jane Smith,34,San Francisco,Designer
Bob Johnson,45,Chicago,Manager
```

**Command**:
```bash
python main.py test_samples/sample1.csv
```

**Output**:
```markdown
| Name | Age | City | Occupation |
| --- | --- | --- | --- |
| John Doe | 28 | New York | Engineer |
| Jane Smith | 34 | San Francisco | Designer |
| Bob Johnson | 45 | Chicago | Manager |
```

### Example 2: Special Characters

**Input** (`sample2.csv`):
```
Title,Content,Notes
"Basic Data","Hello, World!","Comma test"
"Pipe Test","Data | with | pipes","Backslash \ test"
"Newline Test","Line1
Line2","Multi-line cell"
```

**Command**:
```bash
python main.py test_samples/sample2.csv
```

**Output**:
```markdown
| Title | Content | Notes |
| --- | --- | --- |
| Basic Data | Hello, World! | Comma test |
| Pipe Test | Data \| with \| pipes | Backslash \\ test |
| Newline Test | Line1 Line2 | Multi-line cell |
```

### Example 3: Empty Cells

**Input** (`sample3.csv`):
```
Name,Middle,LastName,Age,City
John,,Doe,28,New York
Jane,Marie,Smith,34,
Bob,J.,Johnson,,Chicago
```

**Command**:
```bash
python main.py test_samples/sample3.csv
```

**Output**:
```markdown
| Name | Middle | LastName | Age | City |
| --- | --- | --- | --- | --- |
| John |  | Doe | 28 | New York |
| Jane | Marie | Smith | 34 |  |
| Bob | J. | Johnson |  | Chicago |
```

## Testing

### Run All Tests

```bash
pytest test_converter.py -v
```

### Run Specific Test Class

```bash
pytest test_converter.py::TestEscapeMarkdown -v
pytest test_converter.py::TestCSVToMarkdown -v
pytest test_converter.py::TestFileConversion -v
```

### Test Coverage

The test suite includes:
- **Escaping Tests**: Pipe (`|`), backslash (`\`), newline, whitespace handling
- **CSV Conversion Tests**: Basic data, special characters, newlines, empty cells
- **File Operations**: Reading test samples, error handling, encoding
- **API Tests**: Response format, success/error states, parameter passing
- **Sample Files**: 3 representative test CSV files included

## Architecture

### `converter.py`
Core conversion logic:
- `CSVToMarkdownConverter` class: Main converter with file/string handling
- `_escape_markdown()`: Escapes special characters for Markdown tables
- `convert_csv_to_markdown()`: High-level function returning ACME-compliant JSON

### `main.py`
CLI interface:
- Argument parsing (input, delimiter, encoding, output, format)
- Output handling (stdout, file, JSON)
- Exit codes (0 for success, 1 for errors)

### `test_converter.py`
Comprehensive test suite with 15+ test cases covering:
- Character escaping
- CSV parsing with various scenarios
- File I/O operations
- Error handling
- JSON response format

## Special Character Handling

| Character | Replacement | Example |
| --- | --- | --- |
| `\|` (pipe) | `\|` | `a\|b` |
| `\` (backslash) | `\\` | `a\\b` |
| Newline | Space | `line1 line2` |

## Command Line Options

```
usage: main.py [-h] [--delimiter {,,;}] [--encoding ENCODING] 
               [--output OUTPUT] [--json] input

positional arguments:
  input                 Input CSV file path

optional arguments:
  -h, --help           show this help message and exit
  --delimiter {,,;}    CSV delimiter (default: comma)
  --encoding ENCODING  File encoding (default: UTF-8)
  --output OUTPUT      Output markdown file (optional)
  --json               Output as JSON (default: Markdown)
```

## Error Handling

The tool gracefully handles:
- Missing files
- Encoding errors
- Malformed CSV (missing headers, etc.)
- Invalid parameters
- Empty CSV files

All errors return proper error responses with descriptive messages.

## Notes

- Empty cells are preserved in the output
- Rows shorter than headers are padded with empty cells
- Cell content is trimmed of leading/trailing whitespace
- Markdown tables use standard format with pipes and dashes
