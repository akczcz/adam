"""
pytest configuration a shared fixtures pro csv2md testy
"""
import pytest
import tempfile
import os


@pytest.fixture
def temp_csv_utf8():
    """Vytvoří dočasný CSV soubor v UTF-8 s testovacími daty"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', encoding='utf-8', delete=False) as f:
        f.write('jméno;věk;město\n')
        f.write('Alice;30;Praha\n')
        f.write('Bob;25;Brno\n')
        f.flush()
        filepath = f.name
    
    yield filepath
    
    # Cleanup
    if os.path.exists(filepath):
        os.unlink(filepath)


@pytest.fixture
def temp_csv_cp1250():
    """Vytvoří dočasný CSV soubor v CP1250 s testovacími daty"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', encoding='cp1250', delete=False) as f:
        f.write('jméno;věc\n')
        f.write('Alice;příliš\n')
        f.flush()
        filepath = f.name
    
    yield filepath
    
    # Cleanup
    if os.path.exists(filepath):
        os.unlink(filepath)


@pytest.fixture
def temp_csv_with_special_chars():
    """CSV soubor s |, \\, uvozovkami a newlines"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', encoding='utf-8', delete=False) as f:
        f.write('id;obsah;popis\n')
        f.write('1;"a|b";"pipe v obsahu"\n')
        f.write('2;"c\\\\d";"backslash v obsahu"\n')
        f.write('3;"line1\\nline2";"newline v buňce"\n')
        f.write('4;"";"prázdný obsah"\n')
        f.flush()
        filepath = f.name
    
    yield filepath
    
    # Cleanup
    if os.path.exists(filepath):
        os.unlink(filepath)


@pytest.fixture
def temp_empty_csv():
    """Vytvoří prázdný CSV soubor"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', encoding='utf-8', delete=False) as f:
        f.flush()
        filepath = f.name
    
    yield filepath
    
    # Cleanup
    if os.path.exists(filepath):
        os.unlink(filepath)


@pytest.fixture
def temp_csv_no_data():
    """Vytvoří CSV soubor jen s hlavičkou (bez datových řádků)"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', encoding='utf-8', delete=False) as f:
        f.write('col1;col2;col3\n')
        f.flush()
        filepath = f.name
    
    yield filepath
    
    # Cleanup
    if os.path.exists(filepath):
        os.unlink(filepath)
