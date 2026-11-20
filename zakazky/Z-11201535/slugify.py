"""
Modul pro konverzi textu na slug (URL-friendly formát).

Slugify funkce:
- Převádí na malá písmena
- Odstraňuje diakritiku
- Nahrazuje mezery a nealfanumerické znaky pomlčkami
- Odstraňuje opakované a krajní pomlčky
"""

import unicodedata


def slugify(text: str) -> str:
    """
    Konvertuje text na slug.
    
    Args:
        text: Vstupní text
        
    Returns:
        Slug (malá písmena, bez diakritiky, znaky odděleny pomlčkami)
        
    Examples:
        >>> slugify("Příliš žluťoučký kůň")
        'prilis-zlutoucky-kun'
        >>> slugify("Hello  World!")
        'hello-world'
        >>> slugify("")
        ''
    """
    if not text:
        return ""
    
    # Normalizace a odstranění diakritiky
    # NFD normalizace rozloží znaky s diakritikou na základní znak + diakritiku
    text = unicodedata.normalize('NFD', text)
    # Filtrujeme pouze základní znaky (bez kombinujících znaků - kategorii Mn)
    text = ''.join(char for char in text if unicodedata.category(char) != 'Mn')
    
    # Převod na malá písmena
    text = text.lower()
    
    # Nahrazení mezer a nealfanumerických znaků (mimo pomlčky a podtržítka) pomlčkou
    result = []
    for char in text:
        if char.isalnum():
            result.append(char)
        elif char in (' ', '-', '_'):
            # Mezery, pomlčky a podtržítka nahradíme pomlčkou
            result.append('-')
        # Ostatní znaky ignorujeme
    
    text = ''.join(result)
    
    # Odstranění opakovaných pomlček
    while '--' in text:
        text = text.replace('--', '-')
    
    # Odstranění krajních pomlček
    text = text.strip('-')
    
    return text
