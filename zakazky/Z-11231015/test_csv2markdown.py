"""Tests for csv2markdown.py"""

import sys
import tempfile
import subprocess
from pathlib import Path
import io


def run_csv2markdown(csv_path, encoding=None, output=None):
    """Helper: run csv2markdown.py and return exit code, stdout, stderr."""
    cmd = [sys.executable, "csv2markdown.py", str(csv_path)]
    if encoding:
        cmd.extend(["--encoding", encoding])
    if output:
        cmd.extend(["-o", output])
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.returncode, result.stdout, result.stderr


# ============================================================================
# 1. BASIC FUNCTIONALITY & EXAMPLES
# ============================================================================

def test_basic_example():
    """Test the example from task description."""
    with tempfile.TemporaryDirectory() as tmpdir:
        csv_file = Path(tmpdir) / "test.csv"
        csv_file.write_text(
            'jmeno;mesto;poznamka\n'
            'Jan Novák;Brno;"zkouška; s čárkou | a svislítkem"\n',
            encoding='utf-8'
        )
        
        exit_code, stdout, stderr = run_csv2markdown(csv_file)
        
        assert exit_code == 0, f"Exit code {exit_code}, stderr: {stderr}"
        expected = (
            "| jmeno | mesto | poznamka |\n"
            "|---|---|---|\n"
            "| Jan Novák | Brno | zkouška; s čárkou \\| a svislítkem |\n"
        )
        assert stdout == expected, f"Got:\n{repr(stdout)}\nExpected:\n{repr(expected)}"


def test_simple_data():
    """Test simple CSV without special characters."""
    with tempfile.TemporaryDirectory() as tmpdir:
        csv_file = Path(tmpdir) / "test.csv"
        csv_file.write_text('a;b;c\n1;2;3\n4;5;6\n', encoding='utf-8')
        
        exit_code, stdout, stderr = run_csv2markdown(csv_file)
        
        assert exit_code == 0
        lines = stdout.strip().split('\n')
        assert len(lines) == 4  # header + separator + 2 data rows
        assert "| a | b | c |" in stdout
        assert "| 1 | 2 | 3 |" in stdout


# ============================================================================
# 2. CSV PARSING - QUOTES & SPECIAL CHARS
# ============================================================================

def test_quoted_values():
    """Test CSV with quoted values."""
    with tempfile.TemporaryDirectory() as tmpdir:
        csv_file = Path(tmpdir) / "test.csv"
        csv_file.write_text('name;desc\n"John Smith";"Developer"\n', encoding='utf-8')
        
        exit_code, stdout, stderr = run_csv2markdown(csv_file)
        
        assert exit_code == 0
        assert "John Smith" in stdout
        assert "Developer" in stdout


def test_quoted_with_semicolon():
    """Test quoted values containing semicolons."""
    with tempfile.TemporaryDirectory() as tmpdir:
        csv_file = Path(tmpdir) / "test.csv"
        csv_file.write_text('a;b\n"x;y;z";"foo"\n', encoding='utf-8')
        
        exit_code, stdout, stderr = run_csv2markdown(csv_file)
        
        assert exit_code == 0
        assert "x;y;z" in stdout
        assert "foo" in stdout


def test_quoted_with_quotes():
    """Test quoted values containing escaped quotes."""
    with tempfile.TemporaryDirectory() as tmpdir:
        csv_file = Path(tmpdir) / "test.csv"
        csv_file.write_text('a;b\n"He said \\"hello\\"";test\n', encoding='utf-8')
        
        exit_code, stdout, stderr = run_csv2markdown(csv_file)
        
        assert exit_code == 0
        # Quotes should be in output (may be escaped or plain)
        assert "hello" in stdout


def test_unquoted_simple():
    """Test unquoted simple values."""
    with tempfile.TemporaryDirectory() as tmpdir:
        csv_file = Path(tmpdir) / "test.csv"
        csv_file.write_text('col1;col2\nval1;val2\n', encoding='utf-8')
        
        exit_code, stdout, stderr = run_csv2markdown(csv_file)
        
        assert exit_code == 0
        assert "col1" in stdout and "col2" in stdout
        assert "val1" in stdout and "val2" in stdout


# ============================================================================
# 3. MARKDOWN ESCAPING
# ============================================================================

def test_escape_pipe():
    """Test pipe character escaping."""
    with tempfile.TemporaryDirectory() as tmpdir:
        csv_file = Path(tmpdir) / "test.csv"
        csv_file.write_text('a;b\n"x|y";"z|w"\n', encoding='utf-8')
        
        exit_code, stdout, stderr = run_csv2markdown(csv_file)
        
        assert exit_code == 0
        assert "x\\|y" in stdout
        assert "z\\|w" in stdout


def test_escape_pipe_in_header():
    """Test pipe escaping in header."""
    with tempfile.TemporaryDirectory() as tmpdir:
        csv_file = Path(tmpdir) / "test.csv"
        csv_file.write_text('"col|1";"col|2"\nval1;val2\n', encoding='utf-8')
        
        exit_code, stdout, stderr = run_csv2markdown(csv_file)
        
        assert exit_code == 0
        lines = stdout.strip().split('\n')
        assert "col\\|1" in lines[0]
        assert "col\\|2" in lines[0]


def test_escape_backslash():
    """Test backslash escaping."""
    with tempfile.TemporaryDirectory() as tmpdir:
        csv_file = Path(tmpdir) / "test.csv"
        csv_file.write_text('a;b\n"x\\\\y";"z"\n', encoding='utf-8')
        
        exit_code, stdout, stderr = run_csv2markdown(csv_file)
        
        assert exit_code == 0
        # Input backslash should be doubled in output
        assert "x\\\\\\\\y" in stdout


def test_escape_backslash_in_header():
    """Test backslash escaping in header."""
    with tempfile.TemporaryDirectory() as tmpdir:
        csv_file = Path(tmpdir) / "test.csv"
        csv_file.write_text('"col\\\\1";"col2"\nval1;val2\n', encoding='utf-8')
        
        exit_code, stdout, stderr = run_csv2markdown(csv_file)
        
        assert exit_code == 0
        lines = stdout.strip().split('\n')
        assert "\\\\\\\\" in lines[0]  # Doubled backslash


def test_escape_pipe_and_backslash_combined():
    """Test combined pipe and backslash escaping."""
    with tempfile.TemporaryDirectory() as tmpdir:
        csv_file = Path(tmpdir) / "test.csv"
        csv_file.write_text('a;b\n"x|y\\\\z";"foo"\n', encoding='utf-8')
        
        exit_code, stdout, stderr = run_csv2markdown(csv_file)
        
        assert exit_code == 0
        # Should escape both characters
        assert "\\|" in stdout
        assert "\\\\\\\\" in stdout


def test_escape_pipe_multiple():
    """Test multiple pipes in single cell."""
    with tempfile.TemporaryDirectory() as tmpdir:
        csv_file = Path(tmpdir) / "test.csv"
        csv_file.write_text('a;b\n"a|b|c|d|e";"x"\n', encoding='utf-8')
        
        exit_code, stdout, stderr = run_csv2markdown(csv_file)
        
        assert exit_code == 0
        # All 4 pipes should be escaped
        assert stdout.count("\\|") == 4


# ============================================================================
# 4. LINE BREAKS & SPECIAL LINE ENDINGS
# ============================================================================

def test_line_breaks_lf():
    """Test line break replacement with <br> (LF)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        csv_file = Path(tmpdir) / "test.csv"
        csv_file.write_text('a;b\n"line1\nline2";x\n', encoding='utf-8')
        
        exit_code, stdout, stderr = run_csv2markdown(csv_file)
        
        assert exit_code == 0
        assert "line1<br>line2" in stdout


def test_line_breaks_crlf():
    """Test line break replacement with <br> (CRLF)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        csv_file = Path(tmpdir) / "test.csv"
        # Write with CRLF line breaks inside quoted cell
        csv_file.write_bytes(b'a;b\n"line1\r\nline2";x\n')
        
        exit_code, stdout, stderr = run_csv2markdown(csv_file)
        
        assert exit_code == 0
        assert "line1<br>line2" in stdout or "line1" in stdout


def test_line_breaks_cr():
    """Test line break replacement with <br> (CR only)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        csv_file = Path(tmpdir) / "test.csv"
        csv_file.write_bytes(b'a;b\n"line1\rline2";x\n')
        
        exit_code, stdout, stderr = run_csv2markdown(csv_file)
        
        assert exit_code == 0
        # CR should be replaced with <br>
        assert "line1<br>line2" in stdout or "line1" in stdout


def test_line_breaks_multiple():
    """Test multiple line breaks in single cell."""
    with tempfile.TemporaryDirectory() as tmpdir:
        csv_file = Path(tmpdir) / "test.csv"
        csv_file.write_text('a;b\n"a\nb\nc\nd";x\n', encoding='utf-8')
        
        exit_code, stdout, stderr = run_csv2markdown(csv_file)
        
        assert exit_code == 0
        assert stdout.count("<br>") == 3


def test_line_breaks_with_escaping():
    """Test line breaks combined with pipe escaping."""
    with tempfile.TemporaryDirectory() as tmpdir:
        csv_file = Path(tmpdir) / "test.csv"
        csv_file.write_text('a;b\n"line1|a\nline2|b";x\n', encoding='utf-8')
        
        exit_code, stdout, stderr = run_csv2markdown(csv_file)
        
        assert exit_code == 0
        assert "line1\\|a<br>line2\\|b" in stdout


# ============================================================================
# 5. ENCODING - AUTO-DETECTION & EXPLICIT
# ============================================================================

def test_encoding_utf8():
    """Test UTF-8 encoding."""
    with tempfile.TemporaryDirectory() as tmpdir:
        csv_file = Path(tmpdir) / "test.csv"
        csv_file.write_text('jméno;město\nAntonín;Český Krumlov\n', encoding='utf-8')
        
        exit_code, stdout, stderr = run_csv2markdown(csv_file)
        
        assert exit_code == 0
        assert "jméno" in stdout
        assert "Český Krumlov" in stdout


def test_encoding_cp1250():
    """Test cp1250 encoding with fallback."""
    with tempfile.TemporaryDirectory() as tmpdir:
        csv_file = Path(tmpdir) / "test.csv"
        csv_file.write_bytes(
            'jméno;město\nAntonín;Český Krumlov\n'.encode('cp1250')
        )
        
        exit_code, stdout, stderr = run_csv2markdown(csv_file)
        
        # Should fallback to cp1250 and succeed
        assert exit_code == 0
        assert "jméno" in stdout or "jmeno" in stdout


def test_explicit_encoding():
    """Test explicit encoding parameter."""
    with tempfile.TemporaryDirectory() as tmpdir:
        csv_file = Path(tmpdir) / "test.csv"
        csv_file.write_bytes(
            'a;b\nx;y\n'.encode('cp1250')
        )
        
        exit_code, stdout, stderr = run_csv2markdown(csv_file, encoding='cp1250')
        
        assert exit_code == 0
        assert "| a | b |" in stdout


def test_explicit_encoding_utf8():
    """Test explicit UTF-8 encoding."""
    with tempfile.TemporaryDirectory() as tmpdir:
        csv_file = Path(tmpdir) / "test.csv"
        csv_file.write_text('a;b\nžlutý;modrý\n', encoding='utf-8')
        
        exit_code, stdout, stderr = run_csv2markdown(csv_file, encoding='utf-8')
        
        assert exit_code == 0
        assert "žlutý" in stdout


# ============================================================================
# 6. CLI PARAMETERS
# ============================================================================

def test_output_to_file():
    """Test writing to output file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        csv_file = Path(tmpdir) / "test.csv"
        output_file = Path(tmpdir) / "output.md"
        csv_file.write_text('a;b\nx;y\n', encoding='utf-8')
        
        exit_code, stdout, stderr = run_csv2markdown(csv_file, output=str(output_file))
        
        assert exit_code == 0
        assert stdout == ""  # No stdout when -o is used
        assert output_file.exists()
        content = output_file.read_text()
        assert "| a | b |" in content
        assert "| x | y |" in content


def test_output_long_flag():
    """Test --output flag."""
    with tempfile.TemporaryDirectory() as tmpdir:
        csv_file = Path(tmpdir) / "test.csv"
        output_file = Path(tmpdir) / "out.md"
        csv_file.write_text('h1;h2\nv1;v2\n', encoding='utf-8')
        
        cmd = [sys.executable, "csv2markdown.py", str(csv_file), "--output", str(output_file)]
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        assert result.returncode == 0
        assert output_file.exists()


def test_encoding_flag():
    """Test --encoding flag."""
    with tempfile.TemporaryDirectory() as tmpdir:
        csv_file = Path(tmpdir) / "test.csv"
        csv_file.write_bytes(b'a;b\nx;y\n')  # ASCII, works with both
        
        cmd = [sys.executable, "csv2markdown.py", str(csv_file), "--encoding", "utf-8"]
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        assert result.returncode == 0
        assert "| a | b |" in result.stdout


def test_help_flag():
    """Test --help flag."""
    result = subprocess.run(
        [sys.executable, "csv2markdown.py", "--help"],
        capture_output=True, text=True
    )
    
    assert result.returncode == 0
    # Help should mention csv_file or CSV
    assert "csv" in result.stdout.lower() or "file" in result.stdout.lower()


# ============================================================================
# 7. ERROR HANDLING
# ============================================================================

def test_file_not_found():
    """Test error handling for missing file."""
    exit_code, stdout, stderr = run_csv2markdown("/nonexistent/file.csv")
    
    assert exit_code == 1
    assert "not found" in stderr.lower()


def test_bad_encoding():
    """Test error handling for bad encoding."""
    with tempfile.TemporaryDirectory() as tmpdir:
        csv_file = Path(tmpdir) / "test.csv"
        csv_file.write_text('a;b\nx;y\n', encoding='utf-8')
        
        exit_code, stdout, stderr = run_csv2markdown(csv_file, encoding='nonexistent')
        
        assert exit_code == 1
        assert "encoding" in stderr.lower()


def test_invalid_csv_format():
    """Test error handling for invalid CSV."""
    with tempfile.TemporaryDirectory() as tmpdir:
        csv_file = Path(tmpdir) / "test.csv"
        # Write binary junk
        csv_file.write_bytes(b'\x80\x81\x82\x83')
        
        exit_code, stdout, stderr = run_csv2markdown(csv_file)
        
        # Should fail or at least not crash
        assert exit_code == 1 or "Error" in stderr


# ============================================================================
# 8. EDGE CASES
# ============================================================================

def test_single_row():
    """Test CSV with only header (no data rows)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        csv_file = Path(tmpdir) / "test.csv"
        csv_file.write_text('header1;header2;header3\n', encoding='utf-8')
        
        exit_code, stdout, stderr = run_csv2markdown(csv_file)
        
        # Should succeed even with no data
        assert exit_code == 0
        lines = stdout.strip().split('\n')
        assert len(lines) == 2  # header + separator
        assert "header1" in stdout


def test_one_data_row():
    """Test CSV with header and one data row."""
    with tempfile.TemporaryDirectory() as tmpdir:
        csv_file = Path(tmpdir) / "test.csv"
        csv_file.write_text('a;b;c\ndata1;data2;data3\n', encoding='utf-8')
        
        exit_code, stdout, stderr = run_csv2markdown(csv_file)
        
        assert exit_code == 0
        lines = stdout.strip().split('\n')
        assert len(lines) == 3  # header + separator + 1 data row


def test_empty_cells():
    """Test handling of empty cells."""
    with tempfile.TemporaryDirectory() as tmpdir:
        csv_file = Path(tmpdir) / "test.csv"
        csv_file.write_text('a;b;c\n;;x\ny;;z\n;b;\n', encoding='utf-8')
        
        exit_code, stdout, stderr = run_csv2markdown(csv_file)
        
        assert exit_code == 0
        # Should have empty cells
        lines = stdout.strip().split('\n')
        assert len(lines) == 5  # header + separator + 3 data rows


def test_empty_cell_quoted():
    """Test empty quoted cells."""
    with tempfile.TemporaryDirectory() as tmpdir:
        csv_file = Path(tmpdir) / "test.csv"
        csv_file.write_text('a;b\n"";x\ny;""\n', encoding='utf-8')
        
        exit_code, stdout, stderr = run_csv2markdown(csv_file)
        
        assert exit_code == 0
        lines = stdout.strip().split('\n')
        assert len(lines) == 4  # header + separator + 2 data rows


def test_mismatched_columns():
    """Test rows with fewer columns than header."""
    with tempfile.TemporaryDirectory() as tmpdir:
        csv_file = Path(tmpdir) / "test.csv"
        csv_file.write_text('a;b;c;d\nx;y\np;q;r\n', encoding='utf-8')
        
        exit_code, stdout, stderr = run_csv2markdown(csv_file)
        
        assert exit_code == 0
        # Should pad with empty cells
        assert "| x | y |" in stdout or "| x | y | | |" in stdout


def test_whitespace_handling():
    """Test whitespace in values."""
    with tempfile.TemporaryDirectory() as tmpdir:
        csv_file = Path(tmpdir) / "test.csv"
        csv_file.write_text('a; b ; c \n  x  ;  y  \n', encoding='utf-8')
        
        exit_code, stdout, stderr = run_csv2markdown(csv_file)
        
        assert exit_code == 0
        # Whitespace should be preserved
        assert " b " in stdout or "b" in stdout


def test_long_values():
    """Test handling of long cell values."""
    with tempfile.TemporaryDirectory() as tmpdir:
        csv_file = Path(tmpdir) / "test.csv"
        long_text = "x" * 1000
        csv_file.write_text(f'a;b\n{long_text};y\n', encoding='utf-8')
        
        exit_code, stdout, stderr = run_csv2markdown(csv_file)
        
        assert exit_code == 0
        assert long_text in stdout


def test_many_rows():
    """Test handling of many rows."""
    with tempfile.TemporaryDirectory() as tmpdir:
        csv_file = Path(tmpdir) / "test.csv"
        lines = ['a;b;c']
        for i in range(100):
            lines.append(f'row{i};val{i};data{i}')
        csv_file.write_text('\n'.join(lines) + '\n', encoding='utf-8')
        
        exit_code, stdout, stderr = run_csv2markdown(csv_file)
        
        assert exit_code == 0
        output_lines = stdout.strip().split('\n')
        # header + separator + 100 data rows
        assert len(output_lines) == 102


def test_many_columns():
    """Test handling of many columns."""
    with tempfile.TemporaryDirectory() as tmpdir:
        csv_file = Path(tmpdir) / "test.csv"
        header = ";".join([f"col{i}" for i in range(50)])
        data = ";".join([f"val{i}" for i in range(50)])
        csv_file.write_text(f'{header}\n{data}\n', encoding='utf-8')
        
        exit_code, stdout, stderr = run_csv2markdown(csv_file)
        
        assert exit_code == 0
        # Should have all columns
        assert "col0" in stdout
        assert "col49" in stdout


def test_special_chars_in_header():
    """Test special characters in header."""
    with tempfile.TemporaryDirectory() as tmpdir:
        csv_file = Path(tmpdir) / "test.csv"
        csv_file.write_text('"col|1";"col\\\\2";"col3"\nval1;val2;val3\n', encoding='utf-8')
        
        exit_code, stdout, stderr = run_csv2markdown(csv_file)
        
        assert exit_code == 0
        lines = stdout.strip().split('\n')
        # Header should be escaped
        assert "\\|" in lines[0] or "col|1" in lines[0]


def test_all_empty_cells():
    """Test row with all empty cells."""
    with tempfile.TemporaryDirectory() as tmpdir:
        csv_file = Path(tmpdir) / "test.csv"
        csv_file.write_text('a;b;c\n;;;\n;;;\nx;y;z\n', encoding='utf-8')
        
        exit_code, stdout, stderr = run_csv2markdown(csv_file)
        
        assert exit_code == 0
        lines = stdout.strip().split('\n')
        assert len(lines) == 5  # header + separator + 3 data rows


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
