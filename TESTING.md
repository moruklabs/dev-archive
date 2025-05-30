# Testing the HTML to YAML Parser

This document explains how to test the HTML to YAML parsing workflow before merging.

## Quick Test

Run the automated test suite:

```bash
python test_parser.py
```

This will:
- ✅ Check all required dependencies
- ✅ Process all HTML files in `captures/` directory  
- ✅ Validate YAML output structure
- ✅ Report success/failure with detailed statistics

## Manual Testing Options

### 1. **Local Testing** (Recommended)
Test the parser locally with existing captured data:

```bash
# Install dependencies
pip install -r requirements.txt

# Run the parser
python parse_html_to_yaml.py

# Check the output
ls -la parsed/
```

### 2. **GitHub Actions Manual Trigger**
The workflow includes `workflow_dispatch` which allows manual execution:

1. Go to **Actions** tab in GitHub
2. Select **"Parse HTML to YAML"** workflow
3. Click **"Run workflow"** button
4. Monitor the execution and check artifacts

### 3. **Test with Subset of Files**
Test with specific HTML files:

```bash
# Create a test directory with sample files
mkdir -p test_captures/capture/2025-05-30/
cp captures/capture/2025-05-30/hn/index.html test_captures/capture/2025-05-30/

# Update CAPTURES_DIR in parse_html_to_yaml.py temporarily to 'test_captures'
# Run parser and verify output
```

## What the Tests Validate

### ✅ **Dependency Check**
- `pyyaml` - YAML output generation
- `beautifulsoup4` - HTML parsing  
- `requests` - HTTP utilities

### ✅ **Parsing Functionality**
- **HackerNews**: Story extraction (titles, URLs, scores, comments)
- **GitHub Trending**: Repository data (stars, forks, descriptions)
- **GitHub Topics**: Topic-based repository listings
- **ProductHunt**: Basic product information
- **Generic HTML**: Fallback parsing with BeautifulSoup

### ✅ **Output Validation**
- Valid YAML structure
- Required fields present (`source`, `captured_at`, etc.)
- Consistent file organization matching `captures/` structure

## Expected Results

With current test data (147 HTML files):
- **Input**: 147 HTML files from various sources
- **Output**: 147 corresponding YAML files
- **Success Rate**: 100% (all files should parse successfully)
- **Sources Detected**: `github_trending`, `github_topics`, `hackernews`, `producthunt`

## Troubleshooting

### Missing Dependencies
```bash
pip install beautifulsoup4 pyyaml requests
```

### No HTML Files Found
Ensure `captures/` directory exists with HTML files from the capture workflow.

### YAML Validation Errors
Check the parser logs for specific parsing issues with individual files.

## Workflow Schedule Testing

The workflow runs every 20 minutes (`*/20 * * * *`). To verify timing:
1. Check the workflow file: `.github/workflows/parse-html-to-yaml.yml`
2. Validate cron expression at [crontab.guru](https://crontab.guru)
3. Monitor actual execution times in GitHub Actions

## Safe Testing

The workflow includes safety measures:
- ✅ Runs on separate schedule from capture workflow
- ✅ Uses artifacts to transfer data between jobs
- ✅ Only commits if new parsed data exists
- ✅ Pulls latest changes before committing to avoid conflicts