"""Testy pro csv2md.py"""
import pytest
import tempfile
import os
from pathlib import Path
from csv2md import csv_to_markdown, escape_markdown


class TestEscapeMarkdown:
    """Testy escapování znaků."""
    
    def test_escape_backslash(self):
        """Backslash se zdvojuje."""
        assert escape_markdown('a\\b') == 'a\\\\b'
    
    def test_escape_pipe(self):
        """Pipe se escapuje."""
        assert escape_markdown('a|b') == 'a\\|b'
    
    def test_escape_newline(self):
        """Newline se změní na <br>."""
        assert escape_markdown('a\nb') == 'a<br>b'
    
    def test_escape_carriage_return(self):
        """Carriage return se odstranuje."""
        assert escape_markdown('a\rb') == 'ab'
    
    def test_escape_combined(self):
        """Kombinované escapování."""
        result = escape_markdown('a\\b|c\nd')
        assert result == 'a\\\\b\\|c<br>d'


class TestCSVToMarkdown:
    """Testy konverze CSV na Markdown."""
    
    def test_simple_csv(self):
        """Jednoduchou CSV konvertuje na tabulku."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8') as f:
            f.write('jmeno;mesto\nJan;Brno\nFranta;Praha\n')
            temp_file = f.name
        
        try:
            exit_code, output = csv_to_markdown(temp_file)
            assert exit_code == 0
            assert '| jmeno | mesto |' in output
            assert '|---|---|' in output
            assert '| Jan | Brno |' in output
            assert '| Franta | Praha |' in output
        finally:
            os.unlink(temp_file)
    
    def test_escape_in_csv(self):
        """Escapování znaků v CSV buňkách."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8') as f:
            f.write('jmeno;poznamka\n"Jan";"a|b\\c"\n')
            temp_file = f.name
        
        try:
            exit_code, output = csv_to_markdown(temp_file)
            assert exit_code == 0
            assert 'a\\|b\\\\c' in output
        finally:
            os.unlink(temp_file)
    
    def test_newline_in_csv(self):
        """Zalomení řádku se změní na <br>."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8') as f:
            f.write('jmeno;poznamka\n"Jan";"řádek1\nřádek2"\n')
            temp_file = f.name
        
        try:
            exit_code, output = csv_to_markdown(temp_file)
            assert exit_code == 0
            assert 'řádek1<br>řádek2' in output
        finally:
            os.unlink(temp_file)
    
    def test_sample_from_spec(self):
        """Vzorek z specifikace."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8') as f:
            f.write('jmeno;mesto;poznamka\nJan Novák;Brno;"zkouška; s čárkou | a svislítkem"\n')
            temp_file = f.name
        
        try:
            exit_code, output = csv_to_markdown(temp_file)
            assert exit_code == 0
            assert '| jmeno | mesto | poznamka |' in output
            assert '|---|---|---|' in output
            assert 'zkouška; s čárkou \\| a svislítkem' in output
        finally:
            os.unlink(temp_file)
    
    def test_empty_cells(self):
        """Prázdné buňky zůstávají prázdné."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8') as f:
            f.write('a;b;c\n1;;3\n;;;\n')
            temp_file = f.name
        
        try:
            exit_code, output = csv_to_markdown(temp_file)
            assert exit_code == 0
            assert '| 1 |  | 3 |' in output
        finally:
            os.unlink(temp_file)
    
    def test_fewer_columns(self):
        """Řádky s méně sloupci se doplní prázdnými buňkami."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8') as f:
            f.write('a;b;c\n1;2\n3\n')
            temp_file = f.name
        
        try:
            exit_code, output = csv_to_markdown(temp_file)
            assert exit_code == 0
            assert '| 1 | 2 |  |' in output
            assert '| 3 |  |  |' in output
        finally:
            os.unlink(temp_file)
    
    def test_file_not_found(self):
        """Neexistující soubor vrátí chybu."""
        exit_code, output = csv_to_markdown('/nonexistent/file.csv')
        assert exit_code == 1
        assert 'nenalezen' in output.lower()
    
    def test_empty_file(self):
        """Prázdný soubor vrátí chybu."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8') as f:
            temp_file = f.name
        
        try:
            exit_code, output = csv_to_markdown(temp_file)
            assert exit_code == 1
            assert 'prázdný' in output.lower()
        finally:
            os.unlink(temp_file)
    
    def test_output_file(self):
        """Výstup se zapíše do souboru."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8') as f:
            f.write('a;b\n1;2\n')
            csv_file = f.name
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
            md_file = f.name
        
        try:
            exit_code, output = csv_to_markdown(csv_file, output_file=md_file)
            assert exit_code == 0
            
            with open(md_file, 'r', encoding='utf-8') as f:
                content = f.read()
            assert '| a | b |' in content
        finally:
            os.unlink(csv_file)
            os.unlink(md_file)
    
    def test_utf8_encoding(self):
        """UTF-8 kódování se správně detekuje."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8') as f:
            f.write('jméno;město\nJan;Brno\n')
            temp_file = f.name
        
        try:
            exit_code, output = csv_to_markdown(temp_file)
            assert exit_code == 0
            assert 'jméno' in output
            assert 'město' in output
        finally:
            os.unlink(temp_file)
    
    def test_cp1250_encoding(self):
        """cp1250 kódování se detekuje a používá."""
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


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
