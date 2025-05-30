#!/usr/bin/env python3

"""
HTML to YAML Parser

This script parses HTML files captured by capture_and_parse.py using the purehtml library
and converts them to structured YAML files for easier analysis and processing.
"""

import os
import json
import yaml
import argparse
from pathlib import Path
from datetime import datetime, timezone
from urllib.parse import urlparse
import purehtml


CONFIG_FILE = 'config.json'
CAPTURES_DIR = 'captures'
PARSED_DIR = 'parsed'
DELAY_RANGE = (1, 2)  # seconds between processing files


def load_config():
    """Load configuration from config.json"""
    with open(CONFIG_FILE, 'r') as f:
        return json.load(f)


def extract_metadata_from_path(html_path):
    """Extract metadata from the file path structure"""
    path_parts = Path(html_path).parts
    
    metadata = {
        'source_file': str(html_path),
        'parsed_at': datetime.now(timezone.utc).isoformat(),
    }
    
    # Extract date from path (assuming captures/capture/YYYY-MM-DD/...)
    if len(path_parts) >= 3 and path_parts[1] == 'capture':
        try:
            metadata['capture_date'] = path_parts[2]
        except (IndexError, ValueError):
            pass
    
    # Extract source type (hackernews, ph, gh, etc.)
    if len(path_parts) >= 4:
        metadata['source_type'] = path_parts[3]
        
        # Handle GitHub specific structure
        if path_parts[3] == 'gh' and len(path_parts) >= 5:
            metadata['gh_section'] = path_parts[4]  # trending, topics
            if len(path_parts) >= 6:
                metadata['gh_subsection'] = path_parts[5]  # daily/weekly/monthly for trending
    
    return metadata


def parse_html_content(html_content, source_type=None):
    """Parse HTML content using purehtml and extract structured data"""
    
    try:
        # Convert HTML to clean markdown format
        markdown_content = purehtml.purify_html_str(
            html_content, 
            output_format='markdown',
            keep_href=True,
            keep_format_tags=True,
            keep_group_tags=True
        )
        
        # Also get clean HTML version
        clean_html = purehtml.purify_html_str(
            html_content,
            output_format='html',
            keep_href=True,
            keep_format_tags=True,
            keep_group_tags=True
        )
        
        # Basic content analysis
        content_info = {
            'markdown_length': len(markdown_content),
            'html_length': len(clean_html),
            'original_html_length': len(html_content),
            'compression_ratio': round(len(clean_html) / len(html_content), 3) if html_content else 0
        }
        
        # Extract basic text statistics
        lines = markdown_content.split('\n')
        non_empty_lines = [line for line in lines if line.strip()]
        
        content_info.update({
            'total_lines': len(lines),
            'non_empty_lines': len(non_empty_lines),
            'has_headers': '#' in markdown_content,  # More flexible header detection
            'has_links': '[' in markdown_content and '](' in markdown_content,
        })
        
        return {
            'success': True,
            'markdown': markdown_content,
            'clean_html': clean_html,
            'content_info': content_info,
            'error': None
        }
        
    except Exception as e:
        return {
            'success': False,
            'markdown': None,
            'clean_html': None,
            'content_info': None,
            'error': str(e)
        }


def process_html_file(html_path, output_path):
    """Process a single HTML file and save as YAML"""
    
    try:
        # Read HTML content
        with open(html_path, 'r', encoding='utf-8', errors='replace') as f:
            html_content = f.read()
        
        # Extract metadata from path
        metadata = extract_metadata_from_path(html_path)
        
        # Parse HTML content  
        parse_result = parse_html_content(html_content, metadata.get('source_type'))
        
        # Create structured output
        output_data = {
            'metadata': metadata,
            'parsing': {
                'success': parse_result['success'],
                'error': parse_result['error'],
                'processed_at': datetime.now(timezone.utc).isoformat()
            },
            'content': {
                'info': parse_result['content_info'],
                'markdown': parse_result['markdown'],
                'clean_html': parse_result['clean_html']
            }
        }
        
        # Ensure output directory exists
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        # Save as YAML
        with open(output_path, 'w', encoding='utf-8') as f:
            yaml.dump(output_data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
        
        return True, None
        
    except Exception as e:
        return False, str(e)


def find_html_files(captures_dir):
    """Find all HTML files in the captures directory"""
    html_files = []
    
    for root, dirs, files in os.walk(captures_dir):
        for file in files:
            if file.endswith('.html'):
                html_files.append(os.path.join(root, file))
    
    return sorted(html_files)


def get_output_path(html_path, parsed_dir):
    """Generate output path for parsed YAML file"""
    # Convert captures/... to parsed/...
    rel_path = os.path.relpath(html_path, CAPTURES_DIR)
    yaml_path = os.path.join(parsed_dir, rel_path.replace('.html', '.yaml'))
    return yaml_path


def main():
    parser = argparse.ArgumentParser(description='Parse HTML files to YAML using purehtml')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be processed without doing it')
    parser.add_argument('--force', action='store_true', help='Reprocess files even if output already exists')
    parser.add_argument('--filter', type=str, help='Only process files containing this string in their path')
    parser.add_argument('--limit', type=int, help='Limit number of files to process (for testing)')
    args = parser.parse_args()

    # Find all HTML files
    html_files = find_html_files(CAPTURES_DIR)
    
    if args.filter:
        html_files = [f for f in html_files if args.filter in f]
    
    if args.limit:
        html_files = html_files[:args.limit]
    
    print(f"[INFO] Found {len(html_files)} HTML files to process")
    
    if args.dry_run:
        print('[INFO] Dry run: files that would be processed:')
        for html_file in html_files:
            output_file = get_output_path(html_file, PARSED_DIR)
            status = "EXISTS" if os.path.exists(output_file) else "NEW"
            print(f"  {html_file} -> {output_file} [{status}]")
        return
    
    # Process files
    processed = 0
    skipped = 0
    errors = 0
    
    for html_file in html_files:
        output_file = get_output_path(html_file, PARSED_DIR)
        
        # Skip if output exists and not forcing
        if os.path.exists(output_file) and not args.force:
            print(f"[SKIP] {html_file} (output exists)")
            skipped += 1
            continue
        
        print(f"[PROCESS] {html_file}")
        success, error = process_html_file(html_file, output_file)
        
        if success:
            print(f"[SUCCESS] Saved to {output_file}")
            processed += 1
        else:
            print(f"[ERROR] Failed to process {html_file}: {error}")
            errors += 1
    
    print(f"\n[SUMMARY] Processed: {processed}, Skipped: {skipped}, Errors: {errors}")


if __name__ == '__main__':
    main()