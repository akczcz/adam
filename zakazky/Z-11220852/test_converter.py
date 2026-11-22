"""Unit tests for CSV to Markdown converter."""
import pytest
import os
from converter import CSVToMarkdownConverter, convert_csv_to_markdown


class TestEscapeMarkdown:
    """Test Markdown escaping function."""
    
    def test_escape_pipe(self):
        """Test pipe character escaping."""
        converter = CSVToMarkdownConverter()
        assert converter._escape_markdown("a|b") == "a\\|b"
    
    def test_escape_backslash(self):
        """Test backslash escaping."""
        converter = CSVToMarkdownConverter()
        assert converter._escape_markdown("a\\b") == "a\\\\b"
    
    def test_escape_newline(self):
        """Test newline replacement."""
        converter = CSVToMarkdownConverter()
        assert converter._escape_markdown("line1\nline2") == "line1 line2"
    
    def test_escape_multiple(self):
        """Test multiple special characters."""
        converter = CSVToMarkdownConverter()
        result = converter._escape_markdown("a|b\\c\nd")
        # Should have escaped pipe and backslash, newline as space
        assert "\\|" in result
        assert "\n" not in result
    
    def test_whitespace_trim(self):
        """Test leading/trailing whitespace trimming."""
        converter = CSVToMarkdownConverter()
        assert converter._escape_markdown("  hello  ") == "hello"


class TestCSVToMarkdown:
    """Test CSV to Markdown conversion."""
    
    def test_basic_csv(self):
        """Test conversion of basic CSV."""
        converter = CSVToMarkdownConverter()
        csv_content = "Name,Age\nJohn,28\nJane,34"
        success, markdown, error = converter.csv_to_markdown(csv_content)
        
        assert success
        assert "| Name | Age |" in markdown
        assert "| John | 28 |" in markdown
        assert "| Jane | 34 |" in markdown
        assert "---" in markdown
    
    def test_csv_with_special_chars(self):
        """Test CSV with special characters."""
        converter = CSVToMarkdownConverter()
        csv_content = "Title,Content\n\"Test | pipe\",\"Backslash \\\""
        success, markdown, error = converter.csv_to_markdown(csv_content)
        
        assert success
        assert "\\|" in markdown
        assert "\\\\" in markdown
    
    def test_csv_with_newlines(self):
        """Test CSV with newlines in cells."""
        converter = CSVToMarkdownConverter()
        csv_content = "Name,Description\nJohn,\"Multi\nLine\""
        success, markdown, error = converter.csv_to_markdown(csv_content)
        
        assert success
        # Newlines should be replaced with spaces
        lines = markdown.split('\n')
        # Last line should not have embedded newlines (only the split ones)
        for line in lines:
            if 'Multi' in line:
                assert "Multi Line" in line
    
    def test_csv_with_empty_cells(self):
        """Test CSV with empty cells."""
        converter = CSVToMarkdownConverter()
        csv_content = "Name,Middle,Last\nJohn,,Doe\nJane,Marie,Smith"
        success, markdown, error = converter.csv_to_markdown(csv_content)
        
        assert success
        assert "| John |  | Doe |" in markdown
    
    def test_empty_csv(self):
        """Test error handling for empty CSV."""
        converter = CSVToMarkdownConverter()
        success, markdown, error = converter.csv_to_markdown("")
        
        assert not success
        assert "empty" in error.lower()
    
    def test_delimiter_semicolon(self):
        """Test semicolon delimiter."""
        converter = CSVToMarkdownConverter(delimiter=';')
        csv_content = "Name;Age\nJohn;28"
        success, markdown, error = converter.csv_to_markdown(csv_content)
        
        assert success
        assert "| Name | Age |" in markdown
    
    def test_invalid_delimiter(self):
        """Test error handling for invalid delimiter."""
        with pytest.raises(ValueError):
            CSVToMarkdownConverter(delimiter='|')


class TestFileConversion:
    """Test file-based conversion."""
    
    def test_convert_sample1(self):
        """Test sample1.csv conversion."""
        converter = CSVToMarkdownConverter()
        success, markdown, error = converter.convert_file('test_samples/sample1.csv')
        
        assert success
        assert "| Name | Age | City | Occupation |" in markdown
        assert "| John Doe | 28 | New York | Engineer |" in markdown
    
    def test_convert_sample2(self):
        """Test sample2.csv with special characters."""
        converter = CSVToMarkdownConverter()
        success, markdown, error = converter.convert_file('test_samples/sample2.csv')
        
        assert success
        assert "\\|" in markdown
    
    def test_convert_sample3(self):
        """Test sample3.csv with empty cells."""
        converter = CSVToMarkdownConverter()
        success, markdown, error = converter.convert_file('test_samples/sample3.csv')
        
        assert success
        assert "|  |" in markdown  # Empty cells
    
    def test_file_not_found(self):
        """Test error handling for missing file."""
        converter = CSVToMarkdownConverter()
        success, markdown, error = converter.convert_file('nonexistent.csv')
        
        assert not success
        assert "not found" in error.lower()


class TestHighLevelFunction:
    """Test high-level conversion function."""
    
    def test_success_response(self):
        """Test successful conversion response format."""
        result = convert_csv_to_markdown('test_samples/sample1.csv')
        
        assert result['status'] == 'ok'
        assert 'message' in result
        assert 'data' in result
        assert 'markdown' in result['data']
    
    def test_error_response(self):
        """Test error response format."""
        result = convert_csv_to_markdown('nonexistent.csv')
        
        assert result['status'] == 'error'
        assert 'message' in result
        assert 'data' in result
    
    def test_delimiter_parameter(self):
        """Test delimiter parameter passing."""
        result = convert_csv_to_markdown(
            'test_samples/sample1.csv',
            delimiter=','
        )
        
        assert result['status'] == 'ok'


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
