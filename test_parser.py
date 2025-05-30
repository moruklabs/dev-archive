#!/usr/bin/env python3

"""
Simple test for the HTML to YAML parsing functionality
"""

import os
import tempfile
import yaml
from parse_html_to_yaml import parse_html_content, extract_metadata_from_path, process_html_file


def test_parse_html_content():
    """Test basic HTML parsing functionality"""
    sample_html = '''
    <html>
        <head><title>Test Page</title></head>
        <body>
            <h1>Hello World</h1>
            <p>This is a test paragraph with <a href="https://example.com">a link</a>.</p>
            <ul>
                <li>Item 1</li>
                <li>Item 2</li>
            </ul>
        </body>
    </html>
    '''
    
    result = parse_html_content(sample_html)
    
    assert result['success'] == True, "Parsing should succeed"
    assert result['markdown'] is not None, "Markdown content should be generated"
    assert result['clean_html'] is not None, "Clean HTML should be generated"
    assert result['content_info'] is not None, "Content info should be generated"
    assert result['content_info']['has_headers'] == True, "Should detect headers"
    assert result['content_info']['has_links'] == False, "purehtml strips href attributes in default mode"
    
    print("✓ parse_html_content test passed")


def test_extract_metadata_from_path():
    """Test metadata extraction from file paths"""
    test_cases = [
        ('captures/capture/2025-05-30/hackernews/home.html', {
            'capture_date': '2025-05-30',
            'source_type': 'hackernews'
        }),
        ('captures/capture/2025-05-30/gh/trending/daily/python-trending.html', {
            'capture_date': '2025-05-30',
            'source_type': 'gh',
            'gh_section': 'trending',
            'gh_subsection': 'daily'
        }),
        ('captures/capture/2025-05-30/ph/home.html', {
            'capture_date': '2025-05-30',
            'source_type': 'ph'
        })
    ]
    
    for path, expected in test_cases:
        metadata = extract_metadata_from_path(path)
        
        for key, value in expected.items():
            assert metadata.get(key) == value, f"Expected {key}={value} for path {path}, got {metadata.get(key)}"
    
    print("✓ extract_metadata_from_path test passed")


def test_process_html_file():
    """Test full file processing workflow"""
    sample_html = '''
    <html>
        <head><title>Test Document</title></head>
        <body>
            <h1>Test Content</h1>
            <p>This is test content for parsing.</p>
        </body>
    </html>
    '''
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False) as input_file:
        input_file.write(sample_html)
        input_path = input_file.name
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as output_file:
        output_path = output_file.name
    
    try:
        # Process the file
        success, error = process_html_file(input_path, output_path)
        
        assert success == True, f"Processing should succeed, got error: {error}"
        assert os.path.exists(output_path), "Output file should be created"
        
        # Load and validate YAML output
        with open(output_path, 'r') as f:
            data = yaml.safe_load(f)
        
        assert 'metadata' in data, "YAML should contain metadata"
        assert 'parsing' in data, "YAML should contain parsing info"
        assert 'content' in data, "YAML should contain content"
        assert data['parsing']['success'] == True, "Parsing should be successful"
        assert data['content']['markdown'] is not None, "Should contain markdown content"
        
        print("✓ process_html_file test passed")
        
    finally:
        # Clean up temp files
        os.unlink(input_path)
        if os.path.exists(output_path):
            os.unlink(output_path)


def main():
    """Run all tests"""
    print("Running HTML to YAML parser tests...")
    
    test_parse_html_content()
    test_extract_metadata_from_path()
    test_process_html_file()
    
    print("\n✓ All tests passed!")


if __name__ == '__main__':
    main()