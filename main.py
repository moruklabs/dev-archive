import os
import json
import time
import random
import re
import requests
from datetime import datetime, timezone
from itertools import product
from urllib.parse import urlparse

import xml.etree.ElementTree as ET
import dotenv
import argparse
import concurrent.futures
from urllib.parse import quote

try:

    if not os.environ.get('GITHUB_ACTIONS', '').lower() == 'true':
        dotenv.load_dotenv('.env')
except ImportError:
    pass

CONFIG_FILE = 'config.json'
CAPTURES_DIR = 'rss'
DELAY_RANGE = (1, 3)  # seconds, shorter to keep jobs fast
MAX_RETRIES = 3
BACKOFF_FACTOR = 2
REQUEST_TIMEOUT = 10  # seconds

# Our own base URL for RSS feeds - using GitHub Pages URL for this repository
OUR_BASE_URL = "https://moruklabs.github.io/dev-archive"

def is_safe_path(base_dir, path):
    base_dir = os.path.realpath(base_dir)
    path = os.path.realpath(path)
    return os.path.commonpath([base_dir]) == os.path.commonpath([base_dir, path])

def load_config():
    with open(CONFIG_FILE, 'r') as f:
        return json.load(f)

def substitute(template, variables):
    variables = dict(variables)
    variables['today'] = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    def replacer(match):
        var = match.group(1)
        return str(variables.get(var, match.group(0)))
    return re.sub(r'\$?\{([^}]+)\}', replacer, template)

def transform_rss_content(content, lang, feed_type):
    """Transform RSS content to use our own links and ensure proper RSS compliance."""
    try:
        # Parse the RSS XML
        root = ET.fromstring(content)
        
        # Find the channel element
        channel = root.find('channel')
        if channel is None:
            print(f"[ERROR] No channel element found in RSS")
            return content
        
        # Update channel link to point to our repository
        link_elem = channel.find('link')
        if link_elem is not None:
            link_elem.text = OUR_BASE_URL
        
        # Update channel description to include our branding
        desc_elem = channel.find('description')
        if desc_elem is not None:
            original_desc = desc_elem.text or ""
            if "GitHub" in original_desc and "Trending" in original_desc:
                # Update description to indicate this is our curated feed
                desc_elem.text = f"Curated {original_desc} - Archived by MorukLabs"
        
        # Add or update channel elements for better RSS compliance
        # Add language if not present
        if channel.find('language') is None:
            lang_elem = ET.SubElement(channel, 'language')
            lang_elem.text = 'en-us'
        
        # Add generator info
        generator_elem = channel.find('generator')
        if generator_elem is None:
            generator_elem = ET.SubElement(channel, 'generator')
        generator_elem.text = 'MorukLabs Dev Archive RSS Generator'
        
        # Process each item
        for item in channel.findall('item'):
            # Update item links to point to our archive instead of direct GitHub
            link_elem = item.find('link')
            if link_elem is not None and link_elem.text:
                github_url = link_elem.text
                if github_url.startswith('https://github.com/'):
                    # Extract repo name from GitHub URL
                    repo_name = github_url.replace('https://github.com/', '')
                    # Create our own URL that will eventually redirect or show info about this repo
                    our_url = f"{OUR_BASE_URL}/repo/{quote(repo_name)}"
                    link_elem.text = our_url
            
            # Add GUID for better RSS compatibility if not present
            guid_elem = item.find('guid')
            if guid_elem is None and link_elem is not None:
                guid_elem = ET.SubElement(item, 'guid')
                guid_elem.text = link_elem.text
                guid_elem.set('isPermaLink', 'true')
            
            # Ensure pubDate is present for the item
            pubdate_elem = item.find('pubDate')
            if pubdate_elem is None:
                # Use channel pubDate or current time
                channel_pubdate = channel.find('pubDate')
                pubdate_elem = ET.SubElement(item, 'pubDate')
                if channel_pubdate is not None and channel_pubdate.text:
                    pubdate_elem.text = channel_pubdate.text
                else:
                    pubdate_elem.text = datetime.now(timezone.utc).strftime('%a, %d %b %Y %H:%M:%S GMT')
        
        # Convert back to string with proper XML declaration
        xml_str = ET.tostring(root, encoding='utf-8', xml_declaration=True).decode('utf-8')
        
        # Basic formatting: add newlines after major elements for readability
        xml_str = xml_str.replace('><', '>\n<')
        
        return xml_str
        
    except ET.ParseError as e:
        print(f"[ERROR] Failed to parse RSS XML: {e}")
        return content
    except Exception as e:
        print(f"[ERROR] Failed to transform RSS content: {e}")
        return content

def expand_targets(defs, targets):
    # Separate fixed and list variables from defs
    fixed_defs = {k: v for k, v in defs.items() if not isinstance(v, list)}
    list_defs = {k: v for k, v in defs.items() if isinstance(v, list)}

    # Heuristic mapping for template variable names (e.g., "langs" -> "lang")
    list_var_template_names_map = {
        key: key[:-1] if key.endswith('s') and len(key) > 1 else key
        for key in list_defs.keys()
    }

    all_expanded_targets = []

    # Generate all combinations from defs list variables
    defs_combinations = []
    if list_defs:
        list_product_keys = sorted(list(list_defs.keys())) # Ensure consistent order
        list_product_values = [list_defs[key] for key in list_product_keys]
        for combo_values in product(*list_product_values):
            combo_dict = {}
            for i, list_key in enumerate(list_product_keys):
                template_var_name = list_var_template_names_map.get(list_key, list_key)
                combo_dict[template_var_name] = combo_values[i]
            defs_combinations.append(combo_dict)
    else:
        defs_combinations.append({}) # No list variables in defs, so just one empty combination

    for defs_combo in defs_combinations:
        # Construct the base variables for the current defs combination
        current_base_vars_for_base_sub = {**fixed_defs, **defs_combo}
        current_base_vars = {**current_base_vars_for_base_sub}
        # Substitute 'base' now that all defs variables are available for this combination
        current_base_vars['base'] = substitute(defs.get('base', ''), current_base_vars_for_base_sub)

        for target in targets:
            # Separate fixed and list variables from target vars
            target_vars = target.get('vars', {})
            fixed_target_vars = {k: v for k, v in target_vars.items() if not isinstance(v, list)}
            list_target_vars = {k: v for k, v in target_vars.items() if isinstance(v, list)}

            # Generate all combinations from target list variables
            target_combinations = []
            if list_target_vars:
                target_list_product_keys = sorted(list(list_target_vars.keys())) # Ensure consistent order
                target_list_product_values = [list_target_vars[key] for key in target_list_product_keys]
                for combo_values in product(*target_list_product_values):
                    combo_dict = dict(zip(target_list_product_keys, combo_values))
                    target_combinations.append(combo_dict)
            else:
                target_combinations.append({}) # No list variables in target, so just one empty combination

            for target_combo in target_combinations:
                # Combine all variables for the final substitution
                all_vars = {
                    **current_base_vars,
                    **fixed_target_vars,
                    **target_combo
                }

                filepath = substitute(target.get('filepath', ''), all_vars)
                url = substitute(target.get('url', ''), all_vars)

                # Extract language for grouping if present in all_vars
                lang = all_vars.get(list_var_template_names_map.get('langs', 'langs'))

                expanded_entry = {'filepath': filepath, 'url': url}
                if lang:
                    expanded_entry['lang'] = lang
                all_expanded_targets.append(expanded_entry)

    return all_expanded_targets

ALLOWED_DOMAINS = {"mshibanami.github.io"}

def process_language_targets(language_targets):
    """Processes a list of targets for a single language sequentially."""
    language_failures = []
    for entry in language_targets:
        if 'filepath' not in entry:
            print(f"[ERROR] Main loop: Entry missing 'filepath': {entry}")
            language_failures.append({"url": entry.get('url', '[NO URL]'), "filepath": "[MISSING FILEPATH]", "error": "missing filepath"})
            continue
        filepath = os.path.join(CAPTURES_DIR, entry['filepath'])
        if not is_safe_path(CAPTURES_DIR, filepath):
            print(f"[ERROR] Unsafe filepath detected: {filepath}")
            language_failures.append({"url": entry.get('url', '[NO URL]'), "filepath": filepath, "error": "unsafe filepath"})
            continue
        url = entry.get('url', '[NO URL]')
        if url == '[NO URL]':
            print(f"[ERROR] Main loop: Entry missing 'url' for filepath: {filepath}")
            language_failures.append({"url": "[MISSING URL]", "filepath": filepath, "error": "Missing URL in config entry"})
            continue

        if os.path.exists(filepath) and os.path.getsize(filepath) > 0:
            print(f"[INFO] Skipping {url} -> {filepath} (file exists and is non-empty)")
            continue

        print(f"[INFO] Processing {url} -> {filepath}")
        content = fetch_url(url)
        if content:
            ## check if the content is valid xml
            try:
                ET.fromstring(content)
            except ET.ParseError:
                print(f"[ERROR] Invalid XML content for {url}")
                language_failures.append({"url": url, "filepath": filepath, "error": "invalid XML"})
                continue
            
            # Extract language and feed type from filepath for transformation
            path_parts = filepath.split('/')
            lang = entry.get('lang', 'unknown')
            feed_type = 'unknown'
            filename = path_parts[-1]
            if filename.endswith('.xml'):
                feed_type = filename[:-4]  # Remove .xml extension
            
            # Transform RSS content to use our own links
            transformed_content = transform_rss_content(content, lang, feed_type)
            
            save_content(os.path.dirname(filepath), os.path.basename(filepath), transformed_content)
            print(f"[INFO] Saved transformed content for {url} to {filepath}")
        else:
            print(f"[ERROR] Failed to fetch content for {url}")
            language_failures.append({"url": url, "filepath": filepath, "error": "fetch failed"})

        delay = random.uniform(*DELAY_RANGE)
        print(f"[INFO] Sleeping for {delay:.2f} seconds...")
        time.sleep(delay)
    return language_failures

def fetch_url(url):
    parsed = urlparse(url)
    if parsed.netloc not in ALLOWED_DOMAINS:
        print(f"[ERROR] Refusing to fetch from unauthorized domain: {parsed.netloc}")
        return None
    headers = {"User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_6_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.6 Mobile/15E148 Safari/604.1 OPT/5.0.5"}
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
            if resp.status_code == 200:
                return resp.text
            elif resp.status_code in (429, 500, 502, 503, 504):
                print(f"[WARN] Retrying {url} due to status {resp.status_code} (attempt {attempt}/{MAX_RETRIES})")
                time.sleep(BACKOFF_FACTOR ** attempt)
            else:
                print(f"[ERROR] Non-retryable error {resp.status_code} for {url}")
                return None
        except requests.exceptions.RequestException as e_req:
            print(f"[ERROR] RequestException during fetch for {url} (attempt {attempt}/{MAX_RETRIES}): {e_req}")
            time.sleep(BACKOFF_FACTOR ** attempt)
    print(f"[ERROR] Failed to fetch {url} after {MAX_RETRIES} attempts.")
    return None

def save_content(folder, filename, content):
    os.makedirs(folder, exist_ok=True)
    file_path = os.path.join(folder, filename)
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)

def generate_folders(defs, targets):
    expanded = expand_targets(defs, targets)
    for entry in expanded:
        if 'filepath' not in entry:
            print(f"[ERROR] Entry missing 'filepath': {entry}")
            continue
        filepath = os.path.join(CAPTURES_DIR, entry['filepath'])
        print(f"[INFO] Creating parent directory for: {filepath}")
        os.makedirs(os.path.dirname(filepath), exist_ok=True)

def send_telegram_message(message):
    token = os.environ.get('TELEGRAM_BOT_TOKEN')
    chat_id = os.environ.get('TELEGRAM_CHAT_ID')
    if not token or not chat_id:
        print("Telegram bot token or chat ID not set; skipping notification.")
        return
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = {"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}
    try:
        resp = requests.post(url, data=data, timeout=REQUEST_TIMEOUT)
        if resp.status_code != 200:
            print(f"Failed to send Telegram message: {resp.text}")
    except Exception as e:
        print(f"Exception sending Telegram message: {e}")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dry-run', action='store_true', help='Print expanded URLs and paths, then exit')
    parser.add_argument('--test', action='store_true', help='Test mode: process only a subset of items')
    parser.add_argument('--random', action='store_true', help='Shuffle items before processing (only active if --test is also specified)')
    parser.add_argument('--number', type=int, default=1, help='Number of items to process in test mode (default: 1)')
    args = parser.parse_args()

    config = load_config()
    defs = config.get('defs', {})
    targets = config.get('target', [])

    # Generate folders for all potential targets initially
    generate_folders(defs, targets)
    expanded = expand_targets(defs, targets)

    if args.test:
        if args.random:
            print("[INFO] Test mode: Randomizing target list.")
            random.shuffle(expanded)
        else:
            print("[INFO] Test mode: Using first N targets.")
        if args.number > len(expanded):
            print(f"[WARN] Requested number ({args.number}) is more than available targets ({len(expanded)}). Processing all available.")
            args.number = len(expanded)
        expanded = expanded[:args.number]
        print(f"[INFO] Test mode: Processing {len(expanded)} item(s).")

    if args.dry_run:
        print('[INFO] Dry run: expanded URLs and paths to be processed:')
        if not expanded:
            print("[INFO] No items selected for dry run.")
        for entry in expanded:
            if 'filepath' not in entry:
                print(f"[ERROR] Dry run: Entry missing 'filepath': {entry}")
                continue
            filepath = os.path.join(CAPTURES_DIR, entry['filepath'])
            url = entry.get('url', '[NO URL]')
            lang = entry.get('lang', '[NO LANG]')
            print(f"[LANG: {lang}] {url} -> {filepath}")
        return

    failures = []
    if not expanded:
        print("[INFO] No items to process.")

    # Group targets by language
    language_groups = {}
    for entry in expanded:
        lang = entry.get('lang', 'default')  # Use 'default' if no language is specified
        if lang not in language_groups:
            language_groups[lang] = []
        language_groups[lang].append(entry)

    # Process each language group in parallel using ThreadPoolExecutor
    with concurrent.futures.ThreadPoolExecutor() as executor:
        future_to_lang = {
            executor.submit(process_language_targets, targets_for_lang):
            lang for lang, targets_for_lang in language_groups.items()
        }
        for future in concurrent.futures.as_completed(future_to_lang):
            lang = future_to_lang[future]
            try:
                language_failures = future.result()
                failures.extend(language_failures)
                print(f"[INFO] Finished processing language group: {lang}")
            except Exception as exc:
                print(f"[ERROR] Language group {lang} generated an exception: {exc}")
                failures.append({"language": lang, "error": str(exc), "type": "thread_exception"})

    if failures:
        msg_lines = [f"*Capture Failures* ({datetime.now(timezone.utc).isoformat()} UTC):"]
        for f in failures:
            msg_lines.append(f"- `{f.get('url', f.get('language', 'unknown'))}` for `{f.get('filepath', 'unknown')}`: {f['error']}")
        send_telegram_message('\n'.join(msg_lines))

    print("[INFO] Script finished.")

if __name__ == '__main__':
    main()
