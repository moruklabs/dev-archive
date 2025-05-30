# HTML to YAML Parser

This directory contains a HTML to YAML parsing job that processes captured HTML files using the [purehtml](https://purescraps.github.io/purehtml/) library.

## Overview

The HTML parser (`parse_html_to_yaml.py`) takes the HTML files captured by `capture_and_parse.py` and converts them to structured YAML files for easier analysis and processing.

## Features

- **HTML Cleaning**: Uses purehtml to clean and normalize HTML content
- **Dual Output**: Generates both markdown and clean HTML versions
- **Metadata Extraction**: Automatically extracts metadata from file paths
- **Content Analysis**: Provides statistics about the parsed content
- **Structured Output**: Saves results in YAML format for easy processing
- **Error Handling**: Comprehensive error handling and logging
- **Flexible Processing**: Support for filtering, dry-run, and force-reprocess options

## Usage

### Basic Usage

```bash
# Process all HTML files
python parse_html_to_yaml.py

# Dry run to see what would be processed
python parse_html_to_yaml.py --dry-run

# Process only a subset of files
python parse_html_to_yaml.py --filter hackernews --limit 5

# Force reprocessing of existing files
python parse_html_to_yaml.py --force
```

### Command Line Options

- `--dry-run`: Show what would be processed without actually doing it
- `--force`: Reprocess files even if output already exists
- `--filter <string>`: Only process files containing this string in their path
- `--limit <number>`: Limit number of files to process (useful for testing)

## Output Format

The parser generates YAML files with the following structure:

```yaml
metadata:
  source_file: captures/capture/2025-05-30/hackernews/home.html
  parsed_at: '2025-05-30T19:30:37.380209+00:00'
  capture_date: '2025-05-30'
  source_type: hackernews

parsing:
  success: true
  error: null
  processed_at: '2025-05-30T19:30:37.833254+00:00'

content:
  info:
    markdown_length: 5502
    html_length: 13471
    original_html_length: 37125
    compression_ratio: 0.363
    total_lines: 140
    non_empty_lines: 139
    has_headers: true
    has_links: false
  markdown: |
    # Content in markdown format...
  clean_html: |
    <p>Content in clean HTML format...</p>
```

## Directory Structure

```
captures/               # Input HTML files (from capture_and_parse.py)
├── capture/
│   └── 2025-05-30/
│       ├── hackernews/
│       ├── gh/
│       └── ph/
│
parsed/                 # Output YAML files (from parse_html_to_yaml.py)
├── capture/
│   └── 2025-05-30/
│       ├── hackernews/
│       ├── gh/
│       └── ph/
```

## Workflow Integration

The parser is integrated into the GitHub Actions workflow:

1. **capture-and-parse**: Captures HTML content from websites
2. **parse-html-to-yaml**: Processes HTML files to generate YAML (NEW)
3. **commit-captures**: Commits both HTML captures and parsed YAML files

The workflow runs hourly and automatically processes new HTML files.

## Testing

Run the test suite to ensure everything is working correctly:

```bash
python test_parser.py
```

## Dependencies

The parser requires these additional dependencies (added to `requirements.txt`):

- `purehtml`: For HTML cleaning and conversion
- `termcolor`: Required by purehtml
- `pyyaml`: For YAML file generation

## Error Handling

The parser includes comprehensive error handling:

- Invalid HTML files are logged but don't stop processing
- Network issues or file access problems are caught and reported
- Parsing errors are saved in the YAML output for debugging
- Summary statistics are provided at the end of each run