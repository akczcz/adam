"""
Jednotkové testy pro csv2md core module
"""
import pytest
import tempfile
import os
from csv2md import read_csv, escape_markdown_cell, csv_to_markdown


class TestEscapeMarkdownCell:
    """Testy pro escape_markdown_cell"""
    
    def test_escape_pipe(self):
        assert escape_markdown_cell("a|b") == "a\\|b"
    
    def test_escape_backslash(self):
        assert escape_markdown_cell("a\\b") == "a\\\\b"
    
    def test_escape_both(self):
        assert escape_markdown_cell("a|b\\c") == "a\\|b\\\\c"
    
    def test_newline_to_br(self):
        assert escape_markdown_cell("a\nb") == "a<br>b"
    
    def test_carriage_return_removed(self):
        assert escape_markdown_cell("a\rb") == "ab"
    
    def test_combined_escape_and_br(self):
        assert escape_markdown_cell("a|b\nc\\d") == "a\\|b<br>c\\\\d"
    
    def test_empty_string(self):
        assert escape_markdown_cell("") == ""
    
    def test_none_value(self):
        assert escape_markdown_cell(None) == ""


class TestReadCsv:
    """Testy pro read_csv"""
    
    def test_read_simple_csv_utf8(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', encoding='utf-8', delete=False) as f:
            f.write("jméno;věk\nAlice;30\nBob;25\n")
            f.flush()
            filepath = f.name
        
        try:
            rows = read_csv(filepath)
            assert len(rows) == 2
            assert rows[0]['jméno'] == 'Alice'
            assert rows[0]['věk'] == '30'
            assert rows[1]['jméno'] == 'Bob'
        finally:
            os.unlink(filepath)
    
    def test_read_csv_with_quoted_values(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', encoding='utf-8', delete=False) as f:
            f.write('jméno;popis\n"Alice";"má rád pizza"\nBob;"nemá rád"\n')
            f.flush()
            filepath = f.name
        
        try:
            rows = read_csv(filepath)
            assert len(rows) == 2
            assert rows[0]['jméno'] == 'Alice'
            assert rows[0]['popis'] == 'má rád pizza'
        finally:
            os.unlink(filepath)
    
    def test_read_csv_with_escaped_quotes(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', encoding='utf-8', delete=False) as f:
            f.write('jméno;text\n"Alice";"řekl ""ahoj"""\n')
            f.flush()
            filepath = f.name
        
        try:
            rows = read_csv(filepath)
            assert len(rows) == 1
            assert rows[0]['text'] == 'řekl "ahoj"'
        finally:
            os.unlink(filepath)
    
    def test_read_csv_with_pipe_and_backslash(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', encoding='utf-8', delete=False) as f:
            f.write('id;obsah\n1;"a|b\\c"\n')
            f.flush()
            filepath = f.name
        
        try:
            rows = read_csv(filepath)
            assert len(rows) == 1
            assert rows[0]['obsah'] == 'a|b\\c'
        finally:
            os.unlink(filepath)
    
    def test_read_csv_windows1250(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', encoding='windows-1250', delete=False) as f:
            f.write("jméno;věk\nAlice;30\nBob;25\n")
            f.flush()
            filepath = f.name
        
        try:
            rows = read_csv(filepath, encoding='windows-1250')
            assert len(rows) == 2
            assert rows[0]['jméno'] == 'Alice'
        finally:
            os.unlink(filepath)
    
    def test_read_csv_fallback_utf8_to_windows1250(self):
        # Vytvoř soubor v Windows-1250 (bez explicitního encoding parametru)
        with tempfile.NamedTemporaryFile(mode='wb', suffix='.csv', delete=False) as f:
            # "příliš" v windows-1250
            content = "jméno;věc\nAlice;příliš\n".encode('windows-1250')
            f.write(content)
            f.flush()
            filepath = f.name
        
        try:
            rows = read_csv(filepath)  # Bez explicitního kódování, mělo by fallback
            assert len(rows) == 1
            assert 'Alice' in rows[0]['jméno']
        finally:
            os.unlink(filepath)
    
    def test_read_csv_file_not_found(self):
        with pytest.raises(FileNotFoundError):
            read_csv("/neexistující/cesta/soubor.csv")
    
    def test_read_csv_empty_file(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', encoding='utf-8', delete=False) as f:
            f.write("")
            f.flush()
            filepath = f.name
        
        try:
            with pytest.raises(ValueError, match="nemá hlavičku nebo je prázdný"):
                read_csv(filepath)
        finally:
            os.unlink(filepath)


class TestCsvToMarkdown:
    """Testy pro csv_to_markdown"""
    
    def test_simple_table(self):
        rows = [
            {'jméno': 'Alice', 'věk': '30'},
            {'jméno': 'Bob', 'věk': '25'}
        ]
        md = csv_to_markdown(rows)
        
        assert '| jméno | věk |' in md
        assert '| Alice | 30 |' in md
        assert '| Bob | 25 |' in md
        assert '|---|---|' in md or '|---|---|' in md.replace(' ', '')
    
    def test_table_with_escaped_values(self):
        rows = [
            {'col1': 'a|b', 'col2': 'c\\d'}
        ]
        md = csv_to_markdown(rows)
        
        # Po escapování
        assert 'a\\|b' in md
        assert 'c\\\\d' in md
    
    def test_table_with_newlines(self):
        rows = [
            {'col1': 'line1\nline2', 'col2': 'x'}
        ]
        md = csv_to_markdown(rows)
        
        assert 'line1<br>line2' in md
    
    def test_table_with_empty_cells(self):
        rows = [
            {'col1': 'a', 'col2': ''},
            {'col1': '', 'col2': 'b'}
        ]
        md = csv_to_markdown(rows)
        
        # Prázdné buňky zůstávají prázdné
        assert '| a |  |' in md or '| a ||' in md
    
    def test_empty_rows_list(self):
        with pytest.raises(ValueError, match="prázdný"):
            csv_to_markdown([])
    
    def test_many_columns(self):
        rows = [
            {'c1': '1', 'c2': '2', 'c3': '3', 'c4': '4', 'c5': '5'}
        ]
        md = csv_to_markdown(rows)
        
        # Měla by být tabulka s 5 sloupci
        lines = md.split('\n')
        assert len(lines[0].split('|')) == 7  # 5 sloupců + 2 prázdné (na začátku a konci)


class TestIntegration:
    """Integrační testy - end-to-end"""
    
    def test_full_workflow_utf8(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', encoding='utf-8', delete=False) as f:
            f.write('jméno;věc;popis\n')
            f.write('Alice;test|1;"řádek1\nřádek2"\n')
            f.write('Bob;back\\slash;""\n')
            f.flush()
            filepath = f.name
        
        try:
            rows = read_csv(filepath)
            assert len(rows) == 2
            md = csv_to_markdown(rows)
            
            # Ověř, že je tabulka správně escapovaná
            assert 'test\\|1' in md
            assert 'back\\\\slash' in md
            assert 'řádek1<br>řádek2' in md
        finally:
            os.unlink(filepath)
    
    def test_full_workflow_windows1250(self):
        with tempfile.NamedTemporaryFile(mode='wb', suffix='.csv', delete=False) as f:
            # Vytvoř CSV v windows-1250
            content = "jméno;obsah\nAlicka;příliš\n".encode('windows-1250')
            f.write(content)
            f.flush()
            filepath = f.name
        
        try:
            rows = read_csv(filepath, encoding='windows-1250')
            md = csv_to_markdown(rows)
            assert len(rows) == 1
            assert 'Alicka' in md
        finally:
            os.unlink(filepath)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
