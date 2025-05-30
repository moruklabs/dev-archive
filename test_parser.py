#!/usr/bin/env python3
"""
Test script for HTML to YAML parser
Tests the parsing functionality locally before deployment
"""

import os
import sys
import yaml
import tempfile
import shutil
from pathlib import Path
from parse_html_to_yaml import main as parse_main

def test_parser():
    """Test the parser with existing HTML files and validate output."""
    print("🧪 Testing HTML to YAML parser...")
    
    # Check if we have captured HTML files
    captures_dir = Path('captures')
    if not captures_dir.exists():
        print("❌ No captures directory found. Need HTML files to test.")
        return False
    
    html_files = list(captures_dir.rglob('*.html'))
    if not html_files:
        print("❌ No HTML files found in captures directory.")
        return False
    
    print(f"📄 Found {len(html_files)} HTML files to test with")
    
    # Create a temporary directory for testing
    with tempfile.TemporaryDirectory() as temp_dir:
        # Copy captures to temp directory
        temp_captures = Path(temp_dir) / 'captures'
        shutil.copytree('captures', temp_captures)
        
        # Set up temporary parsed directory
        temp_parsed = Path(temp_dir) / 'parsed'
        temp_parsed.mkdir(exist_ok=True)
        
        # Save original directories
        original_cwd = os.getcwd()
        
        try:
            # Change to temp directory
            os.chdir(temp_dir)
            
            # Run the parser
            print("🔄 Running parser...")
            parse_main()
            
            # Validate output
            parsed_files = list(temp_parsed.rglob('*.yaml'))
            if not parsed_files:
                print("❌ No YAML files were generated")
                return False
            
            print(f"✅ Generated {len(parsed_files)} YAML files")
            
            # Validate YAML structure
            valid_files = 0
            for yaml_file in parsed_files:
                try:
                    with open(yaml_file, 'r') as f:
                        data = yaml.safe_load(f)
                    
                    # Basic validation
                    if isinstance(data, dict) and 'source' in data:
                        valid_files += 1
                        print(f"✅ {yaml_file.name}: Valid YAML with source '{data.get('source')}'")
                    else:
                        print(f"⚠️  {yaml_file.name}: Missing required fields")
                        
                except yaml.YAMLError as e:
                    print(f"❌ {yaml_file.name}: Invalid YAML - {e}")
                except Exception as e:
                    print(f"❌ {yaml_file.name}: Error reading file - {e}")
            
            print(f"\n📊 Test Results:")
            print(f"   HTML files processed: {len(html_files)}")
            print(f"   YAML files generated: {len(parsed_files)}")
            print(f"   Valid YAML files: {valid_files}")
            
            if valid_files > 0:
                print("✅ Parser test passed!")
                return True
            else:
                print("❌ Parser test failed - no valid YAML files generated")
                return False
                
        finally:
            # Restore original directory
            os.chdir(original_cwd)

def test_dependencies():
    """Test if all required dependencies are available."""
    print("🔍 Checking dependencies...")
    
    required_modules = [
        ('yaml', 'pyyaml'),
        ('bs4', 'beautifulsoup4'),
        ('requests', 'requests')
    ]
    
    missing = []
    for module, package in required_modules:
        try:
            __import__(module)
            print(f"✅ {package}")
        except ImportError:
            print(f"❌ {package} - not found")
            missing.append(package)
    
    if missing:
        print(f"\n❌ Missing dependencies: {', '.join(missing)}")
        print("Install with: pip install " + " ".join(missing))
        return False
    
    print("✅ All dependencies available")
    return True

def main():
    """Run all tests."""
    print("🚀 HTML to YAML Parser Test Suite")
    print("=" * 40)
    
    # Test dependencies first
    if not test_dependencies():
        sys.exit(1)
    
    print()
    
    # Test parser functionality
    if not test_parser():
        sys.exit(1)
    
    print("\n🎉 All tests passed! Parser is ready for deployment.")

if __name__ == "__main__":
    main()