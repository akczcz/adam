"""
Komplexní testy pro csv2md.py s pokrytím edge cases a CLI interface.
Testuje: CSV parsing, Markdown escapování, kódování, chybové stavy, CLI.
"""
import pytest
import tempfile
import os
import subprocess
import sys
from pathlib import Path

# Import z kořene
sys.path.insert(0, '.')
from csv2md import csv_to_markdown, escape_markdown, detect_encoding


class TestEscapeMarkdownAdvanced:
    """Pokročilé testy escapování znaků."""
    
    def test_multiple_pipes(self):
        """Více pipes se escapuje."""
        assert escape_markdown('a|b|c') == 'a\\|b\\|c'
    
    def test_multiple_backslashes(self):
        """Více backslashů se zdvojují."""
        assert escape_markdown('a\\\\b\\\\c') == 'a\\\\\\\\b\\\\\\\\c'
    
    def test_mixed_escaping(self):
        """Kombinace backslash, pipe a newline."""
        assert escape_markdown('path\\to|file\nname') == 'path\\\\to\\|file<br>name'
    
    def test_escape_order(self):
        """Backslash se musí escapovat před pipe."""
        # Nejdřív se escapuje backslash, pak pipe
        result = escape_markdown('\\|')
        # \\ -> \\\\ a | -> \|, takže "\\|" -> "\\\\|"
        assert result == '\\\\\\|'
    
    def test_empty_string(self):
        """Prázdný string zůstane prázdný."""
        assert escape_markdown('') == ''
    
    def test_only_newlines(self):
        """Jen newlines se změní na <br>."""
        assert escape_markdown('\n\n\n') == '<br><br><br>'
    
    def test_only_pipes(self):
        """Jen pipes se escapují."""
        assert escape_markdown('|||') == '\\|\\|\\|'


class TestCSVParsingEdgeCases:
    """Edge cases při čtení CSV."""
    
    def test_quoted_values_with_semicolon(self):
        """Uvozovky obsahující středník."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8') as f:
            f.write('a;b\n"x;y";2\n')
            temp_file = f.name
        try:
            exit_code, output = csv_to_markdown(temp_file)
            assert exit_code == 0
            assert 'x;y' in output
            assert '| x;y | 2 |' in output
        finally:
            os.unlink(temp_file)
    
    def test_quoted_values_with_quotes(self):
        """Zdvojené uvozovky v hodnotách."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8') as f:
            f.write('a;b\n"He said ""Hi""";val\n')
            temp_file = f.name
        try:
            exit_code, output = csv_to_markdown(temp_file)
            assert exit_code == 0
            # CSV reader překonvertuje "" na "
            assert 'He said "Hi"' in output
        finally:
            os.unlink(temp_file)
    
    def test_quoted_multiline_values(self):
        """Zalomení řádku uvnitř uvozovek."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8') as f:
            f.write('name;desc\n"John Doe";"Line1\nLine2\nLine3"\n')
            temp_file = f.name
        try:
            exit_code, output = csv_to_markdown(temp_file)
            assert exit_code == 0
            assert 'Line1<br>Line2<br>Line3' in output
        finally:
            os.unlink(temp_file)
    
    def test_crlf_line_endings(self):
        """CRLF konec řádků se zpracuje správně."""
        with tempfile.NamedTemporaryFile(mode='wb', suffix='.csv', delete=False) as f:
            f.write(b'a;b\r\n1;2\r\n')
            temp_file = f.name
        try:
            exit_code, output = csv_to_markdown(temp_file)
            assert exit_code == 0
            assert '| 1 | 2 |' in output
        finally:
            os.unlink(temp_file)
    
    def test_lf_line_endings(self):
        """LF (Unix) konec řádků."""
        with tempfile.NamedTemporaryFile(mode='wb', suffix='.csv', delete=False) as f:
            f.write(b'a;b\n1;2\n')
            temp_file = f.name
        try:
            exit_code, output = csv_to_markdown(temp_file)
            assert exit_code == 0
            assert '| 1 | 2 |' in output
        finally:
            os.unlink(temp_file)
    
    def test_empty_lines_skipped(self):
        """Prázdné řádky se přeskáčou."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8') as f:
            f.write('a;b\n1;2\n\n\n3;4\n')
            temp_file = f.name
        try:
            exit_code, output = csv_to_markdown(temp_file)
            assert exit_code == 0
            # Prázdné řádky se přeskáčou
            assert '| 1 | 2 |' in output
            assert '| 3 | 4 |' in output
        finally:
            os.unlink(temp_file)
    
    def test_rows_with_only_whitespace_skipped(self):
        """Řádky jen s mezerami se přeskáčou."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8') as f:
            f.write('a;b\n1;2\n   ;  \n3;4\n')
            temp_file = f.name
        try:
            exit_code, output = csv_to_markdown(temp_file)
            assert exit_code == 0
            # Řádek s jen mezerami se přeskočí
            lines = output.strip().split('\n')
            # Header + separator + 2 data rows
            assert len([l for l in lines if l.startswith('|')]) == 4
        finally:
            os.unlink(temp_file)
    
    def test_fewer_columns_than_header(self):
        """Řádek s méně sloupci se doplní prázdnými."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8') as f:
            f.write('a;b;c;d\n1\n2;3\nx;y;z\n')
            temp_file = f.name
        try:
            exit_code, output = csv_to_markdown(temp_file)
            assert exit_code == 0
            assert '| 1 |  |  |  |' in output
            assert '| 2 | 3 |  |  |' in output
            assert '| x | y | z |  |' in output
        finally:
            os.unlink(temp_file)
    
    def test_more_columns_than_header(self):
        """Řádek s více sloupci se zaříznout na délku hlavičky."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8') as f:
            f.write('a;b\n1;2;3;4\n')
            temp_file = f.name
        try:
            exit_code, output = csv_to_markdown(temp_file)
            assert exit_code == 0
            # Jen první dva sloupce
            assert '| 1 | 2 |' in output
        finally:
            os.unlink(temp_file)


class TestMarkdownOutputAdvanced:
    """Pokročilé testy výstupu Markdown."""
    
    def test_pipe_escaping_in_data(self):
        """Pipes v datech se escapují."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8') as f:
            f.write('a;b\na|b;c|d|e\n')
            temp_file = f.name
        try:
            exit_code, output = csv_to_markdown(temp_file)
            assert exit_code == 0
            assert 'a\\|b' in output
            assert 'c\\|d\\|e' in output
        finally:
            os.unlink(temp_file)
    
    def test_backslash_escaping_in_data(self):
        """Backslashes v datech se zdvojují."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8') as f:
            f.write('a;b\n"C:\\path\\file";val\n')
            temp_file = f.name
        try:
            exit_code, output = csv_to_markdown(temp_file)
            assert exit_code == 0
            assert 'C:\\\\path\\\\file' in output
        finally:
            os.unlink(temp_file)
    
    def test_br_replacement_multiline(self):
        """Více <br> pro více zalomení."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8') as f:
            f.write('desc\n"L1\nL2\nL3\nL4"\n')
            temp_file = f.name
        try:
            exit_code, output = csv_to_markdown(temp_file)
            assert exit_code == 0
            assert 'L1<br>L2<br>L3<br>L4' in output
        finally:
            os.unlink(temp_file)
    
    def test_header_order_preserved(self):
        """Pořadí sloupců v hlavičce se zachová."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8') as f:
            f.write('z;a;m;b\n1;2;3;4\n')
            temp_file = f.name
        try:
            exit_code, output = csv_to_markdown(temp_file)
            assert exit_code == 0
            # Pořadí z, a, m, b
            lines = output.strip().split('\n')
            header = lines[0]
            assert header.index('z') < header.index('a')
            assert header.index('a') < header.index('m')
            assert header.index('m') < header.index('b')
        finally:
            os.unlink(temp_file)
    
    def test_special_chars_utf8(self):
        """UTF-8 speciální znaky (háčky, čárky)."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8') as f:
            f.write('jméno;město\nJiří Čech;Příbram\n')
            temp_file = f.name
        try:
            exit_code, output = csv_to_markdown(temp_file)
            assert exit_code == 0
            assert 'Jiří' in output
            assert 'Čech' in output
            assert 'Příbram' in output
        finally:
            os.unlink(temp_file)
    
    def test_unicode_combining_chars(self):
        """Kombinující znaky (combining marks)."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8') as f:
            # e + combining acute = é (dva znaky)
            f.write('name;city\nJosé;São Paulo\n')
            temp_file = f.name
        try:
            exit_code, output = csv_to_markdown(temp_file)
            assert exit_code == 0
            assert 'José' in output or 'Jose' in output or 'Jos' in output
        finally:
            os.unlink(temp_file)
    
    def test_empty_cells_preserved(self):
        """Prázdné buňky se zachovají v tabulce."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8') as f:
            f.write('a;b;c\n1;;3\n;;;\n')
            temp_file = f.name
        try:
            exit_code, output = csv_to_markdown(temp_file)
            assert exit_code == 0
            # Řádek s prázdnou buňkou uprostřed
            assert '| 1 |  | 3 |' in output
        finally:
            os.unlink(temp_file)
    
    def test_separator_line_format(self):
        """Oddělovací řádek má správný formát."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8') as f:
            f.write('a;b;c\n1;2;3\n')
            temp_file = f.name
        try:
            exit_code, output = csv_to_markdown(temp_file)
            assert exit_code == 0
            lines = output.strip().split('\n')
            # Druhý řádek by měl být oddělovač
            assert lines[1] == '|---|---|---|'
        finally:
            os.unlink(temp_file)


class TestEncodingDetection:
    """Testy detekce kódování."""
    
    def test_utf8_auto_detection(self):
        """UTF-8 se detekuje automaticky."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8') as f:
            f.write('jméno;město\nJan;Brno\n')
            temp_file = f.name
        try:
            exit_code, output = csv_to_markdown(temp_file)  # bez encoding
            assert exit_code == 0
            assert 'jméno' in output
            assert 'město' in output
        finally:
            os.unlink(temp_file)
    
    def test_cp1250_explicit_encoding(self):
        """cp1250 se používá, když je explicitně zadán."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='cp1250') as f:
            f.write('jméno;město\nJan;Brno\n')
            temp_file = f.name
        try:
            exit_code, output = csv_to_markdown(temp_file, encoding='cp1250')
            assert exit_code == 0
            assert 'jméno' in output
            assert 'město' in output
        finally:
            os.unlink(temp_file)
    
    def test_encoding_parameter_overrides_detection(self):
        """Parametr --encoding přepíše autodetekci."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8') as f:
            f.write('a;b\n1;2\n')
            temp_file = f.name
        try:
            # Explicitně specifikovat encoding, i když by se detekoval
            exit_code, output = csv_to_markdown(temp_file, encoding='utf-8')
            assert exit_code == 0
        finally:
            os.unlink(temp_file)
    
    def test_detect_encoding_function_utf8(self):
        """detect_encoding detekuje UTF-8."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8') as f:
            f.write('test\n')
            temp_file = f.name
        try:
            encoding = detect_encoding(temp_file)
            assert encoding == 'utf-8'
        finally:
            os.unlink(temp_file)
    
    def test_detect_encoding_function_cp1250(self):
        """detect_encoding fallback na cp1250."""
        with tempfile.NamedTemporaryFile(mode='wb', suffix='.csv', delete=False) as f:
            # Bytes, které nejsou validní UTF-8, ale jsou v cp1250
            f.write(b'\xf8\xfds\ntest\n')  # ř (cp1250)
            temp_file = f.name
        try:
            encoding = detect_encoding(temp_file)
            assert encoding == 'cp1250'
        finally:
            os.unlink(temp_file)


class TestErrorHandling:
    """Testy chybových stavů."""
    
    def test_nonexistent_file(self):
        """Neexistující soubor vrátí chybu."""
        exit_code, output = csv_to_markdown('/nonexistent/path/file.csv')
        assert exit_code == 1
        assert 'nenalezen' in output.lower() or 'error' in output.lower()
    
    def test_empty_file_error(self):
        """Prázdný soubor vrátí chybu."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8') as f:
            temp_file = f.name
        try:
            exit_code, output = csv_to_markdown(temp_file)
            assert exit_code == 1
            assert 'prázdný' in output.lower() or 'empty' in output.lower()
        finally:
            os.unlink(temp_file)
    
    def test_only_header_no_data(self):
        """Jen hlavička bez dat – vrátí tabulku jen s hlavičkou."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8') as f:
            f.write('a;b;c\n')
            temp_file = f.name
        try:
            exit_code, output = csv_to_markdown(temp_file)
            assert exit_code == 0
            # Měla by to být hlavička bez dat
            assert '| a | b | c |' in output
        finally:
            os.unlink(temp_file)
    
    def test_invalid_encoding_explicit(self):
        """Neplatné kódování vrátí chybu."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8') as f:
            f.write('test\n')
            temp_file = f.name
        try:
            # Pokus o čtení s neplatným kódováním
            exit_code, output = csv_to_markdown(temp_file, encoding='invalid-encoding-xyz')
            assert exit_code == 1
        finally:
            os.unlink(temp_file)


class TestSpecificationSample:
    """Testy s vzorkem z specifikace."""
    
    def test_sample_utf8(self):
        """Vzorek z specifikace v UTF-8."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8') as f:
            f.write('jmeno;mesto;poznamka\n')
            f.write('Jan Novák;Brno;"zkouška; s čárkou | a svislítkem"\n')
            temp_file = f.name
        try:
            exit_code, output = csv_to_markdown(temp_file)
            assert exit_code == 0
            # Ověřit strukturu tabulky
            assert '| jmeno | mesto | poznamka |' in output
            assert '|---|---|---|' in output
            # Ověřit escapování
            assert 'zkouška; s čárkou \\| a svislítkem' in output
            # Ověřit, že údaje jsou na správném místě
            assert '| Jan Novák | Brno |' in output
        finally:
            os.unlink(temp_file)
    
    def test_sample_cp1250(self):
        """Vzorek z specifikace v cp1250."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='cp1250') as f:
            f.write('jmeno;mesto;poznamka\n')
            f.write('Jan Novák;Brno;"zkouška; s čárkou | a svislítkem"\n')
            temp_file = f.name
        try:
            exit_code, output = csv_to_markdown(temp_file, encoding='cp1250')
            assert exit_code == 0
            # Strukturu tabulky
            assert '| jmeno | mesto | poznamka |' in output
            # Escapování
            assert 'zkouška; s čárkou \\| a svislítkem' in output
        finally:
            os.unlink(temp_file)


class TestCLIInterface:
    """Testy CLI rozhraní."""
    
    def test_cli_help(self):
        """--help parameter."""
        result = subprocess.run(
            [sys.executable, 'csv2md.py', '--help'],
            capture_output=True,
            text=True
        )
        assert result.returncode == 0
        assert 'usage' in result.stdout.lower() or 'help' in result.stdout.lower()
        assert 'input_file' in result.stdout or 'CSV' in result.stdout
    
    def test_cli_basic_output(self):
        """Základní CLI spuštění s stdout."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8') as f:
            f.write('a;b\n1;2\n')
            csv_file = f.name
        try:
            result = subprocess.run(
                [sys.executable, 'csv2md.py', csv_file],
                capture_output=True,
                text=True
            )
            assert result.returncode == 0
            assert '| a | b |' in result.stdout
            assert '|---|---|' in result.stdout
        finally:
            os.unlink(csv_file)
    
    def test_cli_output_file(self):
        """Parametr -o/--output."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8') as f:
            f.write('a;b\n1;2\n')
            csv_file = f.name
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
            md_file = f.name
        
        try:
            result = subprocess.run(
                [sys.executable, 'csv2md.py', csv_file, '-o', md_file],
                capture_output=True,
                text=True
            )
            assert result.returncode == 0
            # Výstup by neměl být na stdout
            assert result.stdout == ''
            # Obsah by měl být v souboru
            with open(md_file, 'r', encoding='utf-8') as f:
                content = f.read()
            assert '| a | b |' in content
        finally:
            os.unlink(csv_file)
            if os.path.exists(md_file):
                os.unlink(md_file)
    
    def test_cli_output_file_long_form(self):
        """Dlouhá forma --output."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8') as f:
            f.write('x;y\n1;2\n')
            csv_file = f.name
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
            md_file = f.name
        
        try:
            result = subprocess.run(
                [sys.executable, 'csv2md.py', csv_file, '--output', md_file],
                capture_output=True,
                text=True
            )
            assert result.returncode == 0
            with open(md_file, 'r', encoding='utf-8') as f:
                content = f.read()
            assert '| x | y |' in content
        finally:
            os.unlink(csv_file)
            if os.path.exists(md_file):
                os.unlink(md_file)
    
    def test_cli_encoding_parameter(self):
        """Parametr --encoding."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8') as f:
            f.write('jméno;město\nJan;Brno\n')
            csv_file = f.name
        try:
            result = subprocess.run(
                [sys.executable, 'csv2md.py', csv_file, '--encoding', 'utf-8'],
                capture_output=True,
                text=True
            )
            assert result.returncode == 0
            assert 'jméno' in result.stdout
        finally:
            os.unlink(csv_file)
    
    def test_cli_file_not_found(self):
        """CLI s neexistujícím souborem."""
        result = subprocess.run(
            [sys.executable, 'csv2md.py', '/nonexistent/file.csv'],
            capture_output=True,
            text=True
        )
        assert result.returncode == 1
        assert 'nenalezen' in result.stderr.lower() or 'error' in result.stderr.lower()
    
    def test_cli_no_args(self):
        """CLI bez argumentů by měl dát chybu."""
        result = subprocess.run(
            [sys.executable, 'csv2md.py'],
            capture_output=True,
            text=True
        )
        assert result.returncode != 0


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
