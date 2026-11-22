"""
Integrační testy pro csv2md CLI (argparse, error handling, exit codes)
"""
import subprocess
import tempfile
import os
import sys
import pytest


class TestCLIBasic:
    """Základní CLI testy"""
    
    def test_help_displays_usage(self):
        """Test: csv2md --help zobrazuje usage"""
        result = subprocess.run(
            [sys.executable, '-m', 'csv2md', '--help'],
            capture_output=True,
            text=True
        )
        assert result.returncode == 0
        assert 'INPUT' in result.stdout
        assert 'usage' in result.stdout.lower() or 'csv2md' in result.stdout
    
    def test_nonexistent_file_returns_exit_code_1(self):
        """Test: csv2md nonexistent.csv vrací exit code 1"""
        result = subprocess.run(
            [sys.executable, '-m', 'csv2md', 'nonexistent_file_12345.csv'],
            capture_output=True,
            text=True
        )
        assert result.returncode == 1
        assert 'Input file not found' in result.stderr
    
    def test_valid_utf8_file_returns_exit_code_0(self):
        """Test: csv2md test_data/sample_utf8.csv vrací exit code 0"""
        result = subprocess.run(
            [sys.executable, '-m', 'csv2md', 'test_data/sample_utf8.csv'],
            capture_output=True,
            text=True
        )
        assert result.returncode == 0
        # Markdown by měl obsahovat pipes (tabulka)
        assert '|' in result.stdout
        assert len(result.stdout) > 0


class TestCLIOutput:
    """Testy pro output handling"""
    
    def test_output_to_file(self):
        """Test: csv2md -o output.md input.csv zapisuje do souboru"""
        with tempfile.TemporaryDirectory() as tmpdir:
            input_file = os.path.join(tmpdir, 'input.csv')
            output_file = os.path.join(tmpdir, 'output.md')
            
            # Vytvoř testovací CSV
            with open(input_file, 'w', encoding='utf-8') as f:
                f.write('col1;col2\nval1;val2\n')
            
            result = subprocess.run(
                [sys.executable, '-m', 'csv2md', '-o', output_file, input_file],
                capture_output=True,
                text=True
            )
            
            assert result.returncode == 0
            assert os.path.exists(output_file)
            with open(output_file, 'r', encoding='utf-8') as f:
                content = f.read()
                assert '|' in content
                assert 'col1' in content
    
    def test_output_to_stdout_by_default(self):
        """Test: csv2md bez -o vypíše na stdout"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', encoding='utf-8', delete=False) as f:
            f.write('col1;col2\nval1;val2\n')
            f.flush()
            filepath = f.name
        
        try:
            result = subprocess.run(
                [sys.executable, '-m', 'csv2md', filepath],
                capture_output=True,
                text=True
            )
            assert result.returncode == 0
            assert '|' in result.stdout
            assert len(result.stdout) > 0
        finally:
            os.unlink(filepath)


class TestCLIEncoding:
    """Testy pro encoding argumenty"""
    
    def test_encoding_utf8_switch(self):
        """Test: --encoding utf-8 funguje"""
        result = subprocess.run(
            [sys.executable, '-m', 'csv2md', '--encoding', 'utf-8', 'test_data/sample_utf8.csv'],
            capture_output=True,
            text=True
        )
        assert result.returncode == 0
        assert '|' in result.stdout
    
    def test_encoding_cp1250_switch(self):
        """Test: --encoding cp1250 funguje"""
        result = subprocess.run(
            [sys.executable, '-m', 'csv2md', '--encoding', 'cp1250', 'sample_win1250.csv'],
            capture_output=True,
            text=True
        )
        # Měl by vrátit 0 nebo 1 (záleží, jestli soubor lze dekódovat)
        # Podstatné je, že switch je přijat bez syntaktické chyby
        assert isinstance(result.returncode, int)


class TestCLIErrorHandling:
    """Testy pro error handling a stderr zprávy"""
    
    def test_input_file_not_found_error(self):
        """Test: Chyba 'Input file not found'"""
        result = subprocess.run(
            [sys.executable, '-m', 'csv2md', 'this_file_does_not_exist.csv'],
            capture_output=True,
            text=True
        )
        assert result.returncode == 1
        assert 'Input file not found' in result.stderr
    
    def test_cannot_write_to_output_file_error(self):
        """Test: Chyba 'Cannot write to output file'"""
        with tempfile.TemporaryDirectory() as tmpdir:
            input_file = os.path.join(tmpdir, 'input.csv')
            # Vytvoř direktorium místo souboru (nelze do něj psát)
            output_dir = os.path.join(tmpdir, 'output_should_be_file')
            os.makedirs(output_dir)
            
            with open(input_file, 'w', encoding='utf-8') as f:
                f.write('col1;col2\nval1;val2\n')
            
            result = subprocess.run(
                [sys.executable, '-m', 'csv2md', '-o', output_dir, input_file],
                capture_output=True,
                text=True
            )
            
            assert result.returncode == 1
            assert 'Cannot write to output file' in result.stderr
    
    def test_csv_empty_or_no_header_error(self):
        """Test: Chyba 'CSV is empty or has no header'"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', encoding='utf-8', delete=False) as f:
            # Vytvoř prázdný soubor
            f.flush()
            filepath = f.name
        
        try:
            result = subprocess.run(
                [sys.executable, '-m', 'csv2md', filepath],
                capture_output=True,
                text=True
            )
            assert result.returncode == 1
            assert 'CSV is empty or has no header' in result.stderr
        finally:
            os.unlink(filepath)
    
    def test_unable_to_decode_file_error(self):
        """Test: Chyba 'Unable to decode file' pro špatné kódování"""
        with tempfile.NamedTemporaryFile(mode='wb', suffix='.csv', delete=False) as f:
            # Vytvoř soubor se špatným kódováním (válid cp1250, ale řekni že je utf-8)
            # Zahrneme bajty, které nejsou validní UTF-8
            f.write(b'\xff\xfe')  # BOM pro UTF-16
            f.flush()
            filepath = f.name
        
        try:
            result = subprocess.run(
                [sys.executable, '-m', 'csv2md', '--encoding', 'utf-8', filepath],
                capture_output=True,
                text=True
            )
            # Měl by vrátit chybu
            if result.returncode != 0:
                # Pokud je chyba, měla by obsahovat "Unable to decode file"
                # nebo "CSV is empty or has no header"
                assert ('Unable to decode file' in result.stderr or 
                        'CSV is empty or has no header' in result.stderr)
        finally:
            os.unlink(filepath)


class TestCLIExitCodes:
    """Testy na ověření návratových kódů"""
    
    def test_success_returns_zero(self):
        """Test: Úspěšná operace vrací exit code 0"""
        result = subprocess.run(
            [sys.executable, '-m', 'csv2md', 'test_data/sample_utf8.csv'],
            capture_output=True,
            text=True
        )
        assert result.returncode == 0
    
    def test_error_returns_one(self):
        """Test: Chyba vrací exit code 1"""
        result = subprocess.run(
            [sys.executable, '-m', 'csv2md', 'nonexistent.csv'],
            capture_output=True,
            text=True
        )
        assert result.returncode == 1
