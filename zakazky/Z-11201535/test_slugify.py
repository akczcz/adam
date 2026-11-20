"""
Testy pro modul slugify.
"""

import pytest
from slugify import slugify


class TestSlugify:
    """Testy funkce slugify."""
    
    def test_empty_string(self):
        """Test prázdného vstupu."""
        assert slugify("") == ""
    
    def test_simple_text_lowercase(self):
        """Test jednoduchého textu se převodem na malá písmena."""
        assert slugify("Hello World") == "hello-world"
    
    def test_czech_diacritics(self):
        """Test češtiny s diakritikou."""
        assert slugify("Příliš žluťoučký kůň") == "prilis-zlutoucky-kun"
    
    def test_czech_chars_another(self):
        """Test dalších českých znaků s diakritikou."""
        assert slugify("Řeší ščenka") == "resi-scenka"
    
    def test_multiple_spaces(self):
        """Test více mezer za sebou."""
        assert slugify("Hello   World") == "hello-world"
    
    def test_special_characters(self):
        """Test speciálních znaků."""
        assert slugify("Hello! @World? #2024") == "hello-world-2024"
    
    def test_leading_trailing_dashes(self):
        """Test odstranění pomlček na okrajích."""
        assert slugify("-Hello-World-") == "hello-world"
    
    def test_repeated_dashes(self):
        """Test odstranění opakovaných pomlček."""
        assert slugify("Hello--World") == "hello-world"
        assert slugify("Test---case") == "test-case"
    
    def test_mixed_case_with_diacritics(self):
        """Test kombinace velkých písmen a diakritiky."""
        assert slugify("PŘÍLIŠ ŽLUŤOUČKÝ") == "prilis-zlutoucky"
    
    def test_numbers_preserved(self):
        """Test zachování číslic."""
        assert slugify("Test 123 Case") == "test-123-case"
    
    def test_underscores(self):
        """Test konverze podtržítek na pomlčky."""
        assert slugify("test_case_name") == "test-case-name"
    
    def test_only_special_chars(self):
        """Test vstupu jen se speciálními znaky."""
        assert slugify("!@#$%^&*()") == ""
    
    def test_whitespace_only(self):
        """Test vstupu jen s mezerami."""
        assert slugify("   ") == ""
    
    def test_mixed_separators(self):
        """Test různých oddělovačů."""
        assert slugify("Hello-_-World") == "hello-world"
    
    def test_unicode_normalization(self):
        """Test normalizace unicode znaků."""
        # Kombinovaný e s háčkem vs. jednotný e s háčkem
        assert slugify("café") == "cafe"
        assert slugify("naïve") == "naive"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
